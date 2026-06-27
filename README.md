# cogito

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
