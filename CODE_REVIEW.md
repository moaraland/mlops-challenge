# Code Review — MLOps Challenge

**Data da revisão original:** 2026-03-28
**Última atualização:** 2026-03-30
**Revisor:** Engenheiro responsável pela entrega
**Destinatário:** Liderança técnica avaliadora

---

## Escopo

Revisão técnica completa do repositório contra os requisitos do desafio (`CHALLENGE.md`) e as boas práticas de engenharia de software e código limpo. Esta versão incorpora todas as correções aplicadas até a data de entrega.

Áreas cobertas:

- rastreabilidade de `run_id` e `git_sha` entre treino, publicação e serving
- robustez do gateway e gestão de segredos
- atomicidade e executabilidade da orquestração n8n
- health checks e ordem de subida dos serviços
- observabilidade com logs e métricas
- qualidade estrutural do código Python
- código limpo, DRY e coerência semântica

---

## Status geral dos requisitos

| Requisito | Status |
|---|---|
| Pipeline ML de ponta a ponta | implementado |
| Serving via FastAPI com TF SavedModel | implementado |
| Gateway NGINX com autenticação e rate limit | implementado |
| Orquestração n8n do ciclo completo | infraestrutura pronta, rodada completa pendente no ambiente alvo |
| Observabilidade Prometheus + Grafana | implementado |
| CI/CD com GitHub Actions | implementado |
| Rastreabilidade run_id / git_sha | implementado |
| Testes automatizados | implementado |

---

## Achados resolvidos

### 1. Path stripping quebrava caminhos absolutos no container

**Gravidade:** Crítica
**Status:** Resolvido

O `ModelManager` chamava `Path(artifacts_dir.strip("/"))`, convertendo caminhos absolutos como `/workspace/artifacts` em caminhos relativos. Dentro do container isso causava resolução incorreta, potencialmente apontando para `/workspace/workspace/artifacts`.

`ReloadRequest` definia `artifacts_dir="/artifacts"` como valor padrão no schema, o que fazia o endpoint `/reload` trocar o diretório de artefatos mesmo quando o cliente não enviava esse campo.

Correção aplicada:
- caminho preservado sem remoção de barra inicial
- `artifacts_dir` no schema passa a ser `None` por padrão
- o diretório alternativo só é usado quando vier explicitamente na requisição
- o caminho efetivo carregado passa a ser logado

Arquivos:
- `inference_api/model_manager.py`
- `inference_api/schemas.py`
- `inference_api/main.py`

---

### 2. Deploy ignorava o artefato publicado — governança quebrada

**Gravidade:** Crítica
**Status:** Resolvido

O pipeline publicava artefatos em `artifacts/published/<run_id>/`, mas o serving recarregava de `artifacts/<run_id>/saved_model`, ou seja, do diretório bruto de treino. A etapa de publicação existia no fluxo mas não era a fonte de verdade do deploy.

Correção aplicada:
- `ModelManager._resolve_published_root()` passou a enforçar que o artefato servido vem sempre de `artifacts/published/<run_id>/saved_model`
- `LoadedModelInfo` passou a expor `run_id`, `git_sha`, `published_at` e `artifact_path`
- o endpoint `/model` retorna esses metadados para auditoria e incident response

Arquivos:
- `inference_api/model_manager.py`
- `inference_api/main.py`
- `inference_api/schemas.py`
- `pipeline/publish.py`

---

### 3. `/metrics` retornava JSON — scrape Prometheus não funcionava

**Gravidade:** Alta
**Status:** Resolvido

O endpoint `/metrics` devolvia JSON enquanto o Prometheus esperava o formato textual de exposição padrão. A integração estava declarada e configurada, mas tecnicamente incorreta.

Correção aplicada:
- `/metrics` agora expõe o formato Prometheus via `prometheus_client.generate_latest()`
- `/metrics/json` mantido como endpoint separado para debug operacional e testes
- dashboard do Grafana migrado de datasource Infinity para PromQL real

Arquivos:
- `inference_api/metrics.py`
- `inference_api/main.py`
- `monitoring/dashboards/mlops-dashboard.json`
- `monitoring/datasources/prometheus.yml`
- `monitoring/prometheus.yml`

---

### 4. Divergência entre o requisito do desafio e a direção de tradução implementada

**Gravidade:** Alta
**Status:** Resolvido

O desafio especifica EN→PT. O projeto estava orientado para PT→EN nos schemas de request/response, na documentação e nos exemplos.

Correção aplicada:
- pipeline, serving, schemas e documentação alinhados para EN→PT
- `supervised_keys` do dataset `para_crawl/enpt` confirmado como `('en', 'pt')`

Arquivos:
- `inference_api/schemas.py`
- `inference_api/main.py`
- `ml/tokenizers.py`
- `README.md`

---

### 5. Nomenclatura de `TransformerConfig` acoplada a idiomas específicos

**Gravidade:** Média
**Status:** Resolvido

Os campos `pt_vocab_size` e `en_vocab_size` em `TransformerConfig` estavam acoplados ao par de idiomas EN→PT, quebrando coesão semântica e generalidade do modelo. Renomear os campos para um par de idiomas diferente exigiria mudanças em toda a configuração.

Correção aplicada:
- campos renomeados para `encoder_vocab_size` e `decoder_vocab_size`
- `Transformer.__init__` e `Transformer.call` atualizados
- `ml/train.py` atualizado na instanciação de `TransformerConfig`
- variável interna `L` renomeada para `seq_len` para maior legibilidade

Arquivos:
- `ml/model.py`
- `ml/train.py`

---

### 6. `AppMetrics` — rastreamento duplo de estado e naming bug no Counter

**Gravidade:** Média
**Status:** Resolvido

A classe `AppMetrics` mantinha contadores duplicados: variáveis inteiras Python (`_req_count`, `_err_count`, `_trans_count`) incrementadas manualmente em paralelo aos `Counter` do `prometheus_client`. Isso é uma violação DRY clássica com risco de divergência entre as duas fontes de verdade.

Havia também um bug de nomeação: os `Counter` foram criados com nomes terminados em `_total` (`requests_total`, `errors_total`, `translations_total`). O `prometheus_client` acrescenta `_total` automaticamente, gerando amostras com nomes `requests_total_total`, que não combinam com as queries PromQL esperadas.

Além disso, havia um `threading.Lock` redundante, pois o `prometheus_client` já é thread-safe internamente.

Correção aplicada:
- contadores Python removidos — `prometheus_client` é a única fonte de verdade
- `Counter` criados sem sufixo `_total` nos nomes (`requests`, `errors`, `translations`)
- `to_dict()` lê via `registry.get_sample_value("requests_total")`, que é a API pública correta
- `threading.Lock` removido

Arquivos:
- `inference_api/metrics.py`

---

### 7. `datetime.utcnow()` — uso de API depreciada desde Python 3.12

**Gravidade:** Baixa
**Status:** Resolvido

`datetime.utcnow()` foi depreciado no Python 3.12 por retornar um datetime naive sem timezone, o que facilita erros silenciosos em comparações e serialização.

Correção aplicada:
- substituído por `datetime.now(timezone.utc)` em `ml/common.py`

Arquivos:
- `ml/common.py`

---

### 8. `ml/tokenizers.py` — try/except com guarda de flag sempre verdadeira

**Gravidade:** Média
**Status:** Resolvido

O bloco de importação de `tensorflow_text` capturava a exceção mas nunca atribuía `False` ao flag de controle `_TF_TEXT_OK`. O flag era inicializado como `True` antes do bloco, e o except vazio não o alterava. Em consequência, qualquer falha na importação de `tensorflow_text` passava despercebida e o código subsequente se comportava como se o módulo estivesse disponível.

Correção aplicada:

```python
try:
    import tensorflow_text  # noqa: F401
    _TF_TEXT_OK = True
except Exception:
    _TF_TEXT_OK = False
```

Arquivos:
- `ml/tokenizers.py`

---

### 9. Infraestrutura do n8n declarativa, não operacional

**Gravidade:** Alta
**Status:** Parcialmente resolvido

O workflow do `n8n` usa nós `Execute Command` com `docker compose`, `python3` e `git`. A configuração original usava a imagem padrão do `n8n` sem acesso ao Docker host, sem as ferramentas necessárias e com workspace montado como somente leitura.

Correção aplicada:
- imagem custom criada em `n8n/Dockerfile` com `docker`, `docker compose`, `python3`, `git`, `bash` e `curl`
- `docker.sock` montado para acesso Docker-out-of-Docker
- workspace montado com permissão de escrita
- `DOCKER_API_VERSION=1.44` configurado para compatibilizar client do container com daemon do host
- webhook de produção e execução dos nós `Execute Command` validados no ambiente local

Ponto aberto:
- rodada completa de treino → publish → deploy via `n8n` ainda não foi fechada no ambiente alvo sem acompanhamento manual

Arquivos:
- `n8n/Dockerfile`
- `n8n/docker-wrapper.sh`
- `n8n/workflow.json`
- `docker-compose.yml`

---

## Pontos validados positivamente

### Gateway e segurança de borda

O `gateway/nginx.conf` está acima do mínimo esperado para o escopo:

- autenticação por `X-API-Key` com mapeamento por chave
- rate limiting por chave (10 req/s, burst 20)
- logs estruturados em JSON com campos padronizados
- mascaramento parcial da chave nos logs para segurança operacional
- propagação de `X-Request-ID` para correlação de requests
- `depends_on` com `condition: service_healthy` garantindo ordem de subida

Observação: há defaults locais como `changeme-secret-key`. O `.env.example` documenta explicitamente que esses valores devem ser trocados fora do ambiente local, que é o tratamento correto para segredos em repositórios públicos.

### Health check e dependência de serviços

O `depends_on` entre gateway e API usa `condition: service_healthy`, ou seja, o gateway só sobe depois que a API responde com sucesso no health check. Esse padrão evita o race condition de subida que é um dos problemas mais comuns em stacks Docker Compose.

### Estrutura Python e CI/CD

- `ruff` e `black` configurados no `pyproject.toml` com estilo aplicado consistentemente
- CI com três etapas independentes: Lint → Test → Build & Publish no GHCR
- `__init__.py` presente em todos os pacotes (`inference_api`, `ml`, `tests`)
- imports organizados seguindo convenção do `ruff`
- erros de CI de lint corrigidos e suíte de testes passando (12 passed)

### Logging estruturado

`inference_api/logging_config.py` implementa `StructuredFormatter` com campos padronizados no formato `key=value`, compatível com ingestão em sistemas de observabilidade. A configuração é feita uma única vez no startup e aplica ao logger raiz.

---

## Cobertura de testes

Endpoints cobertos pelos testes automatizados:

- `GET /health`
- `POST /predict`
- `GET /metrics` (formato Prometheus)
- `GET /metrics/json` (formato dict)
- `GET /model`
- `POST /reload`

Lacunas que permanecem válidas como próximos passos:

- teste de lineage entre artefato publicado e artefato servido (unitário na resolução de path)
- teste de configuração efetiva do gateway (nginx.conf)
- teste de scrape Prometheus funcional com container real
- teste de round-trip completo do workflow n8n

---

## Parecer final

O repositório passou de uma base funcional com bloqueadores operacionais para uma entrega com governança coerente. Os cinco bloqueadores originais foram resolvidos. Os refactorings de código limpo fecharam issues adicionais que, embora menores, demonstram atenção à qualidade intrínseca: DRY em métricas, nomeação semântica de configuração, uso de APIs modernas do Python e correção de bug silencioso no guard de importação.

O único ponto ainda em aberto com peso operacional é fechar a rodada completa do workflow n8n no ambiente alvo. A infraestrutura necessária está no repositório e foi validada localmente. O que falta é a execução completa no ambiente Docker Linux de destino.

| Dimensão | Avaliação |
|---|---|
| Funcionalidade básica | atende |
| Governança e rastreabilidade | atende |
| Orquestração operacional | parcial |
| Observabilidade | atende |
| Segurança de borda | atende |
| Qualidade de código | atende |
| Cobertura de testes | atende com lacunas pontuais |

A entrega está em condições de defesa técnica com narrativa coerente entre o que está no código, o que está documentado e o que foi validado.
