# Documentacao do Frontend

O frontend e composto por HTML estatico servido pelo FastAPI em `app/static/`. Nao ha framework SPA; as paginas usam JavaScript no proprio arquivo, Tailwind via CDN e Lucide Icons.

## Rotas Visuais

| Rota | Arquivo | Uso |
| --- | --- | --- |
| `/` | `app/static/index.html` | Chat principal. |
| `/notifications` | `app/static/notifications.html` | Geracao e avaliacao de notificacoes. |
| `/rag` | `app/static/rag.html` | Visualizacao de busca RAG. |

## Chat Principal

Rota: `/`

Funcionalidades:

- Envio de mensagens para `POST /chat`.
- Historico visual da sessao atual.
- Indicador de status do provider via `GET /health`.
- Modal de configuracao com override de modelo.
- Navegacao para notificacoes e RAG.

Fluxo:

1. Usuario digita mensagem.
2. JS envia `{ session_id, message, model_override }` para `/chat`.
3. Backend recupera historico, chama provider LLM e salva a troca na memoria.
4. UI renderiza a resposta.

## Teste de Notificacoes

Rota: `/notifications`

Esta tela testa o fluxo de notificacoes proativas e persiste feedback.

### Controles Principais

- Dropdown de persona (`/personas`).
- Dropdown de perfil-alvo (`/target-profiles`).
- Botao para gerar notificacao (`/chat/proactive`).
- Botoes de aprovar/reprovar.
- Modal de notificacoes salvas.
- Modal de configuracao.

### Modal de Configuracao

Permite ajustar:

- modelo LLM (`model_override`);
- prompt da persona (`persona_override.system_prompt`);
- toggle de RAG (`use_rag`);
- sala (`room_id`);
- sensor (`sensor_external_id`);
- pessoa (`pessoa_id`).

Os campos de sala, sensor e pessoa usam autocomplete:

- `/integrations/context/rooms`
- `/integrations/context/sensors`
- `/integrations/context/people`

### Geracao

Payload enviado para `/chat/proactive`:

```json
{
  "persona_id": "provocador",
  "target_profile_id": "gastao",
  "model_override": null,
  "use_rag": true,
  "room_id": "2",
  "sensor_external_id": "SII-001",
  "pessoa_id": "ravilon",
  "persona_override": null
}
```

O backend tambem suporta `notification_type_id` e `notification_context`. A tela atual nao expoe um seletor dedicado para esses campos, mas o endpoint ja aceita o payload para integracoes futuras.

### Resultado

A UI mostra:

- texto da notificacao;
- persona usada;
- modelo usado;
- `context_summary`, quando o backend aplicou contexto operacional.

### Feedback e Historico

Aprovacao/reprovacao chama `PATCH /notifications/saved/{id}` com a chave administrativa. O `POST /notifications/saved` cria somente candidatos `Pendente`; o backend tambem salva automaticamente cada geracao proativa como `Pendente`.

O modal de salvas usa:

- `GET /notifications/saved`;
- `DELETE /notifications/saved/{id}`;
- `DELETE /notifications/saved/all`.

As abas filtram:

- `Aprovada`;
- `Reprovada`.

Notificacoes `Pendente` existem no backend para avaliacao, mas a UI atual foca na lista de feedback aprovado/reprovado.

## Visualizador RAG

Rota: `/rag`

Funcionalidade:

- envia consultas para `POST /rag/search`;
- exibe chunks retornados;
- mostra origem, pagina e score.

Dependencias:

- base Chroma em `data/chroma_db/`;
- embeddings Google configurados via `GEMINI_API_KEY` ou `GOOGLE_API_KEY`.

## E2E com Playwright

Arquivos:

- `tests/e2e/notifications.spec.js`;
- `tests/e2e/helpers/notifications-mocks.js`;
- `playwright.config.js`.

Cenarios cobertos:

- carregamento inicial;
- configuracao em viewport menor;
- geracao de notificacao;
- persistencia de feedback aprovado;
- tratamento de erro.

Execucao:

```bash
npm run test:e2e
```

O teste mocka as rotas principais da tela de notificacoes, entao nao depende de LLM, PostgreSQL remoto nem Spring Boot para validar a experiencia.

## Tecnologias

- HTML5.
- TailwindCSS via CDN.
- Lucide Icons.
- JavaScript vanilla.
- Playwright para E2E.

## Pontos de Atencao

- As paginas estaticas usam chamadas relativas ao mesmo host do FastAPI.
- `API_BASE` em `notifications.html` usa `window.location.origin`.
- A autenticacao ainda nao existe; em producao, proteja os endpoints e restrinja CORS.
- A tela de notificacoes ainda pode evoluir para expor `notification_type_id` e `notification_context` diretamente.
