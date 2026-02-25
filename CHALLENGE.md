# 🏆 Desafio MLOps — Especificação

## Objetivo

Construir um fluxo **end-to-end** que automatize todo o ciclo de vida do modelo de tradução PT → EN fornecido neste repositório, desde a preparação de dados até o deploy em produção.

As **rotinas base já estão implementadas** (preparação de dados, treinamento, API de inferência) e deve criar a **infraestrutura de automação, orquestração e observabilidade** ao redor delas.

---

## 🧩 O Que Já é Fornecido

| Componente | Localização | Descrição |
|---|---|---|
| Preparação de Dados | `ml/prepare_dataset.py` | Download do ParaCrawl, tokenização e geração de TFRecords |
| Treinamento | `ml/train.py` | Treino do Transformer, exportação de SavedModel versionado |
| Inference API | `inference_api/` | API FastAPI com endpoints `/predict`, `/health`, `/model`, `/metrics`, `/reload` |
| Testes de Contrato | `tests/test_api_contract.py` | Validação dos contratos dos endpoints |
| Docker | `Dockerfile` + `docker-compose.yml` | Imagem base e profiles para execução individual das rotinas |

> [!NOTE]
> Consulte o [README.md](README.md) para detalhes de como executar cada rotina individualmente.

---

## 🎯 Requisitos do Desafio

### 1. Orquestração com n8n

Utilizar o [n8n](https://n8n.io/) como orquestrador central do pipeline, disparado via **webhook**.

O fluxo orquestrado deve encadear as seguintes etapas em sequência:

```
Webhook → Preparar Dados → Treinar → Validar → Publicar Artefatos → Deploy
```

**Espera-se:**
- Um workflow n8n funcional e exportável (JSON)
- Cada etapa deve invocar os containers/scripts correspondentes
- Tratamento de falhas entre etapas (se o treino falhar, o deploy não deve acontecer)
- Passagem de parâmetros entre etapas (ex.: `run_id` gerado no treino → usado no deploy)

---

### 2. Automação do Pipeline ML

Automatizar a execução sequencial das etapas:

| # | Etapa | Entrada | Saída |
|---|---|---|---|
| 1 | **Preparar Dados** | Parâmetros (dataset, max_tokens, etc.) | `data/processed/` com TFRecords |
| 2 | **Treinar** | Dados processados + hiperparâmetros | `artifacts/<run_id>/` com SavedModel |
| 3 | **Validar** | Artefatos do treino | Aprovação/rejeição baseada em threshold |
| 4 | **Publicar** | Artefatos validados | Artefatos versionados + metadados |
| 5 | **Deploy** | Artefato publicado | API servindo o novo modelo |

**Espera-se:**
- Versionamento automático dos artefatos (o `run_id` já é gerado pela rotina de treino)
- Metadados rastreáveis (git SHA, data, métricas de treino, parâmetros)
- A etapa de validação deve impedir o deploy de modelos abaixo do threshold de qualidade

---

### 3. Gateway / Controle de Acesso à API

A API de inferência já está implementada. O candidato deve adicionar uma camada de controle de acesso à frente dela, utilizando um **API Gateway** (ex.: Kong, Traefik, NGINX, etc.) ou solução equivalente.

**Requisitos mínimos:**
- **Autenticação** — ao menos API key ou Basic Auth
- **Rate limiting** — limitar requisições por cliente/chave
- **Logging** — registrar requisições que passam pelo gateway

> [!TIP]
> Não é obrigatório usar um produto de gateway específico. Qualquer solução que demonstre controle de acesso, rate limiting e logging é aceita (inclusive um middleware customizado), desde que seja justificada.

---

### 4. CI/CD

Implementar um pipeline de integração e entrega contínua (GitHub Actions, GitLab CI, ou equivalente).

**O pipeline deve incluir:**

| Stage | Ações |
|---|---|
| **Lint** | Verificação de estilo/qualidade do código (ex.: `ruff`, `flake8`, `black`) |
| **Test** | Execução dos testes automatizados (`pytest`) |
| **Build** | Build da imagem Docker |
| **Publish** | Push da imagem para um registry (Docker Hub, GHCR, ECR, etc.) |

---

### 5. Observabilidade

Implementar observabilidade mínima para o ambiente.

**Requisitos mínimos:**

| Pilar | Requisito |
|---|---|
| **Logs** | Logs estruturados da API e do pipeline (a API já emite logs estruturados) |
| **Health Checks** | Verificação periódica de saúde dos serviços (a API já expõe `/health`) |
| **Métricas** | Coleta e visualização de métricas básicas (a API já expõe `/metrics`) |

**Espera-se:**
- Centralização de logs (ex.: Loki, ELK, CloudWatch, ou mesmo `docker compose logs`)
- Health checks configurados no Docker Compose ou equivalente
- Coleta e/ou dashboard de métricas (ex.: Prometheus + Grafana, ou solução mais simples)

> [!NOTE]
> A API já fornece os endpoints `/health` e `/metrics`. O candidato deve **consumir e integrar** esses dados, não reimplementá-los.

---

## 📦 Entregáveis

| # | Entregável | Formato |
|---|---|---|
| 1 | **Repositório Git** | Fork ou repositório próprio com todo o código |
| 2 | **Workflow n8n** | Arquivo JSON exportado do n8n |
| 3 | **Pipeline CI/CD** | Arquivo(s) de configuração (ex.: `.github/workflows/`) |
| 4 | **Docker Compose atualizado** | `docker-compose.yml` incluindo n8n, gateway, e outros serviços adicionados |
| 5 | **Documentação** | README atualizado explicando como executar o ambiente completo |
| 6 | **Diagrama de arquitetura** | Visualização do fluxo end-to-end (formato livre) |

---

## ✅ Critérios de Avaliação

| Critério | Peso | Descrição |
|---|---|---|
| **Funcionalidade** | Alto | O pipeline funciona de ponta a ponta? Todas as etapas são executadas corretamente? |
| **Automação** | Alto | O fluxo é disparado por um único trigger e executa sem intervenção manual? |
| **Qualidade do código** | Médio | Organização, clareza, boas práticas, tratamento de erros |
| **Observabilidade** | Médio | Logs, métricas e health checks estão integrados e acessíveis? |
| **Segurança** | Médio | A API está protegida? Secrets são gerenciados corretamente? |
| **Documentação** | Médio | É possível reproduzir o ambiente apenas seguindo a documentação? |
| **Extras** | Bônus | Rollback automático, testes de integração adicionais, alertas, etc. |