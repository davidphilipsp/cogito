import hashlib
import os
import re
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
    if mode == 'graph':
        raise NotImplementedError("recall(mode='graph') — Marco 3 (arestas parseadas estão em store.notes.links_json)")

    st = _store()
    q_vec = embed([query])[0]
    all_vecs = st.all_vectors()

    if not all_vecs:
        st.close()
        return []

    scored = sorted(
        [(nid, _cosine(q_vec, vec)) for nid, vec in all_vecs],
        key=lambda x: x[1],
        reverse=True,
    )

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

    to_embed: list[tuple[str, str]] = []

    for note in iter_vault(vault_path):
        existing_hash = st.get_hash(note['id'])
        st.upsert_note(note)
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
