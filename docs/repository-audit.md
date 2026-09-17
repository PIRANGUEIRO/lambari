# Repository Audit — Lambari

Gerado em 2026-09-16 seguindo Protocolo de Publicação Profissional, Fase 1.

## Inventário

- Linguagem: Python 3.10+
- Arquivos: 5 scripts (1459 linhas)
- Frameworks: nenhum (stdlib + requests, duckdb)
- Banco: DuckDB local, sem servidor
- APIs: OpenCNPJ, Casa dos Dados (RF), ReceitaWS, RD Station
- Infra: sem Docker, sem CI (antes deste commit)
- Testes: nível 0 — sem testes
- Docs: 3 notas no Vault (Anexos), sem README anterior
- Docker/CI/CD/env: ausentes antes; adicionados neste repo

## Classificação

**B — Portfolio Secundário** — problema real, complexidade média-alta, mas sem testes e com código procedural.

## Segurança

- Antes: CLIENT_ID/SECRET hardcoded em 3 arquivos — SANITIZADO para `os.getenv` + `.env.example`
- Verificado: `grep -r fafd3f86 src/` retorna vazio
- .gitignore cobre `.env`, `*.db`, `*.csv`, `*.zip`, tokens

## Qualidade

- Nomes: bons (português descritivo, funções puras)
- Modularidade: procedural, sem classes — aceitável para scripts CLI
- Tipagem: parcial (`typing.Any`, `list[str]`)
- Tratamento de exceção: básico (try em load DuckDB, fetch)
- Código morto: não identificado
- Duplicação: auth flow duplicado entre auth.py e auth_server.py — intencional (manual vs servidor)

## Reprodutibilidade

- `pip install -r requirements.txt` + dependências sistema (curl, funzip, iconv)
- `cp .env.example .env` apenas para auth RD
- `python -m src.buscador_importadores --profile` funciona sem dados RF

## Score (0-5)

Technical Complexity 4, Architecture 2, Code Quality 3, Documentation 4 (após README), Testing 0, Reproducibility 4, Real-world 4, Professional Relevance 3, Demo Value 3 — **médio 3.0** (honesto, sem inflar)
