from __future__ import annotations

import re

from projmap.schemas import (
    ChunkRecord,
    chunk_id,
    file_hash,
    slugify_heading_path,
)


def extract_heading_events(content: str) -> list[dict]:
    """Parse markdown headings and return events with heading_path."""
    events = []
    stack: list[tuple[int, str]] = []  # (level, title)

    for i, line in enumerate(content.split("\n")):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()

        # Pop deeper levels
        stack = [(lv, t) for lv, t in stack if lv < level]
        stack.append((level, title))

        heading_path = " > ".join(t for _, t in stack)
        # Compute offset: sum of all lines up to this one
        offset = sum(len(l) + 1 for l in content.split("\n")[:i])

        events.append({
            "offset": offset,
            "level": level,
            "title": title,
            "heading_path": heading_path,
        })

    return events


def heading_path_for_offset(heading_events: list[dict], offset: int) -> str | None:
    """Find the heading_path active at a given character offset."""
    active = None
    for ev in heading_events:
        if ev["offset"] <= offset:
            active = ev["heading_path"]
        else:
            break
    return active


def _find_split_point(text: str, max_pos: int) -> int:
    """Try to split at heading or blank line before max_pos."""
    search_start = max(0, max_pos - 2000)
    best = max_pos

    # Look for markdown heading
    for i in range(max_pos, search_start, -1):
        if i < len(text) and text[i] == "#" and (i == 0 or text[i - 1] == "\n"):
            return i

    # Look for blank line
    for i in range(max_pos, search_start, -1):
        if i + 1 < len(text) and text[i] == "\n" and (i == 0 or text[i - 1] == "\n"):
            return i + 1

    return best


def chunk_text(
    content: str,
    file_path: str,
    max_chars: int = 12000,
    overlap_chars: int = 800,
) -> list[ChunkRecord]:
    if not content.strip():
        return []

    heading_events = extract_heading_events(content)

    lines = content.split("\n")
    line_offsets: list[int] = []
    pos = 0
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1  # +1 for \n

    chunks: list[ChunkRecord] = []
    start = 0
    idx = 0

    while start < len(content):
        end = min(start + max_chars, len(content))

        if end < len(content):
            end = _find_split_point(content, end)

        chunk_content = content[start:end].strip()
        if chunk_content:
            # Determine line numbers
            start_line = None
            end_line = None
            for li, off in enumerate(line_offsets):
                if off >= start and start_line is None:
                    start_line = li + 1
                if off <= end:
                    end_line = li + 1

            hp = heading_path_for_offset(heading_events, start)
            sa = slugify_heading_path(hp) or f"chunk-{idx:04d}"
            chash = file_hash(chunk_content)
            chunks.append(ChunkRecord(
                id=chunk_id(file_path, sa, chash),
                file_path=file_path,
                chunk_index=idx,
                heading_path=hp,
                semantic_anchor=sa,
                content=chunk_content,
                content_hash=chash,
                start_line=start_line,
                end_line=end_line,
            ))
            idx += 1

        if end >= len(content):
            break
        start = end - overlap_chars if end - overlap_chars > start else end

    return chunks
