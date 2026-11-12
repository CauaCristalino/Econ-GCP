# Econ-GCP

Pipeline batch diário de indicadores econômicos do Brasil (Selic, IPCA, dólar, IGP-M),
construído no Google Cloud usando só o nível gratuito permanente (Always Free).

Fonte: API SGS do Banco Central → data lake no Cloud Storage → BigQuery
(bronze/silver/gold com dbt) → dashboard no Looker Studio.

## Andamento

| Fase | Entrega | Status |
| --- | --- | --- |
| 0 | Projeto GCP, alerta de orçamento, APIs | pendente |
| 1 | Ingestão local em Python (incremental, retry, testada) | feita |
| 2 | Data lake no GCS e camada bronze no BigQuery | pendente |
| 3 | dbt: staging, marts, testes e docs | pendente |
| 4 | Container, Cloud Run Job e Cloud Scheduler | pendente |
| 5 | Terraform e GitHub Actions | pendente |
| 6 | Dashboard e README de portfólio | pendente |

## Estrutura

```text
ingestion/
├── src/
│   ├── config.py          # séries, URL da API, limites de retry e de janela
│   ├── extract.py         # chamadas à API SGS com retry e carga incremental
│   ├── local_store.py     # grava o JSON bruto no layout particionado
│   ├── logging_config.py  # logs estruturados em JSON
│   └── main.py            # ponto de entrada
├── tests/
├── requirements.txt
└── requirements-dev.txt
pyproject.toml             # configuração do ruff, mypy e pytest
.github/workflows/ci.yml   # lint, tipos e testes em todo PR
```

As pastas `transform/` (dbt) e `infra/` (Terraform) entram nas fases 3 e 5.

## Como rodar a ingestão local

Requer Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r ingestion/requirements-dev.txt
```

Lint, tipos e testes (a partir da raiz):

```bash
ruff check . && ruff format --check . && mypy ingestion/src && pytest
```

Ingestão (a partir de `ingestion/`):

```bash
cd ingestion
python -m src.main
```

O dado bruto vai para `ingestion/data/raw/bcb/serie=<codigo>/ingestion_date=AAAA-MM-DD/dados.json`,
o mesmo layout que o bucket terá na Fase 2. A pasta `data/` não é versionada.

## Decisões da Fase 1

- **Carga incremental:** cada execução pede só do dia seguinte ao último dado já carregado até hoje.
  A primeira execução faz a carga histórica desde 2000, em janelas de até 3650 dias,
  porque a API limita o período das séries diárias.
- **Idempotência:** a "última data carregada" ignora a partição do próprio dia. Rodar duas vezes
  no mesmo dia refaz o mesmo pedido e sobrescreve o mesmo arquivo, sem duplicar nada.
- **Retry com backoff exponencial:** só para falhas passageiras (429, 5xx, timeout, conexão).
  Erros como 400 falham na hora, porque repetir não resolve.
- **Bruto sem transformação:** datas e valores ficam como texto, do jeito que a API devolve.
  A tipagem acontece no dbt, e o original sempre pode ser reprocessado.
- **Falha isolada:** se uma série falha, as outras são carregadas e o processo termina com código 1.
