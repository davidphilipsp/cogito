"""CLI: cogito [ingest | recall [--graph] <query> | propose ... | apply <id>]"""
import os
import re
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

_WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]')


def _get_flag(args: list[str], flag: str, default: str | None = None) -> str | None:
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
    return default


def _get_all_flags(args: list[str], flag: str) -> list[str]:
    vals = []
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            vals.append(args[i + 1])
    return vals


def _bare_link(raw: str) -> str:
    m = _WIKILINK_RE.match(raw.strip())
    return m.group(1).strip() if m else raw.strip()


def _cmd_propose(args: list[str]) -> None:
    from cogito.writeback import propose, diff, save_proposal

    kind = _get_flag(args, '--kind', 'edit')
    target = _get_flag(args, '--target')
    reason = _get_flag(args, '--reason', '')
    conf = _get_flag(args, '--conf', 'baixa')
    content_flag = _get_flag(args, '--content')
    link_vals = _get_all_flags(args, '--link')

    if not target:
        print("Error: --target is required", file=sys.stderr)
        sys.exit(1)

    if content_flag:
        content = content_flag
        links = [_bare_link(lv) for lv in link_vals]
    elif link_vals:
        items = '\n'.join(f'- {_yaml_quote(v)}' for v in link_vals)
        content = f'relacionado:\n{items}'
        links = [_bare_link(lv) for lv in link_vals]
    else:
        print("Error: --content or --link required", file=sys.stderr)
        sys.exit(1)

    proposal = propose(target, content, kind=kind, reason=reason,
                       confianca=conf, links=links)
    d = diff(proposal)
    print(d if d else '(no changes)')
    proposal_id = save_proposal(proposal)
    print(f'\n[proposal: {proposal_id}]')
    print(f'Run: cogito apply {proposal_id}')


def _yaml_quote(v: str) -> str:
    if any(c in v for c in '#:[]{}|>&*!\'",%@`'):
        return f'"{v}"'
    return v


def _cmd_apply(args: list[str]) -> None:
    from cogito.writeback import load_proposal, apply, diff

    if not args:
        print("Error: proposal_id required", file=sys.stderr)
        sys.exit(1)

    proposal_id = args[0]
    proposal = load_proposal(proposal_id)

    print(diff(proposal))
    print(f'\nProposal: {proposal.id}')
    print(f'Target:   {proposal.target}')
    print(f'Reason:   {proposal.reason}')
    print(f'Conf:     {proposal.confianca}')

    answer = input('\nApply to vault? [y/N] ').strip().lower()
    if answer != 'y':
        print('Aborted.')
        sys.exit(0)

    sha = apply(proposal)
    print(f'\nApplied — vault commit: {sha}')


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: cogito [ingest | recall [--graph] <query> | propose ... | apply <id>]")
        sys.exit(1)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd == 'ingest':
        n = ingest_vault()
        print(f"Indexed {n} notes.")

    elif cmd == 'recall':
        if not rest:
            print("Usage: cogito recall [--graph] <query>")
            sys.exit(1)
        mode = 'semantic'
        if rest[0] == '--graph':
            mode = 'graph'
            rest = rest[1:]
        query = ' '.join(rest)
        results = recall(query, mode=mode, top_k=5)
        if not results:
            print("(no results — run ingest first)" if mode == 'semantic'
                  else "(no graph neighbors found)")
            return
        label = ('semantic' if mode == 'semantic'
                 else f'graph (seeds={os.getenv("COGITO_GRAPH_SEEDS", 5)}, '
                      f'hops={os.getenv("COGITO_GRAPH_HOPS", 3)})')
        print(f"[{label}]")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['score']:.4f}] {r['note_id']}")
            print(f"   {r['title']}")

    elif cmd == 'propose':
        _cmd_propose(rest)

    elif cmd == 'apply':
        _cmd_apply(rest)

    else:
        print(f"Unknown command: {cmd!r}")
        sys.exit(1)


if __name__ == '__main__':
    main()
