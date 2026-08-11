# Plano 03 — Agente local de métricas da RTX 5090

**Status:** Concluído — implementação, revisão e publicação validadas  
**Base:** `SPEC-004`  
**Objetivo:** fornecer telemetria operacional local sem custo de API e sem
interferir no uso principal da GPU.

## Decisão

Usar um agente Python somente com biblioteca padrão, executado pelo systemd
como `procelbot`. A cada 30 segundos ele consulta `/proc`, `nvidia-smi` e
`systemctl`, grava um snapshot JSON atômico e termina cada ciclo. Não haverá
servidor HTTP no agente, acesso ao Docker socket, chamada ao Gemini ou coleta
de logs/processos.

## Etapas e checkpoints

| Etapa | Entrega | Checkpoint |
| --- | --- | --- |
| 1 | Contrato e ameaça | `SPEC-004` revisada; campos sem segredos |
| 2 | Coletor e unit systemd | `--once`, JSON válido e permissões verificadas |
| 3 | Leitor no backend | somente `/v1/admin/status`; health público inalterado |
| 4 | Testes | teste fresco, inválido, ausente e stale; suite completa |
| 5 | Publicação na 5090 | serviço ativo, snapshot atualizado e smoke HTTP |
| 6 | Revisão | `scripts/agent_review.sh gate --run-tests`; documentação fechada |

## Evidência de conclusão

- `pytest`: 86 passed, 1 warning legado do `TestClient`/httpx;
- gate dos revisores: `GATE: PASS`;
- `procelbot-node-metrics.service`: `active` e `enabled` na RTX 5090;
- snapshot do host: proprietário `procelbot`, modo `0644`, JSON válido;
- `appuser` do container leu o bind mount `:ro` com sucesso;
- `/v1/admin/status` autorizado: HTTP 200, snapshot fresco e uma GPU;
- smoke público: health HTTP 200, admin sem chave HTTP 401 e Swagger sem
  autenticação HTTP 401.

## Configuração operacional

- intervalo do coletor: 30 s;
- TTL aceito pelo backend: 60 s;
- limite do snapshot: 128 KiB;
- diretório no host: `/var/lib/procelbot/node-metrics`;
- arquivo no container: `/run/procelbot/node-metrics/latest.json` em modo `ro`.

## Rollback

1. parar e desabilitar `procelbot-node-metrics.service`;
2. remover o bind mount do compose e recriar somente o container do backend;
3. manter o endpoint administrativo sem `node_metrics` ou reverter a versão da
   aplicação para o commit anterior;
4. não apagar o diretório do snapshot sem validar que não é usado por outra
   versão.

## Próxima etapa

Depois de validar a telemetria, definir o painel administrativo atrás do
Cloudflare Access. Um eventual sumarizador LLM será opcional, assíncrono e
separado do caminho de coleta; a disponibilidade do Gemini não será requisito
para exibir o status do servidor.
