# SPEC-006 — Catálogo de missões e geração dedicada

**Status:** Accepted  
**Escopo:** contrato v1 para as missões do documento V3 e geração de uma
notificação candidata.

## 1. Fonte e versionamento

A fonte de produto é `MissõesXnotificaçõesV3.docx`. O snapshot versionado no
repositório é `app/services/notification_missions.json`, com
`catalog_version=2026-08-11` e 64 missões.

O `mission_id` é um identificador técnico estável em snake_case. Alterações no
nome exibido não devem renomeá-lo sem migração explícita.

## 2. Catálogo

`GET /v1/notifications/missions` retorna:

- `mission_id`, `name`, `category` e `subtype`;
- `template_id` e `execution_status`;
- exemplo da matriz;
- `component_inputs`, `agent_inputs` e `context_variables`;
- `template_required_context_vars`, derivadas do template executável atual.

`execution_status` pode ser:

- `mapped_template`: há um template técnico associado;
- `catalog_only`: a missão está documentada, mas não pode ser gerada pela API.

O endpoint de item (`GET /v1/notifications/missions/{mission_id}`) retorna
`404 mission_not_found` quando o ID não existe.

## 3. Geração

`POST /v1/notifications/generate` recebe o contrato de geração proativa atual
mais `mission_id`:

```json
{
  "mission_id": "sala_vazia_luz_off",
  "persona_id": "motivador",
  "notification_context": {
    "anomaly_window": "últimas 2 horas",
    "measured_consumption_kwh": 8.4,
    "expected_consumption_kwh": 5.2,
    "room_id": "sala-204",
    "potential_wasted_kwh": 3.2,
    "recommended_action": "apagar a iluminação"
  }
}
```

O servidor resolve `template_id` pelo catálogo. Se o cliente enviar
`notification_type_id`, ele deve coincidir com o mapeamento; caso contrário,
responde `400 mission_template_mismatch`.

Respostas relevantes:

| Código | Erro | Significado |
| --- | --- | --- |
| 400 | `validation_error` | contexto incompleto para o template |
| 400 | `mission_template_mismatch` | ID técnico divergente |
| 404 | `mission_not_found` | missão inexistente |
| 409 | `mission_not_executable` | missão `catalog_only` |

Missões geradas continuam no fluxo Human in the Loop como `Pendente`.

## 4. Segurança

- Todos os endpoints exigem `X-API-Key`.
- Nenhum endpoint novo expõe prompt interno ou credencial.
- O catálogo não consulta PostgreSQL, Spring ou Ollama.
- O endpoint de geração mantém os limites de corpo e de contexto da SPEC-002.
- O endpoint não realiza entrega externa nem aceita URL/callback fornecida pelo
  cliente.

## 5. Fora do escopo

Esta especificação não cria ainda:

- endpoint canônico de perfil, pontuação ou ranking;
- ingestão de eventos de sensores;
- estado persistente de missão;
- preferências, consentimento ou entrega push.

Esses recursos dependem de decisões sobre fonte de verdade, autorização,
idempotência e provedor de entrega. Os campos `component_inputs` e
`agent_inputs` registram essa dependência sem simular dados.

## 6. Aceite e rollback

O aceite exige catálogo com 64 itens, testes de autenticação e resolução,
OpenAPI com schemas de erro, e nenhum impacto nos endpoints legados ou em
`POST /v1/chat/proactive`.

Rollback: remover os endpoints novos e o carregador do catálogo, mantendo o
contrato anterior de templates e candidatas. O JSON versionado pode permanecer
no repositório sem ser publicado pela API.
