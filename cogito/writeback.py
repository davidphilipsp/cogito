"""Marco 5 — write-back: propose → diff → human gate → apply (git commit in vault).

Edit is append-only: adds frontmatter fields or body sections, never replaces.
apply() only runs after explicit human confirmation.
"""
import difflib
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

_PRESCRIPTIVE_RE = re.compile(
    r'(?:você deveria|deveria|maximize|otimize|suprima|amplifique|você deve|'
    r'reforce a supressão|reforce|\bshould maximize\b)',
    re.IGNORECASE,
)
_WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]')

VALID_KINDS = frozenset({'edit', 'new', 'claude_md'})
_COGITO_DIR = Path(__file__).parent.parent
_PROPOSALS_DIR = _COGITO_DIR / '.proposals'


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Proposal:
    id: str
    target: str
    kind: str
    content: str
    reason: str
    confianca: str
    links: list[str]
    file_path: str    # str for JSON round-trip
    original: str
    new_content: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vault_root() -> Path:
    return Path(os.getenv('VAULT_PATH',
                          str(Path(__file__).parent.parent.parent / 'modelo-cognitivo')))


def _stem_to_id() -> dict[str, str]:
    from .vault import iter_vault
    mapping: dict[str, str] = {}
    for note in iter_vault(_vault_root()):
        stem = note['id'].rsplit('/', 1)[-1]
        mapping[stem] = note['id']
        mapping[note['id']] = note['id']
    return mapping


def _bare_link(raw: str) -> str:
    m = _WIKILINK_RE.match(raw.strip())
    return m.group(1).strip() if m else raw.strip()


def _resolve_link(raw: str, s2id: dict[str, str]) -> str | None:
    return s2id.get(_bare_link(raw))


def _lint_prescriptive(text: str) -> list[str]:
    return [m.group(0) for m in _PRESCRIPTIVE_RE.finditer(text)]


def _yaml_scalar(v: Any) -> str:
    if isinstance(v, str) and any(c in v for c in '#:[]{}|>&*!\'",%@`'):
        escaped = v.replace('"', '\\"')
        return f'"{escaped}"'
    return str(v)


def _format_yaml_list_field(field_name: str, values: list) -> str:
    lines = [f'{field_name}:'] + [f'- {_yaml_scalar(v)}' for v in values]
    return '\n'.join(lines)


def _fm_close_index(lines: list[str]) -> int:
    """Return index of the second '---' (frontmatter close). Raises if not found."""
    count = 0
    for i, line in enumerate(lines):
        if line.rstrip() == '---':
            count += 1
            if count == 2:
                return i
    raise ValueError("No frontmatter found (expected opening and closing ---)")


def _insert_frontmatter_field(original: str, field_name: str, value: Any) -> str:
    """Surgically insert / extend a frontmatter field (append-only)."""
    import frontmatter as fm
    lines = original.split('\n')
    fm_close = _fm_close_index(lines)
    post = fm.loads(original)
    existing = post.metadata.get(field_name)

    if existing is not None:
        if not isinstance(existing, list):
            raise ValueError(
                f"kind='edit' rejected: field {field_name!r} exists and is not a list"
            )
        new_vals = value if isinstance(value, list) else [value]
        to_add = [v for v in new_vals if v not in existing]
        if not to_add:
            raise ValueError(f"All values already present in {field_name!r} — nothing to add")
        # Append items to the list block inside the frontmatter.
        # Find where the field block ends (first non-list line after the key).
        in_field = False
        last_field_line = fm_close - 1
        for i in range(1, fm_close):
            if lines[i].startswith(field_name + ':'):
                in_field = True
                last_field_line = i
            elif in_field:
                if lines[i].startswith('- ') or lines[i].startswith('  '):
                    last_field_line = i
                else:
                    break
        insert_lines = [f'- {_yaml_scalar(v)}' for v in to_add]
        new_lines = lines[:last_field_line + 1] + insert_lines + lines[last_field_line + 1:]
    else:
        yaml_text = _format_yaml_list_field(field_name, value if isinstance(value, list) else [value])
        insert_lines = yaml_text.split('\n')
        new_lines = lines[:fm_close] + insert_lines + lines[fm_close:]

    return '\n'.join(new_lines)


def _apply_edit(original: str, content: str) -> str:
    """Apply append-only edit. Tries frontmatter field insertion first."""
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        parsed = None

    if isinstance(parsed, dict) and len(parsed) == 1:
        field_name, value = next(iter(parsed.items()))
        return _insert_frontmatter_field(original, field_name, value)

    # Fallback: body append
    return original.rstrip('\n') + '\n\n' + content.strip() + '\n'


def _validate_append_only(original: str, new_content: str) -> None:
    """Raise if new_content modifies or deletes any line from original."""
    orig_lines = original.splitlines()
    new_lines = new_content.splitlines()
    matcher = difflib.SequenceMatcher(None, orig_lines, new_lines, autojunk=False)
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ('replace', 'delete'):
            changed = orig_lines[i1:i2]
            raise ValueError(
                f"kind='edit' is not append-only: existing lines modified/deleted: {changed!r}"
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def propose(
    target: str,
    content: str,
    *,
    kind: str = 'edit',
    reason: str,
    confianca: str = 'baixa',
    links: list[str] | None = None,
) -> Proposal:
    """Validate and build a Proposal. Does NOT write anything."""
    if not reason or not reason.strip():
        raise ValueError("reason is required — propose rejected: no source given")

    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {set(VALID_KINDS)}, got {kind!r}")

    flagged = _lint_prescriptive(content)
    if flagged:
        raise ValueError(f"Content flagged as prescriptive/amplification: {flagged!r}")

    links = list(links or [])
    s2id = _stem_to_id()
    bad = [lnk for lnk in links if _resolve_link(lnk, s2id) is None]
    if bad:
        raise ValueError(f"Links do not resolve to real notes: {bad!r}")

    vault = _vault_root()
    if kind == 'claude_md':
        file_path = vault / 'CLAUDE.md'
    else:
        file_path = vault / f'{target}.md'

    if kind in ('edit', 'claude_md'):
        if not file_path.exists():
            raise FileNotFoundError(f"Target not found: {file_path}")
        original = file_path.read_text(encoding='utf-8')
        new_content = _apply_edit(original, content)
        _validate_append_only(original, new_content)
    else:  # kind == 'new'
        if file_path.exists():
            raise FileExistsError(f"Note already exists: {file_path} — use kind='edit' to append")
        original = ''
        new_content = content.strip() + '\n'

    proposal_id = hashlib.sha256(
        f'{target}|{kind}|{content}|{reason}'.encode()
    ).hexdigest()[:12]

    return Proposal(
        id=proposal_id,
        target=target,
        kind=kind,
        content=content,
        reason=reason,
        confianca=confianca,
        links=links,
        file_path=str(file_path),
        original=original,
        new_content=new_content,
    )


def diff(proposal: Proposal) -> str:
    """Return unified diff string for human review."""
    vault = _vault_root()
    rel = str(Path(proposal.file_path).relative_to(vault))
    from_file = '/dev/null' if proposal.kind == 'new' else f'a/{rel}'
    to_file = f'b/{rel}'
    orig = proposal.original.splitlines(keepends=True)
    new = proposal.new_content.splitlines(keepends=True)
    return ''.join(difflib.unified_diff(orig, new, fromfile=from_file, tofile=to_file))


def apply(proposal: Proposal) -> str:
    """Write file and git commit in the vault. Returns commit SHA."""
    file_path = Path(proposal.file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(proposal.new_content, encoding='utf-8')

    vault = _vault_root()
    rel = str(file_path.relative_to(vault))
    commit_msg = (
        f'cogito: write-back — {proposal.target}\n\n'
        f'kind: {proposal.kind}\n'
        f'reason: {proposal.reason}\n'
        f'confianca: {proposal.confianca}\n'
        f'proposal_id: {proposal.id}'
    )
    subprocess.run(['git', 'add', rel], cwd=str(vault), check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', commit_msg], cwd=str(vault), check=True,
                   capture_output=True)
    sha = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=str(vault), capture_output=True, text=True, check=True,
    ).stdout.strip()
    return sha


# ---------------------------------------------------------------------------
# Proposal persistence (for CLI round-trip)
# ---------------------------------------------------------------------------

def save_proposal(proposal: Proposal) -> str:
    _PROPOSALS_DIR.mkdir(exist_ok=True)
    path = _PROPOSALS_DIR / f'{proposal.id}.json'
    path.write_text(json.dumps(asdict(proposal), indent=2, ensure_ascii=False), encoding='utf-8')
    return proposal.id


def load_proposal(proposal_id: str) -> Proposal:
    path = _PROPOSALS_DIR / f'{proposal_id}.json'
    if not path.exists():
        raise FileNotFoundError(
            f"Proposal not found: {proposal_id!r}. Run 'cogito propose' first."
        )
    data = json.loads(path.read_text(encoding='utf-8'))
    return Proposal(**data)
