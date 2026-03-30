# Cola de Entrevista — Projeto MLOps Challenge

Documento curto para revisão rápida antes de entrevista.

Uso recomendado:

- ler este arquivo em 5 minutos antes da conversa
- usar o `TECH_DECISIONS.md` como material completo de apoio

---

## 1. Qual foi o principal foco técnico do projeto?

O projeto já tinha uma base funcional. Meu foco principal foi fechar os gaps operacionais que impediam uma entrega realmente confiável de MLOps: governança do artefato, deploy coerente, métricas de verdade, previsibilidade do serving e cobertura de testes nos pontos críticos.

---

## 2. Qual era o problema mais importante?

O maior problema era a incoerência entre publicação e deploy. O pipeline publicava artefatos em `artifacts/published/<run_id>`, mas o serving recarregava do diretório bruto de treino. Isso quebrava a ideia de promoção controlada e enfraquecia a rastreabilidade.

---

## 3. O que você decidiu sobre deploy de modelo?

Decidi que o deploy deve usar apenas o artefato publicado. A pasta `published` virou a fonte de verdade do serving. Isso garante coerência entre validação, publicação e produção.

---

## 4. Como você tratou rastreabilidade do modelo ativo?

Passei a expor no serving não só o `run_id`, mas também `git_sha`, `published_at` e o caminho efetivo do artefato carregado. Isso ajuda suporte, auditoria e troubleshooting.

---

## 5. O que foi feito na observabilidade?

O endpoint `/metrics` originalmente devolvia JSON, mas o Prometheus esperava o formato textual padrão. Corrigi isso para o formato Prometheus e mantive um endpoint JSON separado para debug operacional e testes.

---

## 6. O que você mudou nos testes?

Os testes existentes cobriam contrato básico, mas não os maiores riscos do fluxo. Adicionei cobertura para `/reload`, lineage do artefato publicado e métricas no formato correto.

---

## 7. Qual era o problema do n8n?

O workflow estava correto conceitualmente, mas a infraestrutura do container `n8n` não suportava a execução real dos comandos usados no fluxo. Ou seja: havia orquestração declarada, mas não operacional.

---

## 8. Como você corrigiu o n8n?

Implementei uma imagem customizada do `n8n` com as ferramentas necessárias para o workflow real, como `docker`, `docker compose`, `python3`, `git`, `bash` e `curl`, além do mount do `docker.sock` e do workspace com escrita. Na validação real, também foi necessário fixar `DOCKER_API_VERSION=1.44` nas etapas que chamam `docker compose`, para compatibilizar o client do container com o daemon do host. O webhook de produção e a execução dos nós de shell já foram validados localmente.

---

## 9. A sugestão de montar o `docker.sock` resolve?

Resolve só parcialmente. Ela ajuda o `n8n` a acessar o Docker host, mas sozinha não basta, porque o workflow também precisa das ferramentas de linha de comando dentro do container e de um modelo operacional consistente. Por isso a correção final incluiu imagem custom, socket e ajuste de volumes.

---

## 10. Como você lidou com a compatibilidade do TensorFlow?

Tratei isso como questão de plataforma. O stack completo com `tensorflow-text` não é bem suportado no Windows local deste ambiente, então a estratégia correta é separar execução:

- API, testes de contrato e validações leves localmente
- treino e pipeline ML completo via Docker/Linux

Isso é mais robusto e mais honesto do que tentar forçar compatibilidade total em qualquer ambiente.

---

## 11. Qual foi um bug de ambiente que você precisou corrigir?

A venv local estava inconsistente: `pydantic_core` tinha sido instalado com binário de outra versão de Python. Corrigi isso para viabilizar a execução do `pytest` no ambiente atual.

---

## 12. Os testes passaram?

Sim. Depois de reparar a venv local, rodei `python -m pytest` e a suíte passou com `12 passed`.

---

## 13. Existe algum ponto funcional ainda em aberto?

Sim. O maior ponto ainda aberto é terminar uma rodada completa de treino/publicação/deploy via `n8n` no ambiente alvo sem depender de observação manual. A divergência de direção da tradução já foi tratada no código e na documentação, alinhando o projeto para EN→PT, então o risco principal restante ficou concentrado no fechamento operacional do workflow.

---

## 14. Qual foi a principal postura técnica adotada?

Evitar gambiarra que “parece funcionar” e priorizar coerência operacional. Em vez de aceitar workarounds soltos, a ideia foi transformar os componentes já existentes em um fluxo realmente defensável para produção.

---

## 15. Se perguntarem “o que esse projeto demonstra sobre você?”, qual é a melhor resposta?

Que eu consigo pegar uma base já existente, identificar os riscos reais de operação, corrigir incrementalmente os pontos mais críticos e organizar a solução com foco em confiabilidade, rastreabilidade e deploy sustentável.
