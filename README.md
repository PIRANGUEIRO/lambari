# Lambari

[![CI](https://github.com/PIRANGUEIRO/lambari/actions/workflows/ci.yml/badge.svg)](https://github.com/PIRANGUEIRO/lambari/actions) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-MIT-blue)

> Gerador de leads B2B — encontra importadores similares em PR/SC a partir de CNPJs de referência usando dados abertos da Receita Federal + enriquecimento de contatos via crawl.

## Overview

**Problema:** empresas de comércio exterior precisam descobrir novos importadores com perfil similar a clientes existentes, mas as bases públicas da Receita Federal (6.5GB, +50M estabelecimentos) são difíceis de filtrar e os sites das empresas não têm contato estruturado.

**Solução:** pipeline em duas etapas:
1. **Buscador** (`buscador_importadores.py`) — calcula perfil (capital social médio + CNAE) de 3 CNPJs de referência via API mock (api.exemplo.com) e filtra a base RF local (DuckDB) por CNAE 46–50, UF PR/SC, situação ativa e faixa de capital ±70%.
2. **Enriquecimento** (`site_contacts.py`) — crawl paralelo (sitemap + 50 páginas) extrai e-mails, telefones, pessoas, cargos, CNPJ e redes sociais do site de cada lead.

Orquestrado via **n8n workflow** (`bnsuP7NDtBvl8HU9`) exposto como webhook, alimentando o pipeline BotCotation → Google Sheets / RD Station CRM.

## Demo

Interface web demo (Lambari B2B Lead Intelligence):

| Buscador | Extração de Contatos | Pipeline n8n |
|---|---|---|
| ![Buscador](docs/images/buscador.png) | ![Contatos](docs/images/contatos.png) | ![Pipeline](docs/images/pipeline.png) |

> **Interface:** Buscador (3 CNPJs → perfil + Top 15), Extração de Contatos (8 e-mails / 5 telefones / 6 pessoas em 34 páginas), Pipeline n8n (3 → 15 leads via DuckDB).
> Prints em `docs/images/` — modo demo local com dados mock.

```bash
# 1. Perfil apenas (sem baixar 6.5GB) — resposta instantânea
python -m src.buscador_importadores --profile 11378117000120 33000167000101 27865757000102

# 2. Busca rápida (2 arquivos ~1GB)
python -m src.buscador_importadores --shallow 2 11378117000120 33000167000101 27865757000102

# 3. Busca completa (10 arquivos)
python -m src.buscador_importadores 11378117000120 33000167000101 27865757000102

# 4. Enriquecimento de site
python -m src.site_contacts https://exemplo.com.br --json > lead.json
```

Saída do buscador (CLI):
```
======================================================================
  EMPRESAS DE REFERENCIA
======================================================================
1. 11.378.117/0001-20
   Razao: EXEMPLO IMPORTACAO LTDA
   Local: Curitiba/PR
   CNAE:  4693100
   Cap:   R$ 500.000,00

======================================================================
  IMPORTADORES SIMILARES PR/SC (15)
======================================================================
1. 12.345.678/0001-90
   Razao: ALVO LOGISTICA LTDA
   Local: Itajai/SC
   CNAE:  4681805
   Cap:   R$ 420.000,00
```

## Features

- ✅ Perfil automático via OpenCNPJ (sem chave)
- ✅ Filtro streaming da base RF (curl + funzip + grep — não carrega 6.5GB em RAM)
- ✅ Cache local `~/.cache/cnpj_rfb/` com resume (Ctrl+C seguro)
- ✅ DuckDB local com índices para busca sub-segundo
- ✅ Crawl inteligente: sitemap.xml prioritário + 28 caminhos de contato + paralelismo (5 threads)
- ✅ Extração de e-mails, telefones (BR), nomes de pessoas, cargos, CNPJ, LinkedIn/Instagram/Facebook/YouTube/WhatsApp/Telegram
- ✅ Integração n8n via webhook `POST /webhook/buscador-importadores`
- ✅ Modo `--db-url` para usar DuckDB pré-construído (evita download)

## Architecture

```mermaid
flowchart LR
    A[3 CNPJs referência] --> B[API Exemplo<br/>CNPJ_API_URL]
    B --> C{Perfil: capital médio + CNAE top}
    C --> D[(Base RF<br/>api.exemplo.com)]
    D -->|stream grep CNAE 46-50 + UF PR/SC| E[Cache estab_pr_sc.csv]
    D -->|download 10 zips| F[Cache empresas_zips]
    E --> G[DuckDB cnpj.db]
    F --> G
    G -->|faixa cap ±70%| H[Top 15 similares]
    H --> I[site_contacts.py]
    I -->|sitemap + crawl 50 págs| J[Contatos enriquecidos]
    J --> K{n8n Webhook}
    K --> L[Google Sheets / RD CRM]
```

**Componentes:** `src/buscador_importadores.py:121` (perfil), `src/buscador_importadores.py:211` (stream), `src/buscador_importadores.py:268` (DuckDB), `src/buscador_importadores.py:345` (busca), `src/site_contacts.py:544` (crawler), `src/auth/` (OAuth RD Station). Ver `docs/architecture.md` para detalhes.

## Tech Stack

| Camada | Tecnologia | Uso |
|--------|-----------|-----|
| Linguagem | Python 3.10+ | Scripts CLI |
| HTTP | `requests` | OpenCNPJ, download RF |
| DB | `duckdb` | Query local analítica |
| Concorrência | `concurrent.futures.ThreadPoolExecutor` | Downloads + crawl paralelo |
| Infra opcional | n8n + Docker | Orquestração webhook |
| Dados | `api.exemplo.com` (mock) — configurável via `CNPJ_API_URL` / `DADOS_RF_URL` | Fonte |

Apenas tecnologias efetivamente usadas — sem invenção.

> **Nota:** todas as URLs externas são `https://api.exemplo.com` por padrão (mock para portfólio). Aponte `CNPJ_API_URL`, `DADOS_RF_URL`, `OAUTH_DIALOG_URL`/`OAUTH_TOKEN_URL` no `.env` para usar APIs reais.

## Project Structure

```
lambari/
├── src/
│   ├── buscador_importadores.py  # Lead gen por similaridade (CNAE + capital)
│   ├── site_contacts.py          # Crawler de contatos
│   └── auth/
│       ├── auth.py               # OAuth manual (copy URL)
│       ├── auth_server.py        # OAuth com servidor local :8080
│       └── get_token.py          # Teste client_credentials
├── examples/
│   ├── example_output.json       # Saída de exemplo do buscador
│   └── site_contacts_example.json
├── docs/
│   ├── architecture.md
│   └── repository-audit.md
├── .github/workflows/ci.yml
├── .env.example
├── requirements.txt
└── README.md
```

## Installation

```bash
git clone https://github.com/PIRANGUEIRO/lambari.git
cd lambari
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Para auth RD Station (opcional)
cp .env.example .env
# edite .env — já vem com api.exemplo.com mock; aponte para APIs reais se necessário
```

**Dependências de sistema para buscador (Linux):** `curl`, `funzip` (unzip), `iconv`, `grep` — já vêm na maioria das distros. Em macOS: `brew install unzip`.

## Configuration

| Variável | Descrição | Obrigatória |
|----------|-----------|-------------|
| `RD_CLIENT_ID` | Client ID do app RD Station | apenas para `src/auth/*` |
| `RD_CLIENT_SECRET` | Client Secret | apenas para `src/auth/*` |
| `RD_REDIRECT_URL` | Callback URL (ex: `https://exemplo.com/callback` ou `http://localhost:8080/callback`) | apenas para auth |

Nunca commitar `.env` — use `.env.example`.

## Usage

### Buscador de Importadores

```bash
# Perfil instantâneo (sem download)
python -m src.buscador_importadores --profile 11378117000120 33000167000101 27865757000102

# Shallow (rápido, 1 arquivo ~3min)
python -m src.buscador_importadores --shallow 1 11378117000120 33000167000101 27865757000102

# Usando DB pré-construído (se hospedado)
python -m src.buscador_importadores --db-url https://exemplo.com/cnpj.db 11378117000120 33000167000101 27865757000102
```

Critérios de similaridade: `CNAE 46–50` + `UF PR/SC` + `situação 02 (ativa)` + `capital entre 0.3× e 3.0× a média` das referências. Ajuste `CNAE_IMP`, `CAP_MIN_FATOR`, `CAP_MAX_FATOR` e `LIMITE` em `src/buscador_importadores.py:41`.

### Extrator de Contatos

```bash
python -m src.site_contacts https://exemplo.com.br
python -m src.site_contacts exemplo.com.br --json | jq .
python -m src.site_contacts exemplo.com.br --csv > contatos.csv
```

### n8n Webhook

```bash
curl -X POST http://localhost:5678/webhook/buscador-importadores \
  -H "Content-Type: application/json" \
  -d '{"cnpjs": ["11378117000120","33000167000101","27865757000102"]}'
# => {"ok": true, "qtd": 15, "ref": [...], "res": [...]}
```

Workflow ID: `bnsuP7NDtBvl8HU9`. Ver `Anexos/Buscador de Importadores.md` no Vault para estrutura dos nodes.

## API

CLI puro — sem servidor HTTP próprio. A API é o webhook n8n. Ver `Usage > n8n Webhook` e `docs/architecture.md`.

## Testing

Nível atual: **0 — sem testes** (documentado honestamente). Roadmap prevê testes unitários para `limpar_cnpj`, `parse_capital`, `parece_nome_pessoa` e integração para o pipeline DuckDB (ver `docs/repository-audit.md`).

```bash
# Verificação de estilo (CI roda isto)
python -m py_compile src/buscador_importadores.py src/site_contacts.py
```

## Technical Decisions

| Decisão | Motivo | Alternativa | Trade-off |
|---------|--------|-------------|-----------|
| DuckDB local | Query analítica sem servidor, zero-ops | PostgreSQL, SQLite | Requer build local do DB (6.5GB) |
| `curl|funzip|grep` streaming | Filtrar 540MB/arquivo sem RAM | Python `zipfile` puro | Depende de binários Unix |
| `ThreadPoolExecutor(3)` download | Paralelismo controlado | serial | Mais rápido, mas pode sobrecarregar rede |
| `requests` + `urllib` híbrido | `requests` para APIs JSON, `urllib` para crawl sem dependência extra | tudo `requests` | Leve inconsistência |
| `ssl.CERT_NONE` no crawl | Tolerância a sites com cert inválido | falhar | Menos seguro, mais cobertura |
| Cache `~/.cache/cnpj_rfb` | Resume-safe, reutilizável entre execuções | `/tmp` | Ocupa disco até limpeza manual |

## Limitations

- Sem testes automatizados
- `site_contacts` usa heurística de nomes (falso-positivo possível) — ver `RE_NOME`, `PRIMEIROS_NOMES`
- DuckDB precisa ser reconstruído quando a base RF atualiza (`LATEST = 2026-05-10`)
- ReceitaWS (`site_contacts.py:415`) tem rate limit não documentado
- `auth/` exige app registrado no RD Station — secrets nunca commitados
- Buscador foca apenas PR/SC e CNAE 46–50 — generalizar exige parametrização

## Roadmap

- [ ] Parametrizar UF/CNAE/faixa via CLI (`--uf PR,SC --cnae 46-50`)
- [ ] Testes unitários (`pytest`) para parsing e filtros
- [ ] `pyproject.toml` + `ruff` + `mypy`
- [ ] Docker para execução reprodutível sem `curl/funzip`
- [ ] Export JSON/CSV nativo no buscador (hoje só stdout)
- [ ] Normalização de telefone para E.164

## License

MIT — ver `LICENSE`.

## What this project demonstrates

- Python (CLI, stdlib, concorrência, typing)
- Data Engineering (streaming de 6.5GB, DuckDB, ETL)
- Web Scraping / OSINT (sitemap parsing, HTML crawling, regex, heurísticas)
- API Integration (OpenCNPJ, RD Station OAuth, ReceitaWS, n8n webhook)
- System Design (cache, resume, índices, trade-offs documentados)
- Security (env-based secrets, .gitignore, sanitização)
