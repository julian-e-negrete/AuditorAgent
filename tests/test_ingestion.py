"""Unit tests for ArchiveIngestionTool (tasks 3.1 and 3.2)."""

from __future__ import annotations

import pytest
from pathlib import Path

from arch_agent.exceptions import IngestionError
from arch_agent.tools.ingestion import ArchiveIngestionTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# My Heading

Some prose text here.

```mermaid
graph TD
    A --> B
```

```python
def hello():
    pass
```

| col1 | col2 |
|------|------|
| a    | b    |

More prose.
"""


@pytest.fixture
def tool():
    return ArchiveIngestionTool()


@pytest.fixture
def md_file(tmp_path):
    f = tmp_path / "sample.md"
    f.write_text(SAMPLE_MD, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# load() — basic parsing
# ---------------------------------------------------------------------------


def test_load_returns_document_context(tool, md_file):
    ctx = tool.load([md_file])
    assert ctx.source_files == ["sample.md"]
    assert "sample.md" in ctx.raw_text


def test_load_raw_text_format(tool, md_file):
    ctx = tool.load([md_file])
    assert ctx.raw_text.startswith("## Source: sample.md\n\n")


def test_load_raw_text_separator_for_multiple_files(tool, tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# A\nContent A", encoding="utf-8")
    b.write_text("# B\nContent B", encoding="utf-8")
    ctx = tool.load([a, b])
    assert "\n\n---\n\n" in ctx.raw_text
    assert ctx.source_files == ["a.md", "b.md"]


def test_load_section_types(tool, md_file):
    ctx = tool.load([md_file])
    types = {s.section_type for s in ctx.sections}
    assert "mermaid" in types
    assert "code" in types
    assert "table" in types
    assert "prose" in types


def test_load_mermaid_section_content(tool, md_file):
    ctx = tool.load([md_file])
    mermaid = [s for s in ctx.sections if s.section_type == "mermaid"]
    assert len(mermaid) == 1
    assert "graph TD" in mermaid[0].content


def test_load_section_heading(tool, md_file):
    ctx = tool.load([md_file])
    # All sections after the first heading should carry "My Heading"
    non_heading_sections = [s for s in ctx.sections if s.content != "# My Heading"]
    for s in non_heading_sections:
        assert s.heading == "My Heading"


def test_load_source_file_basename_only(tool, tmp_path):
    deep = tmp_path / "sub" / "dir"
    deep.mkdir(parents=True)
    f = deep / "doc.md"
    f.write_text("# Hello\nworld", encoding="utf-8")
    ctx = tool.load([f])
    assert ctx.source_files == ["doc.md"]


# ---------------------------------------------------------------------------
# load() — error handling
# ---------------------------------------------------------------------------


def test_load_raises_ingestion_error_for_missing_file(tool, tmp_path):
    missing = tmp_path / "nope.md"
    with pytest.raises(IngestionError) as exc_info:
        tool.load([missing])
    assert "nope.md" in exc_info.value.path


def test_load_raises_before_processing_any_file(tool, tmp_path):
    good = tmp_path / "good.md"
    good.write_text("# Good\nContent", encoding="utf-8")
    missing = tmp_path / "missing.md"
    # missing comes second — error should still be raised, no partial context
    with pytest.raises(IngestionError):
        tool.load([good, missing])


def test_load_raises_ingestion_error_for_non_utf8(tool, tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
    with pytest.raises(IngestionError) as exc_info:
        tool.load([bad])
    assert "bad.md" in exc_info.value.path


# ---------------------------------------------------------------------------
# load() — deduplication
# ---------------------------------------------------------------------------


def test_load_deduplicates_identical_sections(tool, tmp_path):
    content = "# Shared\n\nThis is duplicated content."
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text(content, encoding="utf-8")
    b.write_text(content, encoding="utf-8")
    ctx = tool.load([a, b])
    # The duplicated prose section should appear only once
    prose = [s for s in ctx.sections if s.section_type == "prose" and "duplicated" in s.content]
    assert len(prose) == 1


def test_load_keeps_first_occurrence_on_dedup(tool, tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# A\n\nShared prose.", encoding="utf-8")
    b.write_text("# B\n\nShared prose.", encoding="utf-8")
    ctx = tool.load([a, b])
    shared = [s for s in ctx.sections if "Shared prose" in s.content]
    assert len(shared) == 1
    assert shared[0].source_file == "a.md"


# ---------------------------------------------------------------------------
# load_directory()
# ---------------------------------------------------------------------------


def test_load_directory_discovers_md_files(tool, tmp_path):
    (tmp_path / "one.md").write_text("# One\nContent", encoding="utf-8")
    (tmp_path / "two.md").write_text("# Two\nContent", encoding="utf-8")
    ctx = tool.load_directory(tmp_path)
    assert set(ctx.source_files) == {"one.md", "two.md"}


def test_load_directory_recursive(tool, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "root.md").write_text("# Root", encoding="utf-8")
    (sub / "nested.md").write_text("# Nested", encoding="utf-8")
    ctx = tool.load_directory(tmp_path)
    assert "root.md" in ctx.source_files
    assert "nested.md" in ctx.source_files


def test_load_directory_raises_when_no_md_files(tool, tmp_path):
    (tmp_path / "file.txt").write_text("not markdown", encoding="utf-8")
    with pytest.raises(IngestionError) as exc_info:
        tool.load_directory(tmp_path)
    assert "no .md files found" in exc_info.value.reason


def test_load_directory_custom_glob(tool, tmp_path):
    (tmp_path / "spec.md").write_text("# Spec", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("not md", encoding="utf-8")
    ctx = tool.load_directory(tmp_path, glob="*.md")
    assert ctx.source_files == ["spec.md"]
