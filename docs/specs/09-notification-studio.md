# SPEC-009 — Notification Studio administrativo

**Status:** Accepted  
**Base:** SPEC-005 e SPEC-006  
**Escopo:** emular, gerar e revisar notificações com dados fictícios

## 1. Objetivo

Disponibilizar ao time um frontend visual para experimentar personas, perfis,
missões e contexto manual sem depender do PostgreSQL remoto e sem enviar push
para usuários. A página pública de operação é:

```text
https://admin.procel-chatbot.com/notifications
```

O acesso exige uma identidade autorizada no Cloudflare Access.

## 2. Experiência

O Studio oferece:

- catálogo pesquisável de missões que possuem template executável;
- seleção de persona e perfil de público;
- formulário de contexto criado dinamicamente a partir do contrato da missão;
- preenchimento de exemplo com valores explicitamente fictícios;
- preview de push em uma moldura de celular;
- geração real pelo Ollama local;
- fila persistida de candidatas pendentes;
- aprovação ou reprovação humana;
- estados de loading, erro, vazio e viewport móvel.

A geração sempre envia `use_canonical_context=false`. Não existem seletores de
pessoa, presença, sala real ou sensor real no frontend.

## 3. Segurança

- HTML, CSS, JavaScript e SVG são locais; não há CDN ou dependência de runtime;
- nenhum segredo, API key ou assertion do Access chega aos assets do navegador;
- o Caddy exige `Cf-Access-Jwt-Assertion` antes de qualquer proxy;
- cookies, `Authorization` e a assertion do Access são removidos antes do
  upstream;
- a chave administrativa é injetada apenas entre Caddy e FastAPI;
- a allowlist aceita somente catálogo por `GET`, geração por `POST` e revisão
  por `PATCH`; rotas fora do escopo terminam em `404`;
- conteúdo retornado pela API entra no DOM com `textContent`/`createElement`;
- candidatas geradas não são entregues como push.

## 4. Arquitetura

```text
Navegador do time
      │ Cloudflare Access
      ▼
admin.procel-chatbot.com/notifications
      │ assets locais + fetch same-origin
      ▼
Caddy (allowlist + chave server-side)
      │
      ▼
FastAPI /v1/notifications/*
      │
      ├── Ollama / gemma4:26b
      └── SQLite de candidatas e pareceres
```

## 5. Critérios comprovados

- [x] Página e assets respondem no domínio administrativo.
- [x] Ausência de sessão Access bloqueia o origin e redireciona no hostname
  público.
- [x] Catálogos, geração e revisão funcionam sem chave no browser.
- [x] Payload fixa `use_canonical_context=false`.
- [x] Contexto obrigatório é validado antes da geração.
- [x] Falha de persistência retorna erro fechado em vez de candidata órfã.
- [x] Aprovação, reprovação, filtros e falha de revisão possuem cobertura E2E.
- [x] Layout desktop e mobile foram inspecionados em navegador real.
- [x] Kimi K3 via Cursor revisou arquitetura e implementação; revisão final
  `PASS`.

## 6. Validação executada

- `156 passed` no conjunto Python completo após os hardenings;
- `9 passed` no conjunto E2E completo, incluindo 5 cenários do Studio;
- `node --check` para o JavaScript;
- `caddy validate` para a configuração;
- smoke remoto: health, página, catálogo e status administrativo `200`;
- smoke ponta a ponta: geração `200` e revisão `200` com dados fictícios;
- rotas sem Access ou fora da allowlist: `403`/`404`.

As chaves internas da API foram rotacionadas durante a publicação e permanecem
somente nos arquivos protegidos do backend e do proxy.

## 7. Rollback

1. restaurar `Caddyfile`, `admin/index.html` e o pacote `app` do backup local de
   implantação;
2. remover os três assets `notifications.*` do diretório administrativo;
3. reconstruir somente `procelbot-chatbot`;
4. recriar somente `procelbot-proxy`;
5. validar `/v1/health` e o painel operacional anterior.
