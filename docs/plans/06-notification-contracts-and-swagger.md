# Plano 06 — Contratos de notificações e Swagger

**Status:** Incremento 1 concluído e publicado na 5090  
**Data:** 2026-08-10  
**Escopo:** transformar o documento de notificações em um contrato de descoberta
para a API FastAPI, sem declarar como executáveis recursos que ainda não têm
template, fonte de dados ou fluxo de entrega implementado.

## Referências usadas

- [MissõesXnotificaçõesV3.docx](https://drive.google.com/file/d/1TJ5vFOJJocIgNxzWpzRktlYdNLcULBGO/view): matriz de 64 missões, categorias, subtipos e variáveis de contexto.
- [2026-junho-notificações.docx](https://drive.google.com/file/d/1AaPNAG2u1iypYD-H_5jXiNXkPvZbn6WD/view): taxonomia inicial, exemplos de mensagens e fontes de contexto.
- [SPEC-002 — Segurança e contratos da API pública](../specs/02-public-api-security-and-contracts.md): versionamento, autenticação e revisão humana.

## Decisão de contrato

O documento V3 descreve 64 missões de produto, mas o backend atual possui 11
templates técnicos reutilizáveis. A API não vai transformar cada nome de missão
em um `notification_type_id` antes de existir um template versionado e um
contrato para fornecer seus dados.

O primeiro incremento expõe os 11 templates executáveis e permite que os
consumidores descubram, em runtime:

- `id` técnico usado em `notification_type_id`;
- categoria e subtipo alinhados à taxonomia do documento;
- variáveis obrigatórias e todos os slots do prompt;
- se o RAG é ativado por padrão.

O contexto permanece um objeto extensível, limitado a 32 chaves e 8 KiB
serializados. O Swagger documenta grupos de variáveis de usuário/recompensa,
missão/progresso, localização, telemetria interna, contexto externo/baselines e
ranking/conquistas. A lista exata por template é retornada por
`GET /v1/notifications/types`.

## Implementado neste incremento

- `GET /v1/notifications/types` protegido por `X-API-Key`.
- Metadados de categoria e subtipo no catálogo interno de templates.
- Tag `notifications` no Swagger.
- Exemplos de contexto para missão e alerta de consumo.
- Schemas OpenAPI explícitos para criação, revisão e remoção de notificações.
- Descrições de que a geração cria uma candidata `Pendente`; entrega push e
  disparo por eventos ainda não fazem parte da API v1.

## Superfície documentada

| Método | Rota | Papel | Acesso |
| --- | --- | --- | --- |
| GET | `/v1/notifications/types` | Descobrir templates e variáveis | API key |
| POST | `/v1/chat/proactive` | Gerar e persistir candidata | API key |
| GET | `/v1/notifications/saved` | Listar candidatas e revisões | API key |
| POST | `/v1/notifications/saved` | Criar candidata manual | API key |
| PATCH | `/v1/notifications/saved/{id}` | Aprovar/reprovar | chave administrativa |
| DELETE | `/v1/notifications/saved/{id}` | Remover uma candidata | chave administrativa |
| DELETE | `/v1/notifications/saved/all` | Limpar candidatas | chave administrativa |

## Critérios de aceite do incremento 1

- O catálogo aparece apenas com caminhos `/v1` no OpenAPI.
- O catálogo não expõe `system_prompt_template` nem credenciais.
- Cada template possui categoria, subtipo e `required_context_vars` válidos.
- O contexto aceita campos específicos das missões sem perder o limite de
  tamanho ou a validação de valores JSON.
- Criação pública continua forçada a `Pendente`.
- Aprovação, reprovação e exclusão continuam exigindo a chave administrativa.
- Testes verificam autenticação, catálogo e exemplos de contexto.

## Próximos incrementos

1. Criar um `mission_id` estável e um catálogo normalizado para as 64 missões,
   relacionando cada missão a um template e a seus campos de entrada.
2. Definir contratos de leitura para perfil, pontuação, ranking e telemetria,
   separando dados fornecidos por outros componentes dos dados derivados pelo
   agente.
3. Definir eventos de disparo, deduplicação, preferências e janela de entrega.
4. Criar o endpoint de entrega/encaminhamento somente depois de definir o
   provedor de push e a autorização do destinatário.
5. Adicionar avaliação humana e métricas de qualidade sem registrar prompts ou
   dados pessoais desnecessariamente.
