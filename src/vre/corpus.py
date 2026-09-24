"""Reading the corpus off disk.

Filenames carry the structure. Each document belongs to a family (a thing that
has versions) and has a version within it, and the ordering of those versions
is what becomes the supersedes chain.

Parsing is deliberately strict: an unrecognised filename raises rather than
being skipped. A loader that silently ignores files it does not understand is
how a corpus ends up mysteriously incomplete, and the eval numbers that come
out of it are then wrong in a way nobody notices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus"


@dataclass(frozen=True)
class DocumentSpec:
    """One file, before it reaches the database."""

    path: Path
    family: str        # the thing that has versions, e.g. "nodejs-assert"
    family_title: str  # how to show it to a human
    version: str       # as the source labels it, e.g. "18.20.8"
    doc_type: str

    @property
    def external_id(self) -> str:
        return f"{self.family}@{self.version}"

    @property
    def title(self) -> str:
        return f"{self.family_title} {self.version}"

    @property
    def version_key(self) -> tuple[int, ...]:
        """Numeric tuple for sorting.

        String sorting is wrong here: it puts "11.15.0" before "5.3.1" because
        it compares character by character. Comparing (11, 15, 0) to (5, 3, 1)
        gives the right answer.
        """
        return tuple(int(part) for part in self.version.split("."))


# Each pattern names the family and the version. Order does not matter, the
# patterns are mutually exclusive.
_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"^(?P<module>assert|errors) nodejs (?P<version>[\d.]+)\.md$"),
        "nodejs-{module}",
        "Node.js {module}",
        "api_documentation",
    ),
    (
        re.compile(r"^Release v(?P<version>[\d.]+) · twbs_bootstrap\.md$"),
        "bootstrap",
        "Bootstrap release notes",
        "release_notes",
    ),
    (
        re.compile(r"^Spark Release (?P<version>[\d.]+) _ Apache Spark\.pdf$"),
        "spark",
        "Apache Spark release notes",
        "release_notes",
    ),
]


def parse_filename(path: Path) -> DocumentSpec:
    for pattern, family_template, title_template, doc_type in _PATTERNS:
        match = pattern.match(path.name)
        if match is None:
            continue
        groups = match.groupdict()
        return DocumentSpec(
            path=path,
            family=family_template.format(**groups),
            family_title=title_template.format(**groups),
            version=groups["version"],
            doc_type=doc_type,
        )

    raise ValueError(
        f"Unrecognised corpus filename: {path.name}. "
        "Add a pattern to _PATTERNS rather than skipping it, so the corpus "
        "cannot silently lose documents."
    )


def read_text(path: Path) -> str:
    """Extract text, by file type.

    PDF extraction is lossy and always will be: layout, tables and column order
    are reconstructed by heuristics. It is good enough for release notes, which
    are mostly prose. It would not be good enough for a financial model, and
    that difference is the whole reason ingestion is the hard part of this kind
    of system.
    """
    if path.suffix == ".md":
        return path.read_text(encoding="utf-8")

    if path.suffix == ".pdf":
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    raise ValueError(f"No reader for file type: {path.suffix}")


def discover(directory: Path = CORPUS_DIR) -> list[DocumentSpec]:
    """All documents in the corpus, grouped and ordered within each family."""
    specs = [parse_filename(p) for p in directory.iterdir() if not p.name.startswith(".")]
    return sorted(specs, key=lambda s: (s.family, s.version_key))


def families(specs: list[DocumentSpec]) -> dict[str, list[DocumentSpec]]:
    """Group by family, each list ordered oldest to newest."""
    grouped: dict[str, list[DocumentSpec]] = {}
    for spec in specs:
        grouped.setdefault(spec.family, []).append(spec)
    for versions in grouped.values():
        versions.sort(key=lambda s: s.version_key)
    return grouped
