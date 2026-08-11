# SPEC-004 — Agente local de métricas do host

**Status:** Accepted  
**Escopo:** telemetria operacional mínima do servidor da RTX 5090 para o
endpoint administrativo.

## 1. Objetivo

Disponibilizar CPU, memória, disco, GPU e estado dos serviços do host para o
futuro painel restrito, sem criar outro endpoint público e sem usar um modelo
externo para coletar métricas.

O agente é um processo local no host da GPU. Ele não executa inferência, não
abre porta, não acessa a internet e não monta o Docker socket. A coleta da GPU
é uma consulta de telemetria ao driver NVIDIA, com intervalo de 30 segundos,
sem reservar VRAM ou executar kernels de CUDA.

## 2. Arquitetura e limites

```text
/proc + nvidia-smi + systemctl
             │
             ▼
procelbot-node-metrics.service (usuário procelbot)
             │ grava atomicamente, 0644
             ▼
/var/lib/procelbot/node-metrics/latest.json
             │ bind mount somente leitura
             ▼
procelbot-chatbot ── GET /v1/admin/status (ADMIN_API_KEY)
```

O backend lê somente o snapshot montado em
`/run/procelbot/node-metrics/latest.json`. Se o arquivo estiver ausente,
inválido ou acima do limite de idade, o status administrativo continua
respondendo e `node_metrics` será `null` ou conterá `fresh: false`, conforme o
caso. O health público não recebe essas métricas.

O futuro uso de Gemini, se houver, poderá resumir incidentes ou sugerir
interpretações em uma camada posterior. Ele não faz parte do coletor e não é
necessário para o painel mostrar os números.

## 3. Contrato do snapshot

O agente grava `schema_version: 1` e os seguintes grupos de campos:

- identificação e tempo: `collected_at`, `hostname`, `host_uptime_seconds`;
- CPU/memória/disco: percentuais e bytes, com caminho de disco limitado a `/`;
- GPU: índice, nome, utilização, memória, temperatura e potência;
- serviços: estados resumidos de Docker, backend, stack Ollama e cloudflared.

O backend rejeita schema desconhecido, JSON inválido, arquivo maior que 128 KiB
e campos que não passam pela validação Pydantic. A publicação usa arquivo
temporário no mesmo diretório, `fsync` e `os.replace`, impedindo que o backend
leia JSON parcialmente escrito.

## 4. Modelo de ameaça

- O processo FastAPI não recebe privilégio para controlar Docker ou systemd.
- O agente roda como `procelbot`, com `NoNewPrivileges`, `ProtectSystem` e
  `ProtectHome`; seu único caminho de escrita é o diretório do snapshot.
- O diretório do snapshot usa modo `755` e o arquivo `644` para que o
  `appuser` não-root criado no container possa atravessar o bind mount
  somente leitura; o conteúdo é limitado a telemetria não sensível.
- O snapshot não deve conter tokens, senhas, IPs públicos, comandos, logs ou
  conteúdo de processo.
- `node_metrics` aparece somente no endpoint já protegido por
  `ADMIN_API_KEY`; o navegador do futuro painel não receberá a chave.
- O intervalo de 30 s reduz consultas ao driver e mantém impacto operacional
  desprezível para workloads que utilizam a RTX 5090.

## 5. Critérios de aceite

- uma execução `--once` produz JSON válido com schema 1;
- o serviço systemd mantém o snapshot atualizado a cada 30 s;
- o backend valida um snapshot fresco e marca um snapshot antigo como
  `fresh=false`;
- timestamps do snapshot no futuro marcam `fresh=false` e `clock_skew=true`;
- `/v1/admin/status` retorna o snapshot somente com a chave administrativa;
- `/v1/health` não contém `node_metrics`;
- não existe listener HTTP adicional nem bind mount do Docker socket;
- falhas de `nvidia-smi` tornam `gpu_available=false` sem derrubar o agente;
- o rollback remove o unit file e o bind mount, sem alterar Ollama, Caddy ou
  o Tunnel.
