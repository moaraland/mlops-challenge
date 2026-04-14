# Preparação — Conversa Técnica MLOps Challenge

## Contexto do projeto

Plataforma de **tradução automática EN→PT** com ciclo MLOps completo:
dataset → treino → validação → publicação → serving → monitoramento.

---

## 1. Arquitetura geral

**O que revisar:**
- Os 5 estágios do pipeline e a responsabilidade de cada um
- Como os componentes se comunicam (volumes Docker, chamada HTTP para `/reload`, webhook n8n)
- Por que dois níveis de artefato: `artifacts/<run_id>/` vs `artifacts/published/<run_id>/`
- O que o `run_id` carrega (`nmt_<timestamp>_<random6>`) e por que é importante para rastreabilidade

**Pergunta provável:** "Me conta o fluxo completo, do dado bruto até o modelo servido."

---

## 2. Modelo Transformer

**O que revisar:**
- Arquitetura encoder-decoder: 4 camadas, d_model=128, 4 heads
- `PositionalEmbedding`: por que posição precisa ser codificada em Transformers
- `EncoderLayer`: self-attention + feed-forward + normalização + dropout
- `DecoderLayer`: causal self-attention + cross-attention (por que são atenções diferentes?)
- Por que a atenção do decoder é **causal** (masked) — evitar vazamento de tokens futuros
- `Translator` / `ExportTranslator`: geração autoregressiva (decodificação token a token)
- **Masked loss/accuracy**: tokens de padding (id=0) não são contados — por que isso importa em NMT

**Pergunta provável:** "Por que você usa atenção causal no decoder e não no encoder?"

---

## 3. Dados e tokenização

**O que revisar:**
- Dataset ParaCrawl EN-PT carregado via TensorFlow Datasets
- Tokenizadores SentencePiece pré-treinados (`ted_hrlr_translate_pt_en`)
- Por que usar tokenizadores **pré-treinados** em vez de treinar do zero
- Formato TFRecord: por que serializar os dados antes do treino (eficiência de leitura I/O)
- `MAX_TOKENS=64`: impacto na qualidade vs velocidade de treino
- Filtro de sequências vazias (< 2 tokens)

**Pergunta provável:** "Por que TFRecord e não ler o dataset diretamente?"

---

## 4. API de Inferência (FastAPI)

**O que revisar:**
- Endpoints: `/health`, `/predict`, `/model`, `/metrics`, `/metrics/json`, `/reload`
- `ModelManager`: por que `threading.Lock` — requests concorrentes podem corromper estado
- Lazy loading: modelo carregado no primeiro request se `DEFAULT_RUN_ID` não estiver definido
- **Hot-reload sem downtime**: `/reload` troca o modelo em memória sem reiniciar o servidor
- Validação de entrada: `PredictRequest` com limite de 1–512 chars (Pydantic)
- `latency_ms` na resposta: rastreabilidade por request
- Por que o `/health` é público e os demais exigem autenticação

**Pergunta provável:** "Como você garante thread-safety na troca de modelo em produção?"

---

## 5. Gateway NGINX

**O que revisar:**
- Autenticação por header `X-API-Key` — vantagens vs JWT vs OAuth para esse contexto
- Rate limiting por chave: `10 req/s`, burst de 20 — o que acontece quando estoura (429)
- Log estruturado JSON: campos `time`, `method`, `uri`, `status`, `api_key` (mascarado: só 4 primeiros chars)
- `X-Request-ID`: gerado no gateway e propagado para o upstream (correlação de logs)
- Por que o `/health` bypassa a autenticação (health checks de infra não devem depender de credenciais)

**Pergunta provável:** "Por que mascarar a API key nos logs e não simplesmente não logar?"

---

## 6. Pipeline e Orquestração

**O que revisar:**
- `run_pipeline.sh`: os 5 estágios em ordem, qual é fatal vs não-fatal (stage 5 — deploy — é não-fatal)
- `validate.py`: quality gate — por que parar o pipeline se `val_token_accuracy < threshold`?
- `publish.py`: promoção de artefato — idempotência (não sobrescreve se já publicado)
- Metadados de proveniência: `git_sha`, `published_at`, métricas, epochs — para auditoria e rollback
- **n8n workflow**: 8 nós, acionado por webhook — diferença prática entre usar bash script vs n8n
- Por que o docker-wrapper.sh no container n8n (mapeia `docker compose` para o binário real)

**Pergunta provável:** "Por que você tem dois mecanismos de pipeline (bash + n8n)? Qual usaria em produção?"

---

## 7. Monitoramento e Observabilidade

**O que revisar:**
- Métricas Prometheus: `requests_total`, `errors_total`, `translations_total`
- Por que `prometheus_client.Counter` e não apenas logs — persistência, agregação, alertas
- Grafana: 5 painéis — total requests, translations, errors, error rate, taxa ao longo do tempo
- Intervalo de scrape: 15s — trade-off entre granularidade e overhead
- Retenção: 7 dias — suficiente para análise operacional de curto prazo
- O que está **faltando** nesse stack: traces distribuídos (OpenTelemetry), alertas configurados no Alertmanager, log aggregation (ELK/Loki)

**Pergunta provável:** "O que você adicionaria nesse stack de observabilidade para ir para produção de verdade?"

---

## 8. Infraestrutura e DevOps

**O que revisar:**
- Docker Compose com **profiles**: `prepare`, `train`, `tests`, `api`, `monitoring`, `n8n`, `full`
  — por que separar em profiles (não subir GPU/treino em prod, não subir serviço desnecessário)
- Volumes compartilhados: `tfds_cache` (evita re-download), `grafana_data`, `n8n_data`
- Dockerfile: `python:3.11-slim`, desabilita extensões desnecessárias do TF (`WRAPT_DISABLE_EXTENSIONS`)
- CI/CD GitHub Actions: Lint → Test → Build & Push para ghcr.io
  - Tags: `sha-<short-sha>` + `latest` (só em push para main)
  - Ferramentas: `ruff` (8 regras), `black` (formatação), `pytest` via Docker Compose

**Pergunta provável:** "Por que usar profiles no Docker Compose em vez de múltiplos arquivos compose?"

---

## 9. Testes

**O que revisar:**
- `test_api_contract.py`: testa contrato da API (não a lógica do modelo)
- Casos cobertos: health, validação de input (422 para texto vazio/longo/campo ausente), 503 sem modelo, métricas
- Framework: `pytest` + `TestClient` do FastAPI (sem servidor real — mais rápido em CI)
- O que **não** está testado: treino do modelo, pipeline end-to-end, performance/latência

**Pergunta provável:** "Como você testaria o modelo em si, não só a API?"

---

## 10. Decisões de design para defender

| Decisão | Justificativa |
|---|---|
| SavedModel format | Padrão TF para deploy, inclui tokenizer junto |
| Dois níveis de artefato | Separação entre "output de treino" e "aprovado para servir" |
| Hot-reload via `/reload` | Zero downtime na troca de modelo |
| Bash + n8n | Bash para desenvolvimento local rápido; n8n para automação com UI e auditoria |
| Quality gate em validate.py | Evitar regressão automática de modelo em produção |
| X-API-Key no gateway | Simples, stateless, suficiente para esse contexto |
| Per-key rate limiting | Isola clientes — um abusador não impacta os demais |

---

## 11. O que provavelmente perguntarão e pontos de atenção

- **Escalabilidade**: como escalar horizontalmente a API? (múltiplos workers Uvicorn, load balancer no NGINX, modelo em memória — stateful)
- **Modelos maiores**: o Transformer aqui é pequeno (d_model=128) — como você escalaria para produção real?
- **Segurança**: API key em header plano (sem HTTPS no compose local) — o que faria diferente?
- **Rollback**: o sistema tem artefatos versionados e proveniência — como executaria um rollback?
- **Drift de dados**: o sistema não tem monitoramento de data drift — o que adicionaria?
- **Latência**: geração autoregressiva é sequencial — quais técnicas reduziriam a latência de inferência?

---

## 12. Termos-chave para ter fluência

`SavedModel`, `TFRecord`, `SentencePiece`, `causal attention`, `masked loss`, `token accuracy`,
`hot-reload`, `thread safety`, `Prometheus scrape`, `Grafana provisioning`, `NGINX upstream`,
`rate limiting`, `artifact versioning`, `quality gate`, `idempotência`, `proveniência`,
`Docker Compose profiles`, `GitHub Actions matrix`, `ASGI`, `Pydantic validation`
