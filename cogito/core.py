import hashlib
import os
import re
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

from .embed import embed
from .store import Store
from .vault import iter_vault

_DB = os.getenv('COGITO_DB', str(Path(__file__).parent.parent / 'cogito.db'))
_VAULT = os.getenv('VAULT_PATH', str(Path(__file__).parent.parent.parent / 'modelo-cognitivo'))

_MD_HEADING = re.compile(r'^#{1,6}\s+', re.MULTILINE)
_MD_BOLD = re.compile(r'\*{1,3}([^*\n]+)\*{1,3}')
_MD_QUOTE = re.compile(r'^>\s*', re.MULTILINE)
_MD_LIST = re.compile(r'^[-*+]\s+', re.MULTILINE)
_MD_WIKILINK = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]')
_MD_CODE = re.compile(r'`([^`]+)`')
_MD_BLANK = re.compile(r'\n{3,}')

_GRAPH_HOPS = int(os.getenv('COGITO_GRAPH_HOPS', '3'))
_GRAPH_SEEDS = int(os.getenv('COGITO_GRAPH_SEEDS', '5'))


def _store() -> Store:
    return Store(_DB)


def _strip_md(text: str) -> str:
    text = _MD_HEADING.sub('', text)
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_QUOTE.sub('', text)
    text = _MD_LIST.sub('', text)
    text = _MD_WIKILINK.sub(r'\1', text)
    text = _MD_CODE.sub(r'\1', text)
    return _MD_BLANK.sub('\n\n', text).strip()


def _text_for_embed(note: dict) -> str:
    parts = [note['title']]
    if note.get('contexto'):
        parts.append(note['contexto'])
    parts.append(_strip_md(note['body']))
    return '\n\n'.join(p for p in parts if p).strip()


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _semantic_scores(st: Store, query: str) -> list[tuple[str, float]]:
    q_vec = embed([query])[0]
    return sorted(
        [(_id, _cosine(q_vec, vec)) for _id, vec in st.all_vectors()],
        key=lambda x: x[1],
        reverse=True,
    )


def remember(
    text: str,
    *,
    note_id: str | None = None,
    source: str | None = None,
    meta: dict | None = None,
) -> str:
    note_id = note_id or hashlib.sha256(text.encode()).hexdigest()[:16]
    h = hashlib.sha256(text.encode()).hexdigest()
    meta = meta or {}

    st = _store()
    existing_hash = st.get_hash(note_id)

    note = {
        'id': note_id,
        'path': source or '',
        'type': meta.get('type', ''),
        'title': meta.get('title', note_id),
        'body': text,
        'links': [],
        'hash': h,
        'mtime': 0.0,
    }
    st.upsert_note(note)

    if existing_hash != h:
        vec = embed([text])[0]
        st.upsert_vector(note_id, vec)

    st.close()
    return note_id


def recall(query: str, *, mode: str = 'semantic', top_k: int = 5) -> list[dict]:
    st = _store()

    if mode == 'semantic':
        scored = _semantic_scores(st, query)
        results = []
        for note_id, score in scored[:top_k]:
            note = st.get_note(note_id)
            if note:
                results.append({
                    'note_id': note_id,
                    'title': note['title'],
                    'score': round(score, 4),
                    'path': note['path'],
                })
        st.close()
        return results

    if mode == 'graph':
        # 1. semantic seeds (top _GRAPH_SEEDS by cosine)
        scored = _semantic_scores(st, query)
        seeds = [nid for nid, _ in scored[:_GRAPH_SEEDS]]

        # 2. valid note IDs — phantom filter happens here
        valid = st.valid_note_ids()

        # 3. undirected adjacency, skip edges to/from phantoms
        adj: dict[str, set[str]] = defaultdict(set)
        for src, dst, _label in st.all_edges():
            if src in valid and dst in valid:
                adj[src].add(dst)
                adj[dst].add(src)

        # 4. BFS from each seed; accumulate 1/(dist+1) scores
        node_scores: dict[str, float] = defaultdict(float)
        seed_set = set(seeds)

        for seed in seeds:
            if seed not in valid:
                continue
            visited: dict[str, int] = {seed: 0}
            queue: deque[str] = deque([seed])
            while queue:
                node = queue.popleft()
                dist = visited[node]
                node_scores[node] += 1.0 / (dist + 1)
                if dist < _GRAPH_HOPS:
                    for nb in adj.get(node, ()):
                        if nb not in visited:
                            visited[nb] = dist + 1
                            queue.append(nb)

        # 5. rank non-seeds by accumulated score
        ranked = sorted(
            [(nid, sc) for nid, sc in node_scores.items() if nid not in seed_set],
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        results = []
        for note_id, score in ranked:
            note = st.get_note(note_id)
            if note:
                results.append({
                    'note_id': note_id,
                    'title': note['title'],
                    'score': round(score, 4),
                    'path': note['path'],
                })
        st.close()
        return results

    raise ValueError(f"Unknown recall mode: {mode!r}. Valid: 'semantic', 'graph'")


def forget(*, everything: bool = False) -> None:
    st = _store()
    if everything:
        st.clear()
    st.close()


def prune() -> None:
    st = _store()
    st.clear_vectors()
    st.close()


def ingest_vault(path: str | None = None) -> int:
    vault_path = path or _VAULT
    st = _store()

    # First pass: collect all notes to build stem → full-id lookup.
    # Wikilinks use just the stem ("05-resposta-loop"), but IDs are full
    # paths ("etapas/05-resposta-loop"). Phantom targets (templates, _index,
    # etc.) simply won't appear in this map and are silently dropped.
    all_notes = list(iter_vault(vault_path))
    stem_to_id: dict[str, str] = {}
    for note in all_notes:
        stem = note['id'].rsplit('/', 1)[-1]
        stem_to_id[stem] = note['id']
        stem_to_id[note['id']] = note['id']  # full-path wikilinks

    to_embed: list[tuple[str, str]] = []

    for note in all_notes:
        existing_hash = st.get_hash(note['id'])
        st.upsert_note(note)

        # Resolve targets; drop phantoms (targets not in stem_to_id)
        resolved = [
            {'label': e['label'], 'target': stem_to_id[e['target']]}
            for e in note['edges']
            if e['target'] in stem_to_id
        ]
        st.upsert_edges(note['id'], resolved)

        if existing_hash != note['hash']:
            to_embed.append((note['id'], _text_for_embed(note)))

    count = st.conn.execute('SELECT COUNT(*) FROM notes').fetchone()[0]

    if to_embed:
        texts = [t for _, t in to_embed]
        vecs = embed(texts)
        for (note_id, _), vec in zip(to_embed, vecs):
            st.upsert_vector(note_id, vec)

    st.close()
    return count
