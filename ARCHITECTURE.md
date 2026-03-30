# Diagrama de Arquitetura — MLOps Challenge

Visualização do fluxo end-to-end do sistema, desde o disparo do pipeline até o serving do modelo em produção.

---

## Fluxo end-to-end

```mermaid
flowchart TD
    subgraph CI["CI/CD — GitHub Actions"]
        lint[Lint\nruff + black]
        test[Test\npytest]
        build[Build & Publish\nGHCR]
        lint --> test --> build
    end

    subgraph trigger["Disparo do Pipeline"]
        webhook[POST /webhook/start-pipeline]
    end

    subgraph n8n_flow["Orquestração — n8n"]
        prepare[Prepare Dataset\ndocker compose --profile prepare]
        train[Train Model\ndocker compose --profile train]
        extract[Extract run_id\nparse stdout JSON]
        validate[Validate\npipeline/validate.py]
        publish[Publish\npipeline/publish.py]
        deploy[Deploy\nPOST /reload]

        prepare --> train --> extract --> validate --> publish --> deploy

        prepare -- erro --> fail[Notify Failure]
        train -- erro --> fail
        extract -- erro --> fail
        validate -- erro --> fail
        publish -- erro --> fail
        deploy -- erro --> fail
        deploy -- sucesso --> success[Notify Success]
    end

    subgraph artifacts["Artefatos — Volume compartilhado"]
        raw["artifacts/<run_id>/\nsaved_model + metrics.json + metadata.json"]
        published["artifacts/published/<run_id>/\nfonte de verdade do serving"]
        raw --> published
    end

    subgraph serving["Serving"]
        gateway["NGINX Gateway\nAutenticação X-API-Key\nRate Limit 10r/s por chave\nLog JSON estruturado"]
        api["FastAPI\n/predict /health /model /reload /metrics"]
        gateway --> api
    end

    subgraph observability["Observabilidade"]
        prometheus[Prometheus\nscrape /metrics]
        grafana[Grafana\nDashboard PromQL]
        prometheus --> grafana
    end

    webhook --> prepare
    publish --> published
    deploy --> api
    api --> prometheus
    client([Cliente HTTP]) --> gateway
```

---

## Serviços Docker Compose

| Serviço | Imagem | Função |
|---|---|---|
| `api` | `Dockerfile` | FastAPI — serving do modelo |
| `gateway` | `nginx:alpine` | NGINX — controle de acesso |
| `n8n` | `n8n/Dockerfile` (custom) | Orquestrador do pipeline |
| `prometheus` | `prom/prometheus` | Coleta de métricas |
| `grafana` | `grafana/grafana` | Visualização de métricas |
| `prepare` *(profile)* | `Dockerfile` | Executa `ml/prepare_dataset.py` |
| `train` *(profile)* | `Dockerfile` | Executa `ml/train.py` |

---

## Pipeline ML — etapas e contratos

```
Webhook
  │  parâmetros: epochs, batch_size, threshold, train_records, val_records
  ▼
Prepare Dataset
  │  saída: data/processed/ (TFRecords + prepared_dataset.json)
  ▼
Train Model
  │  saída: artifacts/<run_id>/ (saved_model + metrics.json + metadata.json)
  │  stdout (última linha): JSON com run_id, status, metric_value
  ▼
Extract run_id
  │  lê stdout do treino, propaga run_id, threshold, git_sha para etapas seguintes
  ▼
Validate
  │  lê artifacts/<run_id>/metrics.json
  │  exit 0 se val_token_accuracy >= threshold, exit 1 caso contrário
  │  (exit 1 → Notify Failure, pipeline interrompido)
  ▼
Publish
  │  copia artifacts/<run_id>/ → artifacts/published/<run_id>/
  │  grava metadata.json com provenance (git_sha, published_at, métricas)
  ▼
Deploy
     POST http://api:8000/reload { run_id }
     API carrega artifacts/published/<run_id>/saved_model
```

---

## Controle de acesso — Gateway

```
Cliente
  │
  ├─ sem X-API-Key header  →  401 Unauthorized
  ├─ chave inválida         →  403 Forbidden
  ├─ acima do rate limit    →  429 Too Many Requests
  └─ chave válida           →  proxy para API (máx 10 req/s, burst 20)
                                  X-Request-ID propagado para correlação
```

---

## CI/CD — GitHub Actions

```
push / pull_request
  │
  ├─ Lint    ruff check + black --check
  ├─ Test    pytest tests/
  └─ Build   docker build + push para GHCR  (somente push em main)
```
