import json
import sqlite3
from pathlib import Path

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id        TEXT PRIMARY KEY,
    path      TEXT,
    type      TEXT,
    title     TEXT,
    body      TEXT,
    links_json TEXT,
    hash      TEXT,
    mtime     REAL
);
CREATE TABLE IF NOT EXISTS vectors (
    note_id TEXT PRIMARY KEY,
    dim     INTEGER,
    vec     BLOB
);
"""


class Store:
    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # --- notes ---

    def get_hash(self, note_id: str) -> str | None:
        row = self.conn.execute(
            'SELECT hash FROM notes WHERE id = ?', (note_id,)
        ).fetchone()
        return row[0] if row else None

    def upsert_note(self, note: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO notes
               (id, path, type, title, body, links_json, hash, mtime)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                note['id'], note['path'], note['type'], note['title'],
                note['body'], json.dumps(note['links']), note['hash'], note['mtime'],
            ),
        )
        self.conn.commit()

    def get_note(self, note_id: str) -> dict | None:
        row = self.conn.execute(
            'SELECT id, path, type, title, body, links_json, hash, mtime FROM notes WHERE id = ?',
            (note_id,),
        ).fetchone()
        if not row:
            return None
        return {
            'id': row[0], 'path': row[1], 'type': row[2], 'title': row[3],
            'body': row[4], 'links': json.loads(row[5]), 'hash': row[6], 'mtime': row[7],
        }

    # --- vectors ---

    def upsert_vector(self, note_id: str, vec: np.ndarray) -> None:
        blob = vec.astype(np.float32).tobytes()
        self.conn.execute(
            'INSERT OR REPLACE INTO vectors (note_id, dim, vec) VALUES (?, ?, ?)',
            (note_id, len(vec), blob),
        )
        self.conn.commit()

    def all_vectors(self) -> list[tuple[str, np.ndarray]]:
        rows = self.conn.execute('SELECT note_id, dim, vec FROM vectors').fetchall()
        return [(r[0], np.frombuffer(r[2], dtype=np.float32)) for r in rows]

    # --- maintenance ---

    def clear(self) -> None:
        self.conn.executescript('DELETE FROM notes; DELETE FROM vectors;')
        self.conn.commit()

    def clear_vectors(self) -> None:
        self.conn.execute('DELETE FROM vectors')
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
