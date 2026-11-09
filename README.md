# cogito

Local retrieval engine for a Markdown / Obsidian knowledge base: hybrid **semantic + graph** recall, with **human-gated, append-only** write-back.

*Versão em português abaixo.*

## Why

Embedding search finds notes that *sound* like the query. It misses notes that are only *connected* to them. cogito combines both: it takes the top semantic hits as seeds and expands through the typed link graph the author already wrote, then re-ranks by graph proximity.

## How it works

| Stage | What it does |
|---|---|
| **Ingest** | Parses Markdown + YAML frontmatter; extracts typed edges from `[[wikilinks]]`, labelled by the H2 section they appear in. Content hashes skip unchanged notes on re-index. |
| **Semantic recall** | Local embeddings via fastembed (`all-MiniLM-L6-v2`), stored in SQLite, ranked by cosine similarity. No API calls, no data leaves the machine. |
| **Graph recall** | Top-N semantic hits become seeds (default 5); BFS over the link graph (default 3 hops); results scored by proximity to the seeds. Both are configurable via env. |
| **Write-back** | The system may only *propose* edits: a new frontmatter field or a new body section. Every proposal is validated as append-only, shown as a diff, and committed to the vault's Git repo only after a human confirms. |

## Design choices

- **Local first.** Embeddings and index run on the machine; the vault never goes to a third-party API.
- **The model never rewrites the author's text.** Append-only validation rejects any proposal that changes or deletes existing content.
- **Human gate before any write.** `cogito apply` asks for confirmation, then commits, so every change is reviewable and revertible in Git.
- **Confidence is explicit.** Proposals carry a reason and a confidence level.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set VAULT_PATH
cogito ingest                 # index the vault
cogito recall "query"         # semantic recall
cogito recall --graph "query" # semantic seeds + graph expansion
pytest                        # test suite (vault parsing, write-back rules)
```

Stack: Python 3.11 · fastembed · NumPy · SQLite · python-frontmatter · pytest.

---

## Português

Motor de memória semântica para um vault Obsidian de modelo cognitivo pessoal.

## O que faz

- **Ingest** — parseia notas Markdown com frontmatter, extrai arestas tipadas (`[[wikilinks]]` por seção H2) e indexa embeddings locais via fastembed.
- **Recall semântico** — busca por similaridade coseno nos embeddings.
- **Recall graph** — BFS a partir de seeds semânticos, pontuação por proximidade no grafo de links.
- **Write-back** — propõe edições append-only ao vault (novo campo no frontmatter, nova seção no corpo), exibe diff, aguarda confirmação humana e commita no repo do vault.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # configure VAULT_PATH
```

## Uso

```bash
cogito ingest                                  # indexa o vault
cogito recall "largar perto do fim"            # recall semântico
cogito recall --graph "largar perto do fim"    # recall por grafo

# write-back (marco 5)
cogito propose --kind edit \
  --target bugs/para-antes-de-concluir \
  --link "[[01-modelar]]" \
  --reason "o corpo cita 'audita pouco' em 01-modelar" \
  --conf baixa

cogito apply <proposal_id>                     # pede confirmação antes de commitar
```

## Testes

```bash
pytest
```

## Marcos

| Marco | Descrição |
|---|---|
| 1 | Parser de vault + frontmatter + wikilinks |
| 2 | Recall semântico (fastembed + SQLite) |
| 3 | Grafo tipado — arestas com rótulo H2 + recall graph |
| 5 | Write-back append-only com gate humano |
