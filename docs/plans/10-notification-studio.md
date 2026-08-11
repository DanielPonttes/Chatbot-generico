# Plano 10 — Notification Studio

**Status:** Concluído  
**Data:** 2026-08-11  
**Base:** [SPEC-009](../specs/09-notification-studio.md)

## Entrega

- [x] revisar o painel e os contratos existentes;
- [x] consultar o Kimi K3 via Cursor para arquitetura e direção visual;
- [x] criar `notifications.html`, `notifications.css` e `notifications.js` sem
  dependências externas;
- [x] adicionar navegação no Control Room;
- [x] criar allowlist de proxy server-side no Caddy;
- [x] fixar `use_canonical_context=false`;
- [x] implementar catálogo, contexto dinâmico, preview e fila de revisão;
- [x] falhar fechado quando a candidata não puder ser persistida;
- [x] cobrir desktop, mobile, aprovação, reprovação e erros em Playwright;
- [x] aplicar achados da revisão do Kimi K3;
- [x] publicar e executar smoke tests no neuromancer.

## Direção do Kimi K3

O Kimi recomendou preservar o design system “Control Room” e dar à página uma
identidade de laboratório editorial em violeta/ciano, com preview de celular
como elemento central. A recomendação também definiu assets locais, DOM sem
HTML dinâmico, estados acessíveis e proxies dentro do bloqueio do Cloudflare
Access. A revisão inicial retornou `PASS_WITH_WARNINGS`; todos os achados
concretos foram corrigidos e a reverificação retornou `PASS`.

## Operação do time

1. autorizar os e-mails do time no Cloudflare Access;
2. abrir `https://admin.procel-chatbot.com/notifications`;
3. escolher persona, perfil e missão;
4. usar somente valores fictícios ou o botão de preenchimento de exemplo;
5. gerar a candidata e registrar aprovação ou reprovação;
6. não usar a tela como mecanismo de entrega push.

O banco remoto, o túnel e o snapshot canônico não participam deste fluxo.

