# Plano 07 — Catálogo de missões e geração dedicada

**Status:** Concluído e publicado na 5090  
**Data:** 2026-08-11  
**Referência principal:** `MissõesXnotificaçõesV3.docx`

## Objetivo

Transformar a matriz de produto em um catálogo estável para o frontend, para
integrações e para o futuro orquestrador de eventos, sem confundir uma missão
de produto com um template de prompt já executável.

## Resultado do mapeamento

- 64 `mission_id`s únicos foram normalizados em
  `app/services/notification_missions.json`.
- Cada missão preserva categoria, subtipo, exemplo, entradas de outros
  componentes, entradas do agente e união das variáveis de contexto.
- 63 missões possuem mapeamento por subtipo para um template técnico atual.
- 1 missão (`mudanca_visivel`) permanece `catalog_only`, pois seu subtipo
  `Feedback em Tempo Real` ainda não possui template técnico equivalente.
- A resposta também informa `template_required_context_vars`; isso evidencia
  quais dados ainda precisam ser fornecidos além da matriz de missão.

## Endpoints implementados

| Método | Rota | Função |
| --- | --- | --- |
| GET | `/v1/notifications/missions` | Catálogo completo e versão da fonte |
| GET | `/v1/notifications/missions/{mission_id}` | Consulta de uma missão |
| POST | `/v1/notifications/generate` | Resolve missão, valida template e gera candidata |

Todos exigem a API key geral. A candidata gerada continua sendo persistida
como `Pendente`; aprovação/reprovação permanece administrativa.

## Contrato de contexto

O catálogo distingue:

- `component_inputs`: dados que devem vir de sensores, integrações ou regras de
  negócio externas;
- `agent_inputs`: dados que o agente deve derivar ou receber do contexto de
  geração;
- `template_required_context_vars`: variáveis exigidas pelo prompt técnico
  atual.

Essa separação evita que o agente invente pontuação, ranking, consumo ou estado
de sensor. O endpoint de geração rejeita contexto incompleto com `400` e uma
missão sem template com `409`.

## Limites desta etapa

Ainda não foram criados endpoints de perfil/gamificação, ingestão de eventos,
estado de missão ou entrega push. O documento define os nomes das variáveis,
mas não define de forma suficiente a tabela/fonte canônica, autorização do
usuário, idempotência, janela de disparo ou provedor de entrega. Esses
contratos serão uma etapa separada, usando o catálogo agora publicado como
referência.

## Critérios de aceite

- O catálogo contém exatamente 64 missões e nenhum `mission_id` duplicado.
- O OpenAPI mostra os três endpoints e os schemas de erro.
- `catalog_only` não chama o LLM e retorna `409`.
- Missão mapeada resolve o `template_id` sem exigir que o cliente duplique o
  ID técnico.
- `notification_type_id` informado manualmente não pode divergir do template
  associado à missão.
- Nenhum prompt interno, segredo ou dado pessoal é incluído no catálogo.
- Testes cobrem autenticação, lookup, resolução, mismatch e limites de contexto.

## Publicação e verificação

- Gate dos revisores: `PASS_WITH_WARNINGS`, sem bloqueadores.
- Suíte local: 107 testes aprovados; `git diff --check` aprovado.
- Backend publicado em `api.procel-chatbot.com` com catálogo autenticado:
  64 missões, 63 `mapped_template` e 1 `catalog_only`.
- Smoke tests externos: OpenAPI com autenticação, acesso sem chave retornando
  `401`, health `200` e `catalog_only` retornando `409` sem chamar o LLM.
- Containers `chatbot`, `proxy` e `ollama` confirmados em execução na 5090.

## Próxima etapa

1. Executar o [Plano 08 — Contratos canônicos de contexto](08-canonical-data-contracts.md)
   e confirmar primeiro as fontes de perfil, consumo, presença e atividades;
   pontuação/ranking só entram após uma fonte canônica ser encontrada.
2. Criar contratos de eventos com chave idempotente e timestamp de ocorrência.
3. Persistir estado de missão (`available`, `accepted`, `in_progress`,
   `completed`, `expired`) fora da tabela de candidatas.
4. Definir preferências, consentimento, canal e provedor de entrega.
