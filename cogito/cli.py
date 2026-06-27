"""Smoke-test CLI: python -m cogito.cli ingest | recall [--graph] <query>"""
import os
import sys
from pathlib import Path

_env = Path(__file__).parent.parent / '.env'
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

from cogito.core import ingest_vault, recall  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m cogito.cli [ingest | recall [--graph] <query>]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'ingest':
        n = ingest_vault()
        print(f"Indexed {n} notes.")

    elif cmd == 'recall':
        args = sys.argv[2:]
        if not args:
            print("Usage: python -m cogito.cli recall [--graph] <query>")
            sys.exit(1)

        mode = 'semantic'
        if args[0] == '--graph':
            mode = 'graph'
            args = args[1:]

        query = ' '.join(args)
        results = recall(query, mode=mode, top_k=5)
        if not results:
            print("(no results — run ingest first)" if mode == 'semantic' else "(no graph neighbors found)")
            return
        label = 'semantic' if mode == 'semantic' else f'graph (seeds={os.getenv("COGITO_GRAPH_SEEDS", 5)}, hops={os.getenv("COGITO_GRAPH_HOPS", 3)})'
        print(f"[{label}]")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['score']:.4f}] {r['note_id']}")
            print(f"   {r['title']}")

    else:
        print(f"Unknown command: {cmd!r}")
        sys.exit(1)


if __name__ == '__main__':
    main()
