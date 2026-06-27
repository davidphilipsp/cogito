from pathlib import Path

import pytest

from cogito.vault import parse_note, iter_vault, _extract_edges

VAULT = Path(__file__).parent.parent.parent / 'modelo-cognitivo'


@pytest.fixture
def vault_root():
    if not VAULT.exists():
        pytest.skip("Vault not found at expected path")
    return VAULT


# --- parser ---

def test_parse_id_and_type(vault_root):
    md = vault_root / 'bugs' / 'para-antes-de-concluir.md'
    note = parse_note(vault_root, md)
    assert note['id'] == 'bugs/para-antes-de-concluir'
    assert note['type'] == 'bug'


def test_parse_title(vault_root):
    md = vault_root / 'bugs' / 'para-antes-de-concluir.md'
    note = parse_note(vault_root, md)
    assert 'Para um passo antes de concluir' in note['title']


def test_parse_hash_and_body(vault_root):
    md = vault_root / 'bugs' / 'para-antes-de-concluir.md'
    note = parse_note(vault_root, md)
    assert len(note['hash']) == 64
    assert 'largar' in note['body']


# --- flat links (backward compat) ---

def test_links_parsed(vault_root):
    md = vault_root / 'bugs' / 'para-antes-de-concluir.md'
    note = parse_note(vault_root, md)
    assert '05-resposta-loop' in note['links']
    assert 'conscienciosidade' in note['links']


# --- labeled edges ---

def test_edges_have_labels(vault_root):
    md = vault_root / 'bugs' / 'para-antes-de-concluir.md'
    note = parse_note(vault_root, md)
    edges = {(e['label'], e['target']) for e in note['edges']}
    assert ('Onde ocorre', '05-resposta-loop') in edges
    assert ('Onde ocorre', 'conscienciosidade') in edges


def test_edges_etapa_disciplinas(vault_root):
    md = vault_root / 'etapas' / '01-modelar.md'
    note = parse_note(vault_root, md)
    edges = {(e['label'], e['target']) for e in note['edges']}
    assert ('Disciplinas', 'cerebro-bayesiano') in edges
    assert ('Disciplinas', 'model-builder') in edges
    assert ('Enviesada por', 'abertura') in edges
    assert ('Próxima etapa', '02-lentes') in edges


def test_edges_conceito_mapeia(vault_root):
    md = vault_root / 'conceitos-software' / 'model-builder.md'
    note = parse_note(vault_root, md)
    edges = {(e['label'], e['target']) for e in note['edges']}
    assert ('Mapeia para', '01-modelar') in edges


def test_edges_no_phantom_h1_label(vault_root):
    """H1 title should never become an edge label."""
    md = vault_root / 'etapas' / '01-modelar.md'
    note = parse_note(vault_root, md)
    labels = {e['label'] for e in note['edges']}
    assert 'Etapa 1 · Modelar' not in labels


def test_extract_edges_unit():
    body = """# Título

## Disciplinas
- [[cerebro-bayesiano]]
- [[model-builder]]

## Enviesada por
[[abertura]] e [[conscienciosidade]]

## Sem links
Texto sem wikilink.
"""
    edges = _extract_edges(body)
    assert {'label': 'Disciplinas', 'target': 'cerebro-bayesiano'} in edges
    assert {'label': 'Disciplinas', 'target': 'model-builder'} in edges
    assert {'label': 'Enviesada por', 'target': 'abertura'} in edges
    assert {'label': 'Enviesada por', 'target': 'conscienciosidade'} in edges
    # H1 line [[links]] would be labelled 'mentions' (no H1 in this body though)
    labels = {e['label'] for e in edges}
    assert 'Título' not in labels


# --- iter_vault ---

def test_iter_vault_finds_notes(vault_root):
    notes = list(iter_vault(vault_root))
    ids = {n['id'] for n in notes}
    assert 'bugs/para-antes-de-concluir' in ids
    assert 'bugs/nucleo-sangra' in ids
    assert 'etapas/01-modelar' in ids
    assert 'lentes/tempo-sobre-emocao' in ids
    assert 'tracos/abertura' in ids


def test_iter_vault_skips_system_files(vault_root):
    notes = list(iter_vault(vault_root))
    ids = {n['id'] for n in notes}
    assert 'CLAUDE' not in ids
    assert 'Dashboard' not in ids
    assert '_index' not in ids


def test_iter_vault_skips_templates(vault_root):
    notes = list(iter_vault(vault_root))
    ids = {n['id'] for n in notes}
    assert not any(i.startswith('templates/') for i in ids)


def test_iter_vault_count(vault_root):
    notes = list(iter_vault(vault_root))
    assert len(notes) >= 30
