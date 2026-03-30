# Code Review — MLOps Challenge

Data da revisão: 2026-03-28

Atualização de contexto: 2026-03-30

Este documento continua útil como fotografia da revisão estática original, mas parte dos achados já foi tratada depois dessa rodada. Status resumido após as correções mais recentes:

- achado 1: resolvido
- achado 2: resolvido
- achado 3: parcialmente resolvido
- achado 4: resolvido
- achado 5: resolvido

## Escopo

Revisão técnica do repositório com foco nos quality gates descritos em `CHALLENGE.md` e nas instruções de `codereviw.yaml`:

- rastreabilidade de `run_id` e `git_sha`
- robustez do gateway e gestão de secrets
- atomicidade da orquestração n8n
- health checks e ordem de subida dos serviços
- observabilidade com logs e métricas
- qualidade estrutural do projeto Python

## Resumo executivo

O projeto tem boa base de organização, CI configurado, gateway com autenticação/rate limit e health check da API conectado ao NGINX. A maior parte dos bloqueadores centrais identificados nesta revisão já foi tratada depois desta análise inicial. O ponto que permanece parcialmente aberto é fechar uma rodada completa de treino/publicação/deploy via `n8n` no ambiente alvo.

Os principais bloqueadores são:

1. `ARTIFACTS_DIR` e `/reload` estavam inconsistentes na API.
2. O deploy recarregava artefatos brutos de `artifacts/<run_id>` em vez dos artefatos promovidos/publicados.
3. O serviço `n8n` ainda precisa fechar a rodada completa do workflow em execução real.
4. O `/metrics` da API estava fora do formato do Prometheus.
5. Havia divergência entre a direção de tradução pedida no desafio e a direção implementada no projeto.

## Achados

### 1. Crítico — Resolução de caminho de artefatos quebra startup e reload

Arquivos:

- `inference_api/model_manager.py`
- `inference_api/schemas.py`
- `inference_api/main.py`
- `docker-compose.yml`

Problema:

- `ModelManager` faz `Path(artifacts_dir.strip("/"))`.
- Quando a API recebe `ARTIFACTS_DIR=/workspace/artifacts`, o valor vira `workspace/artifacts`.
- Dentro do container isso deixa de ser caminho absoluto e pode apontar para `/workspace/workspace/artifacts`.
- `ReloadRequest` ainda define `artifacts_dir="/artifacts"` como valor padrão, o que faz `/reload` trocar de diretório mesmo quando o cliente não pediu isso explicitamente.

Impacto:

- risco de a API não carregar o modelo no startup
- risco de `/reload` buscar modelo em diretório errado
- perda de previsibilidade operacional no serving

Evidências:

- `inference_api/model_manager.py:39`
- `inference_api/schemas.py:89-98`
- `inference_api/main.py:158-168`
- `docker-compose.yml:101`

Recomendação sênior:

- preservar caminhos absolutos sem `strip("/")`
- mudar `artifacts_dir` de `ReloadRequest` para `None` por padrão
- tratar `artifacts_dir` apenas quando o campo vier explicitamente no request
- logar o caminho efetivo carregado

### 2. Crítico — Governança do deploy não fecha com o artefato publicado

Arquivos:

- `ml/train.py`
- `pipeline/publish.py`
- `pipeline/run_pipeline.sh`
- `inference_api/main.py`

Problema:

- o treino gera `artifacts/<run_id>/metadata.json` com `git_sha`
- a publicação copia para `artifacts/published/<run_id>/` e grava `provenance.json`
- o deploy chama `/reload` apenas com `run_id`
- a API recarrega de `artifacts/<run_id>/saved_model`, não de `artifacts/published/<run_id>/saved_model`

Impacto:

- a promoção do artefato não é a fonte da verdade do deploy
- um modelo pode ser servido sem passar pela trilha final de publicação
- a API não registra qual `git_sha` está ativo após reload, apenas o `run_id`

Evidências:

- `ml/train.py:277-291`
- `pipeline/publish.py:29-54`
- `pipeline/run_pipeline.sh:131-166`
- `inference_api/main.py:173`

Recomendação sênior:

- padronizar deploy apenas a partir de `artifacts/published/<run_id>`
- manter um único formato de metadata, evitando `metadata.json` em uma etapa e `provenance.json` em outra
- no `/reload`, ler e logar `run_id`, `git_sha`, timestamp de publicação e caminho efetivo do artefato
- expor esses metadados também em `/model` ou endpoint equivalente de introspecção

### 3. Crítico — Orquestração n8n declarada, mas não executável na infraestrutura atual

Status atual:

- a infraestrutura do `n8n` foi corrigida depois desta revisão
- o webhook de produção e a execução dos nós `Execute Command` já foram validados
- o ponto ainda aberto é fechar a rodada completa de treino/publicação/deploy no ambiente alvo

Arquivos:

- `n8n/workflow.json`
- `docker-compose.yml`

Problema:

- o workflow usa múltiplos nós `Execute Command` com `docker compose`
- o serviço `n8n` não monta `/var/run/docker.sock`
- o container não foi preparado com Docker CLI
- o workspace está montado como `:ro`, o que limita cenários operacionais e depuração

Impacto:

- o fluxo central exigido pelo desafio não roda ponta a ponta na prática
- o desenho do workflow parece correto, mas a infraestrutura não suporta sua execução

Evidências:

- `n8n/workflow.json:24`
- `n8n/workflow.json:35`
- `n8n/workflow.json:57`
- `n8n/workflow.json:68`
- `docker-compose.yml:174-188`

Recomendação sênior:

- decidir explicitamente entre:
  - Docker-out-of-Docker com mount de `/var/run/docker.sock` e Docker CLI no container do `n8n`
  - ou orquestração por chamadas HTTP/serviços dedicados em vez de shelling out para Docker
- documentar o modelo operacional escolhido no README
- manter o encadeamento de erro atual, que está conceitualmente correto para atomicidade

### 4. Alto — Prometheus configurado, mas coleta não funciona com o endpoint atual

Arquivos:

- `inference_api/main.py`
- `monitoring/prometheus.yml`
- `README.md`

Problema:

- a API retorna `/metrics` em JSON
- o Prometheus espera formato de exposição próprio (`text/plain`)
- o próprio repositório já reconhece isso na configuração e no README

Impacto:

- dashboards de série temporal não funcionam de forma confiável
- o requisito de observabilidade fica parcialmente atendido só via workaround de datasource Infinity

Evidências:

- `inference_api/main.py:136-143`
- `monitoring/prometheus.yml:8-17`
- `README.md:469`

Recomendação sênior:

- migrar `/metrics` para `prometheus_client`
- manter, se desejado, um endpoint JSON separado para debug operacional
- validar scrape real via Prometheus UI e não apenas por documentação

### 5. Alto — Divergência entre o requisito do desafio e a direção de tradução implementada

Status atual:

- este achado foi resolvido
- o pipeline, o serving e a documentação foram alinhados para EN→PT

Arquivos:

- `CHALLENGE.md`
- `README.md`
- `inference_api/main.py`
- `inference_api/schemas.py`
- `ml/tokenizers.py`

Problema:

- o desafio descreve EN→PT
- na data desta revisão, o projeto implementava PT→EN

Impacto:

- risco direto de reprovação por desalinhamento com o enunciado principal

Evidências:

- `CHALLENGE.md:5`
- `README.md:3`
- `inference_api/main.py:80`
- `inference_api/schemas.py:10-14`
- `ml/tokenizers.py:19`

Recomendação sênior:

- confirmar com o avaliador qual direção é a correta
- se EN→PT for mandatória, ajustar dataset, tokenizers, documentação e exemplos
- se PT→EN for aceitável por restrição do starter kit, justificar isso claramente na documentação de entrega

## Pontos validados positivamente

### Gateway e segurança

O `gateway/nginx.conf` está acima do mínimo esperado em alguns pontos:

- autenticação por `X-API-Key`
- rate limiting por chave
- logs estruturados em JSON
- mascaramento parcial da chave nos logs
- propagação de `X-Request-ID`
- `depends_on` usando `condition: service_healthy`

Referências:

- `gateway/nginx.conf:27-39`
- `gateway/nginx.conf:45`
- `gateway/nginx.conf:51-54`
- `gateway/nginx.conf:105-119`
- `docker-compose.yml:107-132`

Observação:

- há defaults inseguros para ambiente local, como `changeme-secret-key`, `admin` e `changeme`, mas existe orientação explícita em `.env.example` para troca em ambiente não local.

### Health check e ordem de subida

O requisito de health check entre gateway e API foi atendido corretamente:

- a API possui `healthcheck`
- o gateway depende da API saudável antes de subir

Referências:

- `docker-compose.yml:107-112`
- `docker-compose.yml:130-132`

### Estrutura Python e CI

O projeto tem base boa de qualidade estática:

- `ruff` e `black` configurados no `pyproject.toml`
- CI com etapas de lint, test e build/publish
- `__init__.py` presente nos pacotes principais

Referências:

- `pyproject.toml`
- `.github/workflows/ci.yml`
- `inference_api/__init__.py`
- `ml/__init__.py`
- `tests/__init__.py`

## Lacunas de teste

Os testes automatizados existentes cobrem:

- `/health`
- `/predict`
- `/metrics`
- `/model`

Mas ainda faltam testes para pontos críticos da entrega:

- `/reload` com `run_id` válido e inválido
- carregamento de `DEFAULT_RUN_ID`
- garantia de lineage entre artefato publicado e artefato servido
- configuração efetiva do gateway
- execução real do workflow n8n
- scrape Prometheus funcional

Arquivo atual:

- `tests/test_api_contract.py`

## Parecer final

O repositório demonstra boa organização e intenção arquitetural correta, mas ainda possui falhas que invalidam uma entrega com governança forte de modelo em produção.

Status recomendado da entrega neste estado:

- funcionalidade básica: parcial
- governança/rastreabilidade: insuficiente
- orquestração operacional: insuficiente
- observabilidade: parcial
- segurança de borda: boa para o escopo

Conclusão:

O projeto ainda não está pronto para uma entrega "nota 10" sem corrigir os bloqueadores de governança do artefato, carregamento da API, infraestrutura do n8n e formato de métricas.

## Nota sobre validação local

Esta revisão nasceu como análise majoritariamente estática. Depois dela, a suíte local foi executada com sucesso (`12 passed`) e houve validação prática do webhook e da execução dos nós de shell no `n8n`. Ainda assim, este documento não substitui a validação final da rodada completa do workflow em ambiente Linux/Docker.
