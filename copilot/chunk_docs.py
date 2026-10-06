"""Chunk the docs/ corpus into ~500-character titled pieces.

Why chunking? Embedding models have a short attention window and one big
file would blur together. We split on paragraph boundaries, keeping each
piece small (~500 chars) and carrying a `title` (document name + section)
so every chunk can cite itself later.
"""

import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
MAX_CHARS = 500


def _doc_title(text: str, fallback: str) -> str:
    """First markdown H1 of the file, cleaned up."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _section_of(text: str, pos: int) -> str:
    """Nearest H2 heading at or before `pos` (empty if none)."""
    section = ""
    offset = 0
    for line in text.splitlines(keepends=True):
        if offset > pos:
            break
        if line.startswith("## "):
            section = line[3:].strip()
        offset += len(line)
    return section


def chunk_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    title = _doc_title(text, path.stem)

    # Split into paragraphs, keeping blank-line separators attached.
    paragraphs = re.split(r"\n\s*\n", text)

    chunks: list[dict] = []
    current, start_pos = "", 0
    pos = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            pos += len(para) + 2
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if current and len(candidate) > MAX_CHARS:
            # flush current chunk
            section = _section_of(text, start_pos)
            chunks.append({"title": title, "section": section, "content": current})
            current, start_pos = para, pos
        else:
            if not current:
                start_pos = pos
            current = candidate
        pos += len(para) + 2

    if current:
        section = _section_of(text, start_pos)
        chunks.append({"title": title, "section": section, "content": current})

    # Safety net: hard-split anything over ~500 chars, then re-attach
    # orphan fragments (e.g. a lone heading) to the previous chunk.
    final: list[dict] = []
    for c in chunks:
        if len(c["content"]) <= int(MAX_CHARS * 1.1):
            final.append(c)
            continue
        body = c["content"]
        for i in range(0, len(body), MAX_CHARS):
            final.append({**c, "content": body[i : i + MAX_CHARS]})

    merged: list[dict] = []
    for c in final:
        if merged and len(c["content"]) < 80:
            prev = merged[-1]
            joined = f"{prev['content']}\n\n{c['content']}"
            if len(joined) <= int(MAX_CHARS * 1.1):
                prev["content"] = joined
                continue
        merged.append(c)
    return merged


def build_corpus() -> list[dict]:
    all_chunks: list[dict] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        all_chunks.extend(chunk_file(path))
    for i, c in enumerate(all_chunks):
        c["chunk_id"] = i
        # A readable citation label: "Title › Section"
        c["label"] = f"{c['title']} › {c['section']}" if c["section"] else c["title"]
    return all_chunks


if __name__ == "__main__":
    corpus = build_corpus()
    for c in corpus:
        print(f"[{c['chunk_id']:>3}] {len(c['content']):>4} chars  {c['label']}")
    print(f"\nTotal: {len(corpus)} chunks")
