"""Tests for cogito.writeback (marco 5)."""
import os
import subprocess
from pathlib import Path

import pytest

from cogito.writeback import (
    Proposal,
    _apply_edit,
    _fm_close_index,
    _lint_prescriptive,
    _validate_append_only,
    _yaml_scalar,
    apply,
    diff,
    load_proposal,
    propose,
    save_proposal,
)

VAULT = Path(__file__).parent.parent.parent / 'modelo-cognitivo'
TARGET_BUG = 'bugs/para-antes-de-concluir'
TARGET_ETAPA = 'etapas/01-modelar'

# A clean note without `relacionado`, embedded so tests don't depend on vault state.
_CLEAN_BUG_NOTE = """\
---
type: bug
secao: bugs
categoria: limite
estagio: resposta-loop
prioridade: alta
contexto: "Para um passo antes de concluir — perseverança relativa baixa"
analogo_cerebral: "queda de persistência perto da meta / abandono"
fonte: "6 cenários idiográficos"
confianca: media
data: 2026-06-22
---

# Bug · Para um passo antes de concluir

> Tendência a **largar** perto do fim.

## Onde ocorre
- [[05-resposta-loop]] — no ramo "largar o projeto" do loop.
- Em tensão com [[conscienciosidade]] (alta).
"""

_ETAPA_NOTE = """\
---
type: etapa
secao: pipeline
contexto: "Primeira etapa"
data: 2026-06-22
---

# Etapa 1 · Modelar

Constrói rápido, audita pouco.
"""


# ---------------------------------------------------------------------------
# Pure unit tests (no vault needed)
# ---------------------------------------------------------------------------

MINI_FM = """\
---
type: bug
secao: bugs
data: 2026-06-22
---

# Título

Corpo da nota.
"""


def test_fm_close_index():
    lines = MINI_FM.split('\n')
    # The second --- is at index 4 (0: ---, 1: type, 2: secao, 3: data, 4: ---)
    assert lines[_fm_close_index(lines)] == '---'
    assert _fm_close_index(lines) == 4


def test_apply_edit_new_frontmatter_field():
    result = _apply_edit(MINI_FM, 'relacionado:\n- "[[01-modelar]]"')
    assert 'relacionado:' in result
    assert '- "[[01-modelar]]"' in result
    assert 'type: bug' in result
    assert 'Corpo da nota.' in result


def test_apply_edit_body_fallback():
    result = _apply_edit(MINI_FM, 'Texto adicional sem chave YAML.')
    assert 'Texto adicional' in result
    assert 'type: bug' in result


def test_validate_append_only_pass():
    original = 'linha1\nlinha2\nlinha3\n'
    new = 'linha1\nlinha2\nnova\nlinha3\n'
    _validate_append_only(original, new)  # must not raise


def test_validate_append_only_rejects_replace():
    original = 'linha1\nlinha2\nlinha3\n'
    new = 'linha1\nMODIFICADA\nlinha3\n'
    with pytest.raises(ValueError, match='not append-only'):
        _validate_append_only(original, new)


def test_validate_append_only_rejects_delete():
    original = 'linha1\nlinha2\nlinha3\n'
    new = 'linha1\nlinha3\n'
    with pytest.raises(ValueError, match='not append-only'):
        _validate_append_only(original, new)


def test_lint_prescriptive_clean():
    assert _lint_prescriptive('relacionado:\n- "[[01-modelar]]"') == []


def test_lint_prescriptive_flags_deveria():
    assert _lint_prescriptive('você deveria suprimir mais') != []


def test_lint_prescriptive_flags_maximize():
    assert _lint_prescriptive('maximize a retenção') != []


def test_yaml_scalar_quotes_wikilinks():
    assert _yaml_scalar('[[01-modelar]]') == '"[[01-modelar]]"'


def test_yaml_scalar_plain_string():
    assert _yaml_scalar('etapas') == 'etapas'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vault_root():
    if not VAULT.exists():
        pytest.skip('Vault not found at expected path')
    return VAULT


@pytest.fixture
def temp_vault(tmp_path):
    """Temporary vault with git and clean note content (no prior write-back)."""
    if not VAULT.exists():
        pytest.skip('Vault not found at expected path')

    v = tmp_path / 'vault'
    v.mkdir()
    (v / 'bugs').mkdir()
    (v / 'etapas').mkdir()

    # Write clean, known note content — independent of current vault state.
    (v / 'bugs' / 'para-antes-de-concluir.md').write_text(_CLEAN_BUG_NOTE, encoding='utf-8')
    (v / 'etapas' / '01-modelar.md').write_text(_ETAPA_NOTE, encoding='utf-8')

    subprocess.run(['git', 'init'], cwd=v, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'],
                   cwd=v, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'],
                   cwd=v, check=True, capture_output=True)
    subprocess.run(['git', 'add', '-A'], cwd=v, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=v, check=True, capture_output=True)

    old = os.environ.get('VAULT_PATH')
    os.environ['VAULT_PATH'] = str(v)
    yield v
    if old is not None:
        os.environ['VAULT_PATH'] = old
    else:
        os.environ.pop('VAULT_PATH', None)


# ---------------------------------------------------------------------------
# Integration tests — rejection paths (read-only, use real vault)
# ---------------------------------------------------------------------------

def test_propose_requires_reason(vault_root):
    with pytest.raises(ValueError, match='reason'):
        propose(TARGET_BUG, 'relacionado:\n- "[[01-modelar]]"', reason='')


def test_propose_rejects_prescriptive(vault_root):
    with pytest.raises(ValueError, match='prescriptive'):
        propose(TARGET_BUG, 'você deveria suprimir mais', reason='fonte válida')


def test_propose_rejects_bad_link(vault_root):
    with pytest.raises(ValueError, match='do not resolve'):
        propose(TARGET_BUG, 'relacionado:\n- "[[nota-fantasma]]"',
                reason='fonte', links=['nota-fantasma'])


def test_propose_rejects_nonexistent_target(vault_root):
    with pytest.raises(FileNotFoundError):
        propose('bugs/nota-inexistente', 'algo', reason='fonte')


def test_propose_new_already_exists(vault_root):
    with pytest.raises(FileExistsError):
        propose(TARGET_BUG, 'conteudo novo', kind='new', reason='fonte')


# ---------------------------------------------------------------------------
# Integration tests — happy path (use temp_vault for clean state)
# ---------------------------------------------------------------------------

def test_propose_frontmatter_append(temp_vault):
    p = propose(
        TARGET_BUG,
        'relacionado:\n- "[[01-modelar]]"',
        kind='edit',
        reason='o corpo da nota cita "audita pouco" em 01-modelar',
        confianca='baixa',
        links=['01-modelar'],
    )
    assert isinstance(p, Proposal)
    assert p.target == TARGET_BUG
    assert p.kind == 'edit'
    assert p.confianca == 'baixa'
    assert 'relacionado:' in p.new_content
    assert '- "[[01-modelar]]"' in p.new_content
    # Original lines preserved
    assert 'type: bug' in p.new_content
    assert 'confianca: media' in p.new_content


def test_diff_shows_only_additions(temp_vault):
    p = propose(
        TARGET_BUG,
        'relacionado:\n- "[[01-modelar]]"',
        reason='teste',
        links=['01-modelar'],
    )
    d = diff(p)
    lines = d.splitlines()
    added = [l for l in lines if l.startswith('+') and not l.startswith('+++')]
    removed = [l for l in lines if l.startswith('-') and not l.startswith('---')]
    assert added, 'diff should show additions'
    assert not removed, 'diff must not show removals (append-only)'
    assert any('relacionado' in l for l in added)


def test_propose_append_only_validation_unit():
    """Direct unit test that _validate_append_only rejects modifications."""
    original = 'linha1\nmodificada\n'
    new = 'linha1\nOUTRA\n'
    with pytest.raises(ValueError, match='not append-only'):
        _validate_append_only(original, new)


def test_save_and_load_proposal(temp_vault, tmp_path, monkeypatch):
    import cogito.writeback as wb
    monkeypatch.setattr(wb, '_PROPOSALS_DIR', tmp_path / '.proposals')

    p = propose(
        TARGET_BUG,
        'relacionado:\n- "[[01-modelar]]"',
        reason='teste persistência',
        links=['01-modelar'],
    )
    pid = save_proposal(p)
    loaded = load_proposal(pid)
    assert loaded.id == p.id
    assert loaded.target == p.target
    assert loaded.reason == p.reason


def test_apply_writes_file_and_commits(temp_vault):
    p = propose(
        TARGET_BUG,
        'relacionado:\n- "[[01-modelar]]"',
        reason='o corpo da nota cita "audita pouco" em 01-modelar',
        confianca='baixa',
        links=['01-modelar'],
    )
    sha = apply(p)

    # File was written
    note_path = temp_vault / 'bugs' / 'para-antes-de-concluir.md'
    content = note_path.read_text(encoding='utf-8')
    assert 'relacionado:' in content
    assert '- "[[01-modelar]]"' in content

    # Commit exists in vault repo
    result = subprocess.run(
        ['git', 'log', '--oneline', '-1'],
        cwd=temp_vault, capture_output=True, text=True, check=True,
    )
    assert sha[:7] in result.stdout
    assert 'write-back' in result.stdout
