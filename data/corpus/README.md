# Corpus

34 documents in 4 families, each family a chain of versions of the same thing.

| Family | Versions | Range | Format |
|---|---|---|---|
| `nodejs-assert` | 13 | 11.15.0 → 23.11.0 | Markdown |
| `nodejs-errors` | 9 | 15.14.0 → 23.11.0 | Markdown |
| `bootstrap` | 6 | 5.2.3 → 5.3.5 | Markdown |
| `spark` | 6 | 2.4.7 → 3.5.5 | PDF |

## Why these documents

They contain **real version drift**. Content genuinely changes between versions,
which is what makes version-sensitive questions answerable at all. Concrete
example: Node.js renamed the module from `assert` to `node:assert` partway
along that chain, so a question about the current import form has a different
correct answer depending on which document you read. A retrieval system that
ignores which version it is looking at gets this wrong while sounding certain.

Six of the files are PDFs on purpose. PDF extraction is lossy, and a corpus
made only of clean Markdown would flatter the results.

## Provenance and licences

These are the documents used by the **VersionQA** benchmark, which accompanies
[VersionRAG](https://arxiv.org/abs/2510.08109) (Huwiler, Stockinger, Fürst,
arXiv:2510.08109). Using the same corpus is what makes results here comparable
to the numbers published in that paper.

The documents themselves are third-party and openly licensed:

- **Node.js documentation** — MIT, © Node.js contributors
- **Bootstrap release notes** — MIT, © The Bootstrap Authors
- **Apache Spark release notes** — Apache License 2.0, © The Apache Software Foundation

Each is redistributed here under its own licence. Nothing in this directory is
covered by this repository's MIT licence.

The **question set** is a separate matter: see the Evaluation corpus section of
the top-level README for the permission under which it is used.

## Filenames are structure

The loader parses family and version out of the filename, and an unrecognised
name raises rather than being skipped. That is deliberate: a loader that
silently ignores files it does not understand produces a quietly incomplete
corpus, and every number measured against it is then wrong in a way nobody
notices.

Adding documents means adding a pattern in `src/vre/corpus.py`.
