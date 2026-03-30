# Decisões Técnicas do Projeto

Documento de apoio para defesa do projeto na vaga de MLOps da Hand Talk.

Objetivo:

- registrar o que estava assim no projeto
- o que foi mudado ou precisa ser mudado
- por que a decisão foi tomada
- qual risco ela evita
- qual o status atual

Este documento é separado do `README.md` de propósito. O README explica como usar o projeto. Este arquivo explica o raciocínio técnico e operacional por trás das decisões.

---

## Como ler este documento

Cada decisão segue o mesmo formato:

- `Antes`: como o projeto estava
- `Decisão`: o que foi escolhido
- `Motivo`: por que isso é tecnicamente mais correto
- `Impacto`: o que essa decisão melhora ou protege
- `Status`: `implementado`, `parcial` ou `pendente`

---

## Decisão 1 — Artefato publicado deve ser a fonte de verdade do deploy

**Antes**

- O treino gerava artefatos em `artifacts/<run_id>/`.
- A etapa de publish copiava para `artifacts/published/<run_id>/`.
- O deploy via `/reload` recarregava o modelo usando o caminho bruto do treino, não o artefato publicado.

**Decisão**

- O serving deve carregar somente de `artifacts/published/<run_id>/saved_model`.
- O artefato promovido/publicado passa a ser a fonte oficial de verdade para deploy.

**Motivo**

- O fluxo correto de MLOps não deve servir um artefato que ainda não passou pela etapa formal de publicação.
- Publicação existe justamente para consolidar lineage, metadados e promoção controlada.
- Se o deploy ignora a pasta `published`, a governança do pipeline fica incoerente.

**Impacto**

- fecha o vínculo entre validação, publicação e deploy
- reduz risco de servir um modelo não promovido
- melhora rastreabilidade operacional

**Status**

- `implementado`

Arquivos impactados:

- `inference_api/model_manager.py`
- `inference_api/main.py`
- `pipeline/publish.py`
- `pipeline/run_pipeline.sh`

---

## Decisão 2 — Preservar caminhos absolutos e não sobrescrever `artifacts_dir` por padrão

**Antes**

- O `ModelManager` removia barras do início do caminho com `strip("/")`.
- O `ReloadRequest` definia `artifacts_dir="/artifacts"` como padrão.
- Isso podia alterar o diretório efetivo mesmo quando o cliente não queria trocar nada.

**Decisão**

- Preservar o caminho exatamente como configurado.
- `artifacts_dir` no `/reload` deve ser opcional e `None` por padrão.
- Só usar um diretório alternativo quando ele vier explicitamente no request.

**Motivo**

- Um serviço de produção não deve reinterpretar caminho absoluto de forma implícita.
- O endpoint `/reload` precisa ser previsível e não surpreender a operação.

**Impacto**

- evita bugs de path dentro do container
- reduz comportamento implícito difícil de diagnosticar
- melhora confiabilidade operacional

**Status**

- `implementado`

Arquivos impactados:

- `inference_api/model_manager.py`
- `inference_api/schemas.py`
- `inference_api/main.py`

---

## Decisão 3 — Expor lineage do modelo ativo na API

**Antes**

- A API expunha basicamente `run_id`.
- `git_sha`, timestamp de publicação e caminho efetivo do modelo ativo não apareciam na resposta do serving.

**Decisão**

- Expor no `/model` e no `/reload`:
  - `run_id`
  - `git_sha`
  - `published_at`
  - `artifact_path`

**Motivo**

- Em produção, saber apenas o `run_id` não basta.
- Para auditoria, suporte e incidentes, é importante identificar exatamente qual artefato está servido.

**Impacto**

- melhora debugging
- facilita incident response
- fortalece governança de modelo

**Status**

- `implementado`

Arquivos impactados:

- `inference_api/model_manager.py`
- `inference_api/main.py`
- `inference_api/schemas.py`

---

## Decisão 4 — `/metrics` deve servir Prometheus de verdade

**Antes**

- O endpoint `/metrics` devolvia JSON.
- O Prometheus estava configurado para fazer scrape nesse endpoint.
- Na prática, a integração estava conceitualmente montada, mas tecnicamente incorreta.

**Decisão**

- `/metrics` passa a expor o formato textual esperado pelo Prometheus.
- Foi mantido um endpoint JSON separado, `/metrics/json`, para inspeção operacional simples e compatibilidade com testes.

**Motivo**

- Observabilidade “de verdade” precisa funcionar com o coletor configurado.
- O endpoint principal deve atender ao padrão da ferramenta que consome as métricas.
- O JSON pode existir como conveniência, mas não como endpoint principal do scrape.

**Impacto**

- fecha a integração Prometheus
- reduz gap entre documentação e operação real
- melhora qualidade da observabilidade

**Status**

- `implementado`

Arquivos impactados:

- `inference_api/metrics.py`
- `inference_api/main.py`
- `tests/test_api_contract.py`

---

## Decisão 5 — Testes devem cobrir riscos reais, não só contratos superficiais

**Antes**

- Os testes cobriam `/health`, `/predict`, `/metrics` e `/model`.
- Não havia teste de lineage do artefato publicado.
- Não havia teste de `/reload` para garantir que o deploy partia do artefato promovido.

**Decisão**

- Adicionar testes para:
  - `/reload` carregando a partir de `artifacts/published/<run_id>`
  - retorno de metadados do modelo ativo
  - `/metrics` em formato Prometheus
  - `/metrics/json` para contadores de debug

**Motivo**

- Em MLOps, os maiores riscos normalmente estão nas bordas entre pipeline, publicação e serving.
- Testar só “endpoint sobe e responde” não valida governança real do fluxo.

**Impacto**

- aumenta confiança nas correções principais
- protege contra regressão nas partes mais críticas
- demonstra visão de operação, não só de API

**Status**

- `implementado`

Arquivo impactado:

- `tests/test_api_contract.py`

---

## Decisão 6 — Compatibilidade de TensorFlow deve ser tratada por ambiente, não na marra

**Antes**

- O ambiente local Windows tentou instalar a stack completa de ML.
- `tensorflow-text==2.20.0` não tem wheel viável neste ambiente.
- A venv ainda estava inconsistente, com `pydantic_core` compilado para outra versão de Python.

**Decisão**

- Separar a estratégia de execução por perfil de ambiente:
  - API, contratos e validações leves podem rodar localmente
  - pipeline ML completo deve rodar em Docker/Linux
- Evitar depender do Windows local para o stack completo de treino.

**Motivo**

- Esse é um problema clássico de plataforma, não de lógica do projeto.
- Em MLOps, insistir em “fazer tudo rodar em qualquer ambiente” gera mais fragilidade do que valor.
- O correto é definir um ambiente suportado para treino e serving do stack ML.

**Impacto**

- reduz ruído de setup
- deixa a execução mais reproduzível
- melhora a história técnica para defesa do projeto

**Status**

- `parcial`

Observação:

- a venv foi reparada o suficiente para rodar `pytest`
- ainda falta formalizar no repositório a separação de dependências por perfil

---

## Decisão 7 — O serviço `n8n` precisa ser operacional, não apenas declarativo

**Antes**

- O workflow do `n8n` chama `docker compose`, `python3` e `git`.
- O serviço `n8n` no Compose usa a imagem padrão e monta o workspace como somente leitura.
- Não havia acesso ao Docker host nem garantia das ferramentas necessárias dentro do container.

**Decisão**

- O `n8n` deve rodar com uma imagem preparada para o workflow real.
- Essa imagem deve conter as ferramentas mínimas usadas pelos nós do fluxo.
- O acesso ao Docker host deve ser configurado de forma explícita se a abordagem continuar sendo Docker-out-of-Docker via socket.

**Motivo**

- O desafio pede um workflow funcional, não apenas exportável.
- O ponto de avaliação aqui é automação operacional de ponta a ponta.

**Impacto**

- fecha o principal gap de execução real do pipeline
- torna o workflow reproduzível
- melhora a credibilidade técnica da entrega

**Status**

- `parcial`

Implementação atual:

- foi criada uma imagem custom em `n8n/Dockerfile`
- o runtime passou a incluir `docker`, `docker compose`, `python3`, `git`, `bash` e `curl`
- o serviço `n8n` agora monta o workspace com escrita e monta `/var/run/docker.sock`

Observação:

- a infraestrutura necessária já foi incorporada ao repositório
- o webhook e a execução real dos nós `Execute Command` já foram validados no ambiente Docker local
- foi necessário fixar `DOCKER_API_VERSION=1.44` nas etapas que chamam `docker compose` para compatibilizar o client do container com o daemon exposto via socket
- o checkpoint operacional que ainda falta é fechar uma rodada completa de treino, publicação e deploy via `n8n` sem acompanhamento manual

Arquivos impactados:

- `n8n/Dockerfile`
- `n8n/docker-wrapper.sh`
- `n8n/workflow.json`
- `docker-compose.yml`

---

## Decisão 8 — A direção da tradução precisa ser alinhada com o desafio

**Antes**

- O desafio descreve EN→PT.
- O projeto e a documentação estavam orientados para PT→EN.

**Decisão**

- Ajustar a solução para EN→PT de forma explícita no pipeline de dados, no serving e na documentação.

**Motivo**

- Essa divergência pode ser interpretada como falha de leitura de requisito.
- Mesmo com boa implementação, desalinhamento funcional pode comprometer avaliação.

**Impacto**

- reduz risco de reprovação por mismatch com o enunciado
- melhora clareza da narrativa técnica na apresentação

**Status**

- `implementado`

---

## Decisão 9 — Fix rápido não deve virar gambiarra estrutural

**Antes**

- Havia tentação de resolver problemas isolados com patches mínimos, por exemplo:
  - montar só o `docker.sock`
  - aceitar endpoint de métricas inadequado com workaround
  - tolerar diferença entre publicado e servido

**Decisão**

- Priorizar correções estruturais que fechem a coerência do fluxo.
- Evitar “meia solução” que mascara falhas de operação.

**Motivo**

- Em vaga de MLOps/SRE, a avaliação tende a olhar maturidade operacional.
- Soluções parciais demais podem soar como desconhecimento do problema real.

**Impacto**

- aumenta consistência da entrega
- melhora tua defesa técnica em entrevista
- evita contradições entre discurso e funcionamento do sistema

**Status**

- `em andamento`

---

## Decisão 10 — `TransformerConfig` deve nomear campos pela posição na arquitetura, não pelo idioma

**Antes**

- Os campos eram `pt_vocab_size` e `en_vocab_size`.
- O código do modelo estava acoplado ao par de idiomas EN→PT.
- Renomear para outro par de idiomas exigiria mudanças em toda a configuração.

**Decisão**

- Renomear para `encoder_vocab_size` e `decoder_vocab_size`.
- O modelo Transformer descreve papéis arquiteturais, não idiomas.

**Motivo**

- Nomes acoplados a idiomas violam o princípio de separação de responsabilidades.
- O `TransformerConfig` deve descrever a arquitetura. A escolha de idioma é responsabilidade do pipeline de dados.

**Impacto**

- Remove acoplamento desnecessário
- Facilita reuso do modelo para outros pares de idiomas
- Melhora legibilidade do código de treino

**Status**

- `implementado`

Arquivos impactados:

- `ml/model.py`
- `ml/train.py`

---

## Decisão 11 — `AppMetrics` deve ter uma única fonte de verdade para os contadores

**Antes**

- A classe mantinha variáveis inteiras Python (`_req_count`, `_err_count`, `_trans_count`) incrementadas manualmente em paralelo aos `Counter` do `prometheus_client`.
- Havia também um `threading.Lock` manual, redundante porque o `prometheus_client` é thread-safe internamente.
- Os `Counter` tinham nomes terminados em `_total`, o que fazia o `prometheus_client` gerar amostras com nomes duplicados como `requests_total_total`.

**Decisão**

- Remover as variáveis Python redundantes.
- O `prometheus_client` passa a ser a única fonte de verdade.
- `to_dict()` lê via `registry.get_sample_value()`, que é a API pública correta.
- `Counter` criados sem sufixo `_total` nos nomes.
- `threading.Lock` removido.

**Motivo**

- Rastreamento duplo de estado viola DRY e cria risco de divergência silenciosa.
- Lock desnecessário dá falsa sensação de segurança e adiciona complexidade sem benefício.
- Bug de nomeação quebra queries PromQL e dashboards Grafana.

**Impacto**

- Elimina duplicação de estado
- Corrige queries PromQL
- Reduz complexidade acidental

**Status**

- `implementado`

Arquivos impactados:

- `inference_api/metrics.py`

---

## Decisão 12 — Usar apenas APIs não depreciadas do Python para timestamps

**Antes**

- `datetime.utcnow()` era usado em `ml/common.py` para gerar timestamps de runs.
- Esse método foi depreciado no Python 3.12 por retornar um datetime naive sem timezone, facilitando erros silenciosos em comparações e serialização.

**Decisão**

- Substituir por `datetime.now(timezone.utc)`.

**Motivo**

- Usar APIs depreciadas aumenta dívida técnica e pode gerar warnings ou comportamento incorreto em versões futuras do Python.
- Datetime com timezone explícita é mais seguro e mais expressivo.

**Status**

- `implementado`

Arquivos impactados:

- `ml/common.py`

---

## Decisão 13 — Guard de importação opcional deve ser explícito sobre sucesso e falha

**Antes**

- `ml/tokenizers.py` inicializava `_TF_TEXT_OK = True` antes do bloco `try`.
- O `except` estava vazio e não atribuía `False` ao flag.
- Em caso de falha na importação de `tensorflow_text`, o flag permanecia `True` e o código subsequente se comportava como se o módulo estivesse disponível.

**Decisão**

- O bloco `except` deve atribuir `_TF_TEXT_OK = False` explicitamente.
- O flag deve refletir o resultado real da importação.

**Motivo**

- Um guard de importação que sempre retorna `True` não é um guard, é um bug silencioso.
- Erros de importação mascarados são difíceis de diagnosticar em produção.

**Status**

- `implementado`

Arquivos impactados:

- `ml/tokenizers.py`

---

## O que já está validado

- `pytest` executado com sucesso após reparar a venv local
- suíte atual: `12 passed`
- correções prioritárias da API e do pipeline aplicadas
- trigger real do `n8n` validado via webhook de produção
- execução real dos nós `Execute Command` validada no container do `n8n`
- direção funcional da tradução alinhada para EN→PT no pipeline, serving e documentação
- refactorings de código limpo aplicados e CI passando

---

## O que ainda precisa ser fechado antes da versão final ideal

1. Fechar uma rodada completa de treino, publish e deploy via `n8n` no ambiente alvo.
2. Formalizar a estratégia de compatibilidade TensorFlow por ambiente.
3. Consolidar exemplos e evidências finais do fluxo operacional na documentação de entrega.

---

## Resumo executivo para entrevista

Se eu precisar explicar este projeto de forma objetiva, a narrativa correta é:

- o projeto já tinha uma boa base funcional
- os principais riscos estavam em coerência operacional, não em falta de componentes
- as correções priorizaram governança do artefato, previsibilidade do deploy, observabilidade real e testes cobrindo os pontos críticos
- o runtime do `n8n` já foi validado no ponto de trigger e execução de comandos, e os próximos passos naturais são fechar a rodada completa do pipeline e formalizar a estratégia de ambiente do stack TensorFlow

Essa é a história mais forte para defender o projeto com postura de MLOps sênior.
