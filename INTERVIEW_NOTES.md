# Cola de Entrevista — Projeto MLOps Challenge

Documento curto para revisão rápida antes de entrevista.

Uso recomendado:

- ler este arquivo em 5 minutos antes da conversa
- usar o `TECH_DECISIONS.md` como material completo de apoio

---

## 1. Qual foi o principal foco técnico do projeto?

O projeto já tinha uma base funcional. Meu foco principal foi fechar os gaps operacionais que impediam uma entrega realmente confiável de MLOps: governança do artefato, deploy coerente, métricas de verdade, previsibilidade do serving, cobertura de testes nos pontos críticos e qualidade intrínseca do código.

---

## 2. Qual era o problema mais importante?

O maior problema era a incoerência entre publicação e deploy. O pipeline publicava artefatos em `artifacts/published/<run_id>`, mas o serving recarregava do diretório bruto de treino. Isso quebrava a ideia de promoção controlada e enfraquecia a rastreabilidade.

---

## 3. O que você decidiu sobre deploy de modelo?

Decidi que o deploy deve usar apenas o artefato publicado. A pasta `published` virou a fonte de verdade do serving através do método `_resolve_published_root()`. Isso garante coerência entre validação, publicação e produção.

---

## 4. Como você tratou rastreabilidade do modelo ativo?

Passei a expor no serving não só o `run_id`, mas também `git_sha`, `published_at` e o caminho efetivo do artefato carregado via `LoadedModelInfo`. Isso ajuda suporte, auditoria e troubleshooting.

---

## 5. O que foi feito na observabilidade?

O endpoint `/metrics` originalmente devolvia JSON, mas o Prometheus esperava o formato textual padrão. Corrigi isso usando `prometheus_client.generate_latest()` e mantive um endpoint JSON separado, `/metrics/json`, para debug operacional e testes. O dashboard do Grafana também foi migrado de datasource Infinity para PromQL real.

---

## 6. Havia algum bug na classe de métricas além do formato?

Sim, dois bugs adicionais. O primeiro era um rastreamento de estado duplicado: havia variáveis inteiras Python (`_req_count`, `_err_count`) sendo incrementadas manualmente em paralelo aos `Counter` do `prometheus_client`, o que é uma violação DRY clássica com risco de divergência entre as duas fontes de verdade.

O segundo era um bug de nomeação: os `Counter` tinham nomes terminados em `_total`. O `prometheus_client` acrescenta `_total` automaticamente, gerando amostras `requests_total_total` que não casavam com as queries PromQL. A correção foi criar os counters sem o sufixo e ler via `registry.get_sample_value("requests_total")`.

---

## 7. O que você mudou nos testes?

Os testes existentes cobriam contrato básico, mas não os maiores riscos do fluxo. Adicionei cobertura para `/reload`, lineage do artefato publicado, `/metrics` no formato Prometheus e `/metrics/json` para contadores de debug.

---

## 8. Qual era o problema do n8n?

O workflow estava correto conceitualmente, mas a infraestrutura do container `n8n` não suportava a execução real dos comandos usados no fluxo. Ou seja: havia orquestração declarada, mas não operacional.

---

## 9. Como você corrigiu o n8n?

Implementei uma imagem customizada do `n8n` com as ferramentas necessárias para o workflow real: `docker`, `docker compose`, `python3`, `git`, `bash` e `curl`, além do mount do `docker.sock` e do workspace com escrita. Na validação real, também foi necessário fixar `DOCKER_API_VERSION=1.44` nas etapas que chamam `docker compose`, para compatibilizar o client do container com o daemon do host. O webhook de produção e a execução dos nós de shell já foram validados localmente.

---

## 10. Quais melhorias de código limpo você aplicou além das correções funcionais?

Quatro pontos:

1. **Nomenclatura de `TransformerConfig`:** os campos `pt_vocab_size` e `en_vocab_size` estavam acoplados ao par de idiomas, quebrando generalidade. Renomeei para `encoder_vocab_size` e `decoder_vocab_size`, que descrevem a posição na arquitetura, não o idioma.

2. **Bug silencioso no tokenizador:** o bloco `try/except` de importação de `tensorflow_text` nunca atribuía `False` ao flag `_TF_TEXT_OK` em caso de falha. O flag era inicializado como `True` antes do bloco e o `except` estava vazio. Corrigi para atribuir `False` no except.

3. **API depreciada do Python:** `datetime.utcnow()` foi depreciado no Python 3.12 por retornar um datetime naive. Substituí por `datetime.now(timezone.utc)`.

4. **Lock redundante em `AppMetrics`:** havia um `threading.Lock` na classe, mas o `prometheus_client` já é thread-safe internamente. Removi para evitar falsa sensação de segurança e código desnecessário.

---

## 11. Como você lidou com a compatibilidade do TensorFlow?

Tratei isso como questão de plataforma. O stack completo com `tensorflow-text` não é bem suportado no Windows local deste ambiente, então a estratégia correta é separar execução:

- API, testes de contrato e validações leves localmente
- treino e pipeline ML completo via Docker/Linux

Isso é mais robusto e mais honesto do que tentar forçar compatibilidade total em qualquer ambiente.

---

## 12. Os testes passaram?

Sim. A suíte passou com `12 passed` após as correções.

---

## 13. Existe algum ponto funcional ainda em aberto?

Sim. O maior ponto ainda aberto é fechar uma rodada completa de treino/publicação/deploy via `n8n` no ambiente alvo sem depender de observação manual. A infraestrutura necessária já está no repositório e foi validada localmente. O risco principal restante é operacional, não de código.

---

## 14. Qual foi a principal postura técnica adotada?

Evitar gambiarra que "parece funcionar" e priorizar coerência operacional. Em vez de aceitar workarounds soltos, a ideia foi transformar os componentes já existentes em um fluxo realmente defensável para produção, com código que diz o que faz e não esconde problemas.

---

## 15. Se perguntarem "o que esse projeto demonstra sobre você?", qual é a melhor resposta?

Que eu consigo pegar uma base já existente, identificar os riscos reais de operação, corrigir incrementalmente os pontos mais críticos e organizar a solução com foco em confiabilidade, rastreabilidade e deploy sustentável. E que não aceito "funciona no meu ambiente" como critério de qualidade — se o código tem bugs silenciosos, nomeação enganosa ou duplicação de estado, isso vira dívida técnica que machuca a operação.
