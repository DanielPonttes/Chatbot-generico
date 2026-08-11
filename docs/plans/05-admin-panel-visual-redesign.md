# Plano 05 — Redesign visual do painel administrativo

**Status:** Concluído  
**Base:** `SPEC-005`  
**Objetivo:** transformar o painel operacional em uma interface NOC mais clara,
responsiva e útil para acompanhar a RTX 5090 sem alterar contratos ou controles
de segurança.

## Direção visual

O Kimi K3 foi consultado pelo Cursor CLI e recomendou uma estética de
“Control Room”: GPU como protagonista, gauges para percentuais, semáforos de
severidade, números tabulares, estados stale/offline explícitos e countdown da
próxima coleta.

## Escopo implementado

- sidebar responsiva com navegação para visão geral e Swagger;
- hero da GPU com nome, temperatura, utilização, VRAM e potência;
- cards de provider, modelo, uptime e frescor do snapshot;
- barras de CPU, memória e disco;
- lista de serviços com estado e indicadores acessíveis;
- telemetria detalhada para cada GPU;
- countdown da próxima leitura e estados de loading, erro e stale;
- somente HTML, CSS e JavaScript locais, sem CDN ou dependência adicional.

## Invariantes

- `/api/status`, `/swagger` e o polling de 30 segundos permanecem inalterados;
- nenhum segredo é incluído nos assets;
- dados da API continuam sendo inseridos com `textContent` e nós DOM;
- Cloudflare Access, Caddy, Tunnel e backend não fazem parte do escopo visual.

## Validação

- `node --check deploy/procelbot/admin/admin.js`;
- testes estáticos do painel;
- smoke remoto com Access: sem asserção → 403; com asserção → painel 200;
- smoke remoto de `/api/status`, `/swagger` e `/openapi.json` → 200.

## Próxima revisão

Após feedback visual, avaliar gráficos históricos e uma navegação específica
para o fluxo de notificações. O CSP do Swagger continua como hardening separado,
pois a UI do FastAPI ainda usa o asset CDN padrão.
