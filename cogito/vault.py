import hashlib
import re
from pathlib import Path
from typing import Iterator

import frontmatter

WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]')
HEADING_RE = re.compile(r'^#{1,6}\s+(.+)', re.MULTILINE)
SECTION_RE = re.compile(r'^#{2,}\s+(.+)')  # H2+ only (H1 = title, not a section label)

SKIP_FILES = {'CLAUDE.md', 'Dashboard.md', '_index.md', 'README.md'}
SKIP_DIRS = {'templates', '.obsidian', '.trash'}


def _extract_edges(body: str) -> list[dict]:
    """Walk body line-by-line; H2+ headings become edge labels."""
    edges = []
    current_label = 'mentions'

    for line in body.splitlines():
        m = SECTION_RE.match(line)
        if m:
            current_label = m.group(1).strip()
        else:
            for target in WIKILINK_RE.findall(line):
                t = target.strip()
                if t:
                    edges.append({'label': current_label, 'target': t})

    return edges


def parse_note(vault_root: Path, md_path: Path) -> dict:
    raw = md_path.read_text(encoding='utf-8')
    post = frontmatter.loads(raw)

    rel = md_path.relative_to(vault_root)
    note_id = str(rel.with_suffix('')).replace('\\', '/')

    meta = dict(post.metadata)
    body = post.content.strip()

    m = HEADING_RE.search(body)
    title = m.group(1).strip() if m else md_path.stem

    # flat links list kept for backward compat (covers full raw doc)
    links = [t.strip() for t in WIKILINK_RE.findall(raw) if t.strip()]

    h = hashlib.sha256(raw.encode()).hexdigest()
    mtime = md_path.stat().st_mtime

    return {
        'id': note_id,
        'path': str(rel).replace('\\', '/'),
        'type': meta.get('type', ''),
        'title': title,
        'body': body,
        'contexto': meta.get('contexto', ''),
        'links': links,
        'edges': _extract_edges(body),  # labeled edges (not stored in notes table)
        'hash': h,
        'mtime': mtime,
    }


def iter_vault(vault_root: str | Path) -> Iterator[dict]:
    root = Path(vault_root)
    for md in sorted(root.rglob('*.md')):
        if md.name in SKIP_FILES:
            continue
        parts = md.relative_to(root).parts
        if any(p in SKIP_DIRS or p.startswith('.') for p in parts[:-1]):
            continue
        yield parse_note(root, md)
