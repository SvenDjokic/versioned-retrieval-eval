# versioned-retrieval-eval

**An evaluation harness for retrieval over document corpora where later documents supersede earlier ones.**

> **Status: early.** This README currently contains a survey of prior art and the evaluation design. The harness is in progress. Results tables will appear here as they are produced, including the ones that do not improve.

---

## The problem

Most retrieval systems treat a corpus as a flat set of documents and return whatever scores highest. That assumption breaks whenever documents supersede each other, and it breaks quietly: the system returns an answer from a superseded document, with citations, confidently.

Three shapes of the problem, which behave differently and are often conflated:

**Linear revision.** A document reaches its fourth version. Latest-wins usually works here.

**Amendment.** A signed agreement is later modified by a second document. The second does not replace the first. Neither document alone is the answer, and there is often no version number connecting them. Latest-wins picks one and silently drops the other half.

**Point-in-time.** "What governed in March 2024" and "what do we believe now" are different questions over the same corpus. Answering the first requires deliberately retrieving a superseded version.

The amendment case is the interesting one, because it is not really a versioning problem. It is a question of **what governs**, which is a relationship between documents rather than a property of any one of them.

---

## Why this repository exists

There is a real and active literature here. There is much less measurement.

The research publishes benchmarks. The open-source implementations largely do not: the most visible one ships before-and-after demonstration scenarios and no numbers at all. And each published approach reports results on its own benchmark, so they have not been compared directly on a common corpus.

This repository is an attempt at that comparison, plus the evaluation categories the existing benchmarks skip.

It is not a novel method. Several teams, some well funded, work on adjacent versions of this problem. The contribution here is measurement and comparison, not discovery.

---

## Prior art

Grouped by how the problem gets framed, because the framing determines what you find.

### Agent memory with bitemporal validity

Well developed, partly commercial. Tracks facts with validity periods rather than documents with versions.

- **Zep / Graphiti** — [arXiv:2501.13956](https://arxiv.org/abs/2501.13956). Temporal knowledge graph for agent memory, validity periods and provenance per fact. Reports 63.8% on LongMemEval
- **[c0](https://github.com/douglasjordan2/c0)** — bi-temporal knowledge graph, transaction time and valid time, hybrid retrieval with reciprocal rank fusion
- **Engram**, **Cognee**, **TOKI** — bi-temporal memory engines and contradiction-resolution algebra

The **bi-temporal data model** from this cluster is the right foundation and is used here. Valid time (when something was true) and transaction time (when the system learned it) are independent, and conflating them makes point-in-time questions unanswerable.

### Versioned documents

Thinner.

- **VersionRAG** — [arXiv:2510.08109](https://arxiv.org/abs/2510.08109), Huwiler & Stockinger. Hierarchical version graph with intent-based query routing. Ships **VersionQA**: 100 questions over 34 versioned technical documents. Reports naive RAG at 58%, GraphRAG at 64%, VersionRAG at 90%
- **TimelyRAG** — [arXiv:2609.11572](https://arxiv.org/abs/2609.11572). Temporal distance in ranking, with TimelyQABench across regulation-heavy domains. Up to +28.6% nDCG@10
- **TEMPO**, and a versioned-corpus benchmark on French tax law
- **[temporal-rag](https://github.com/Emmimal/temporal-rag)** — post-retrieval temporal layer. No datasets, benchmark or evaluation harness

### Legal and contract retrieval

Well covered, and versioning is absent from all of it.

- **[LegalBench-RAG](https://github.com/zeroentropy-ai/legalbenchrag)** — 6,858 query-answer pairs over 79M characters of NDAs, M&A agreements, commercial contracts and privacy policies
- **CUAD**, **ContractEval**, **ACORD** — clause-level review and drafting retrieval

### The gap this targets

LegalBench-RAG does not test versioning. VersionQA does not test agreements, abstention, or the amendment case. The agent-memory work models conversational facts rather than governing documents.

A systematic review of RAG systems puts it plainly: *"Few benchmarks explicitly test temporal reasoning and the ability to prioritize up-to-date information, despite this being crucial for real deployments."*

---

## Evaluation design

| Category | Tests | Correct behaviour |
|---|---|---|
| Simple lookup | Baseline retrieval | Find, answer, cite |
| Supersession | Does it know what governs | Answer from the governing version |
| **Composite** | Base document plus amendment | Combine both. Either alone is wrong |
| Routing | Finding without being told where | Locate it across document types |
| **Point-in-time** | Historical retrieval | "As of date X" returns what governed then |
| **Unanswerable** | Calibration | Abstain, and say so |
| Aggregate | Knowing retrieval's limits | Recognise it as a structured-data question |
| Implicit change | Hardest category | What changed between versions, unprompted |

The three in bold are absent from the benchmarks surveyed above.

**Metrics**: recall@k, precision@k, nDCG@10, answer correctness against ground truth, groundedness, and correct-abstention versus false-abstention rates tracked separately. Indexing cost in tokens and time, since approaches differ by an order of magnitude there. Everything reported per category, because the overall number hides what matters.

---

## Approach

Two kinds of storage, one system. A vector index answers what text *means*; a relational layer holds what a document *is* and how it relates to others. Supersession resolution is then a join rather than a similarity judgement, which is the point: vector search has no concept of one document amending another.

Postgres with pgvector, full-text search for the keyword half of hybrid retrieval, and a bi-temporal document model.

---

## Evaluation corpus

This harness evaluates against **VersionQA**: 100 question and answer pairs over 34 versioned technical documents (Bootstrap release notes, Apache Spark release notes, Node.js `assert` and `errors` documentation across many versions).

Used with the kind permission of Daniel Huwiler, granted by email on 2026-09-23. The underlying documents are obtained from their own public sources under their respective licences.

Using the published set rather than a home-made one means results here are directly comparable to the numbers in the VersionRAG paper, and gives a sanity check on the harness itself: a naive baseline that does not land near the published 58% is measuring the wrong thing.

The three categories VersionQA does not cover — unanswerable questions, composite base-plus-amendment cases, and point-in-time retrieval — are added separately and marked as such.

### Citation

> Daniel Huwiler, Kurt Stockinger, Jonathan Fürst. *VersionRAG: Version-Aware Retrieval-Augmented Generation for Evolving Documents.* arXiv:2510.08109, October 2025.

```bibtex
@misc{huwiler2025versionrag,
  title         = {VersionRAG: Version-Aware Retrieval-Augmented Generation for Evolving Documents},
  author        = {Huwiler, Daniel and Stockinger, Kurt and F{\"u}rst, Jonathan},
  year          = {2025},
  eprint        = {2510.08109},
  archivePrefix = {arXiv},
  url           = {https://arxiv.org/abs/2510.08109},
  note          = {Code and VersionQA benchmark: \url{https://github.com/danielhuwiler/versionrag}}
}
```

---

## Licence

MIT. See [LICENSE](LICENSE).

Prior work referenced above belongs to its respective authors. Where their datasets are used, licence terms and permissions are respected and noted.
