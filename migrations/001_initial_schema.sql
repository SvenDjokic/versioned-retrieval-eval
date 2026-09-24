-- Initial schema.
--
-- Two kinds of storage, one system: the relational tables say what a document
-- IS and how it relates to others; the vector column says what its text MEANS.
-- Keeping both in Postgres makes supersession resolution a join rather than a
-- round trip into a second system that can drift out of sync.

CREATE EXTENSION IF NOT EXISTS vector;


-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
-- Bi-temporal, because "what did we believe in March 2024" and "what governed
-- in March 2024" are different questions and both need answering.
--
--   valid_from / valid_to : when this document governed in the world
--   recorded_at           : when this system learned about it
--
-- A document that is still in force has valid_to = NULL.

CREATE TABLE documents (
    id            bigserial PRIMARY KEY,

    -- Stable identifier from the source corpus (filename, slug, URL).
    -- Lets a re-import update rows instead of duplicating them.
    external_id   text        NOT NULL UNIQUE,

    title         text        NOT NULL,
    doc_type      text        NOT NULL,
    source        text,

    -- Human-facing version as the source labels it ("v5.3.1", "18.20.8").
    -- Deliberately text: version schemes are not comparable across corpora.
    version_label text,

    valid_from    timestamptz,
    valid_to      timestamptz,
    recorded_at   timestamptz NOT NULL DEFAULT now(),

    -- Denormalised for cheap filtering. Derivable from valid_to and the
    -- relationships table, and must be kept consistent with them.
    status        text        NOT NULL DEFAULT 'current'
                  CHECK (status IN ('current', 'superseded', 'draft')),

    -- Anything extracted at ingestion that does not deserve a column yet.
    metadata      jsonb       NOT NULL DEFAULT '{}'::jsonb,

    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT documents_valid_range
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX documents_doc_type_idx   ON documents (doc_type);
CREATE INDEX documents_status_idx     ON documents (status);
CREATE INDEX documents_valid_from_idx ON documents (valid_from);
CREATE INDEX documents_metadata_idx   ON documents USING gin (metadata);


-- ---------------------------------------------------------------------------
-- document_relationships
-- ---------------------------------------------------------------------------
-- The edges that make "what governs" answerable.
--
--   supersedes : a later version replaces an earlier one outright
--   amends     : a second document modifies the first without replacing it.
--                Both are needed to answer correctly, and neither alone is
--                right. This is the case naive retrieval gets confidently wrong
--   references : a mention, carrying no authority

CREATE TABLE document_relationships (
    id             bigserial PRIMARY KEY,
    from_doc       bigint      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    to_doc         bigint      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    relation       text        NOT NULL
                   CHECK (relation IN ('supersedes', 'amends', 'references')),
    effective_date timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT document_relationships_no_self_edge CHECK (from_doc <> to_doc),
    CONSTRAINT document_relationships_unique UNIQUE (from_doc, to_doc, relation)
);

CREATE INDEX document_relationships_from_idx     ON document_relationships (from_doc);
CREATE INDEX document_relationships_to_idx       ON document_relationships (to_doc);
CREATE INDEX document_relationships_relation_idx ON document_relationships (relation);


-- ---------------------------------------------------------------------------
-- chunks
-- ---------------------------------------------------------------------------
-- The retrievable units. Embedding is nullable so documents can be loaded and
-- inspected before the embedding step runs.
--
-- Dimension 1024 matches voyage-3. Changing embedding model means a migration,
-- which is the honest cost of storing vectors in a typed column.

CREATE TABLE chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,

    -- Position within the document, so retrieved chunks can be re-ordered
    -- into reading order and neighbours can be pulled in for context.
    ordinal      int         NOT NULL,

    section      text,
    content      text        NOT NULL,

    -- Contextual retrieval: a short document- and section-level summary
    -- prepended before embedding, so a chunk carries where it came from.
    -- Stored separately to keep the original text unmodified.
    context_prefix text,

    embedding    vector(1024),
    token_count  int,

    -- The keyword half of hybrid search. GENERATED means Postgres maintains
    -- it automatically on every insert and update.
    content_tsv  tsvector    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chunks_unique_position UNIQUE (document_id, ordinal)
);

CREATE INDEX chunks_document_idx ON chunks (document_id);
CREATE INDEX chunks_tsv_idx      ON chunks USING gin (content_tsv);

-- HNSW approximate-nearest-neighbour index for cosine distance.
-- Built now while the table is empty, which is cheap; building it later over
-- a populated table takes minutes.
CREATE INDEX chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops);


-- ---------------------------------------------------------------------------
-- eval_questions
-- ---------------------------------------------------------------------------
-- Ground truth. `source` distinguishes the published VersionQA set from
-- questions added here, so results can be reported both ways: comparable to
-- the paper's numbers, and including the categories it does not cover.

CREATE TABLE eval_questions (
    id              bigserial PRIMARY KEY,
    external_id     text        NOT NULL UNIQUE,
    source          text        NOT NULL DEFAULT 'versionqa',
    category        text        NOT NULL,
    question        text        NOT NULL,

    -- NULL means the correct behaviour is to abstain. That is a real expected
    -- answer, not missing data, and it is the category VersionQA omits.
    expected_answer text,

    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX eval_questions_category_idx ON eval_questions (category);
CREATE INDEX eval_questions_source_idx   ON eval_questions (source);


-- ---------------------------------------------------------------------------
-- eval_runs
-- ---------------------------------------------------------------------------
-- One row per execution of the full question set under one configuration.
-- `config` holds what was actually used: chunking, retriever, reranker,
-- models. This is what lets the results table in the README be generated
-- rather than hand-maintained.

CREATE TABLE eval_runs (
    id          bigserial PRIMARY KEY,
    label       text        NOT NULL,
    config      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    git_sha     text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    notes       text
);


-- ---------------------------------------------------------------------------
-- eval_results
-- ---------------------------------------------------------------------------
-- One row per question per run. Keeping the retrieved chunk ids means a
-- failure can be diagnosed later without re-running: did retrieval miss the
-- right chunk, or did it find it and the answer still came out wrong?

CREATE TABLE eval_results (
    id                 bigserial PRIMARY KEY,
    run_id             bigint      NOT NULL REFERENCES eval_runs (id) ON DELETE CASCADE,
    question_id        bigint      NOT NULL REFERENCES eval_questions (id) ON DELETE CASCADE,

    answer             text,
    abstained          boolean     NOT NULL DEFAULT false,

    retrieved_chunk_ids bigint[]   NOT NULL DEFAULT '{}',

    -- Scored by an LLM judge against expected_answer.
    correct            boolean,
    judge_reason       text,

    latency_ms         int,
    cost_usd           numeric(10, 6),

    created_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT eval_results_unique_per_run UNIQUE (run_id, question_id)
);

CREATE INDEX eval_results_run_idx      ON eval_results (run_id);
CREATE INDEX eval_results_question_idx ON eval_results (question_id);
CREATE INDEX eval_results_correct_idx  ON eval_results (run_id, correct);
