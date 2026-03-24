"""ArchiveIngestionTool — loads and parses local Markdown files into a DocumentContext."""

from __future__ import annotations

import re
from pathlib import Path

from arch_agent.exceptions import IngestionError
from arch_agent.models.documents import DocumentContext, DocumentSection


# ---------------------------------------------------------------------------
# Markdown parser helpers
# ---------------------------------------------------------------------------

_ATX_HEADING = re.compile(r"^#{1,3}\s+(.*)")
_FENCED_OPEN = re.compile(r"^(`{3,}|~{3,})(\w*)")


def _parse_sections(text: str, source_file: str) -> list[DocumentSection]:
    """Parse *text* into typed DocumentSection objects.

    Section types (in priority order):
    - "mermaid"  — fenced block whose info-string starts with "mermaid"
    - "code"     — any other fenced block (``` or ~~~)
    - "table"    — consecutive lines starting with "|"
    - "prose"    — everything else
    """
    sections: list[DocumentSection] = []
    lines = text.splitlines(keepends=True)
    current_heading = ""
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")

        # Track ATX headings (# / ## / ###)
        heading_match = _ATX_HEADING.match(stripped)
        if heading_match:
            current_heading = heading_match.group(1).strip()
            # Headings themselves become prose
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    content=stripped,
                    section_type="prose",
                    source_file=source_file,
                )
            )
            i += 1
            continue

        # Fenced code / mermaid block
        fence_match = _FENCED_OPEN.match(stripped)
        if fence_match:
            fence_char = fence_match.group(1)
            info_string = fence_match.group(2).lower()
            block_lines = [line]
            i += 1
            # Closing fence: same fence character, same or longer length, no info string
            close_pattern = re.compile(
                r"^" + re.escape(fence_char[0]) + r"{" + str(len(fence_char)) + r",}\s*$"
            )
            while i < len(lines):
                block_lines.append(lines[i])
                close_stripped = lines[i].rstrip("\n")
                if close_pattern.match(close_stripped):
                    i += 1
                    break
                i += 1
            content = "".join(block_lines).rstrip("\n")
            section_type = "mermaid" if info_string == "mermaid" else "code"
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    content=content,
                    section_type=section_type,
                    source_file=source_file,
                )
            )
            continue

        # Table: consecutive lines starting with "|"
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].rstrip("\n").startswith("|"):
                table_lines.append(lines[i])
                i += 1
            content = "".join(table_lines).rstrip("\n")
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    content=content,
                    section_type="table",
                    source_file=source_file,
                )
            )
            continue

        # Prose: accumulate until next structural element
        prose_lines = []
        while i < len(lines):
            l = lines[i]
            s = l.rstrip("\n")
            if _ATX_HEADING.match(s) or _FENCED_OPEN.match(s) or s.startswith("|"):
                break
            prose_lines.append(l)
            i += 1
        content = "".join(prose_lines).rstrip("\n")
        if content.strip():
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    content=content,
                    section_type="prose",
                    source_file=source_file,
                )
            )

    return sections


# ---------------------------------------------------------------------------
# ArchiveIngestionTool
# ---------------------------------------------------------------------------


class ArchiveIngestionTool:
    """Loads local Markdown files into a structured DocumentContext."""

    # ------------------------------------------------------------------
    # Task 3.1 — load()
    # ------------------------------------------------------------------

    def load(self, paths: list[Path]) -> DocumentContext:
        """Read each path as UTF-8 and return a DocumentContext.

        Raises IngestionError immediately (before any processing) if any
        path is missing or unreadable.  If an error is raised, no partial
        context is stored.
        """
        # --- Phase 1: validate ALL paths before touching any content ---
        file_texts: list[tuple[Path, str]] = []
        for path in paths:
            if not path.exists():
                raise IngestionError(str(path), "file not found")
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise IngestionError(str(path), str(exc)) from exc
            file_texts.append((path, text))

        # --- Phase 2: parse and deduplicate ---
        all_sections: list[DocumentSection] = []
        seen_contents: set[str] = set()
        raw_parts: list[str] = []

        for path, text in file_texts:
            basename = Path(path).name
            sections = _parse_sections(text, source_file=basename)
            for section in sections:
                if section.content not in seen_contents:
                    seen_contents.add(section.content)
                    all_sections.append(section)
            raw_parts.append(f"## Source: {basename}\n\n{text}")

        raw_text = "\n\n---\n\n".join(raw_parts)
        source_files = [Path(p).name for p in paths]

        return DocumentContext(
            sections=all_sections,
            raw_text=raw_text,
            source_files=source_files,
        )

    # ------------------------------------------------------------------
    # Task 3.2 — load_directory()
    # ------------------------------------------------------------------

    def load_directory(self, root: Path, glob: str = "**/*.md") -> DocumentContext:
        """Discover all Markdown files under *root* and delegate to load().

        Raises IngestionError if no files match the glob pattern.
        """
        matched = sorted(root.glob(glob))
        if not matched:
            raise IngestionError(str(root), "no .md files found")
        return self.load(matched)
