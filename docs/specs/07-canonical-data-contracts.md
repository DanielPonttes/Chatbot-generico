# SPEC-007 — Contratos canônicos de contexto

**Status:** In progress — adapters e assembler locais implementados; deploy bloqueado por TLS e privilégio da origem  
**Escopo:** dados reais usados para preencher missões e notificações

## 1. Objetivo

Definir a fronteira entre dados fornecidos por sistemas Procel e dados que o
agente pode derivar. A especificação cobre apenas leitura e normalização; não
cria eventos, altera cadastro, registra presença ou envia notificações.

## 2. Domínios

Os primeiros domínios são:

- perfil mínimo do usuário;
- atividades e resumo de progresso;
- última telemetria de sensor ou sala;
- presença atual e presenças abertas;
- missões remotas, se a fonte for confirmada;
- pontuação, ranking e conquistas somente quando houver fonte canônica.

Cada resposta normalizada deverá carregar, no mínimo, origem, identificador de
escopo, `observed_at`/`as_of`, freshness e estado da fonte. Os nomes finais e
tipos ainda dependem das respostas reais.

## 3. Fonte canônica confirmada

O endereço analisado fala PostgreSQL na porta `4343`, usando o banco
`procel-analitical-db`. O schema relevante confirmado é:

```text
public.pessoa
public.atividade
public.missao
public.compartimento
public.sensor
public.medicao
public.parametro_def
public.parametro_valor
public.presenca
```

Os endpoints Spring abaixo continuam catalogados como uma fonte futura, mas
não são usados pelos adapters canônicos enquanto não houver uma origem HTTP
alcançável e payload validado:

```text
GET /api/pessoas/{pessoa_id}
GET /api/pessoas/{pessoa_id}/atividades
GET /api/pessoas/{pessoa_id}/atividades/resumo
GET /api/sensors/{sensor_external_id}/medicoes/latest
GET /api/sensors/{sensor_external_id}/medicoes
GET /api/rooms/{room_id}/medicoes/latest
GET /api/rooms/{room_id}/medicoes
GET /api/presencas/ocupacao/compartimentos/{room_id}
GET /api/presencas/abertas/compartimentos/{room_id}
GET /api/missoes
GET /api/missoes/{missao_id}
GET /api/rules/parameter-defs
```

A existência no catálogo não equivale a disponibilidade. A porta HTTP testada
não respondeu; a fonte PostgreSQL foi encontrada e lida somente durante a
análise. O servidor está com TLS desligado, então nenhum segredo foi salvo no
backend.

## 4. Contrato de leitura proposto

As rotas abaixo estão implementadas localmente, mas ficam protegidas por chave
administrativa e não devem ser liberadas para produção até o gate de transporte
seguro e credencial read-only:

| Rota proposta | Fonte | Escopo |
| --- | --- | --- |
| `GET /v1/context/users/{user_id}/profile` | `public.pessoa` | identidade mínima |
| `GET /v1/context/users/{user_id}/activities` | `public.atividade` + `missao` | progresso observável |
| `GET /v1/context/rooms/{room_id}/telemetry/latest` | `medicao` + `parametro_valor` | consumo/telemetria |
| `GET /v1/context/sensors/{sensor_id}/telemetry/latest` | `medicao` + `parametro_valor` | leitura instantânea |
| `GET /v1/context/rooms/{room_id}/presence` | `public.presenca` + `compartimento` | presença agregada |
| `GET /v1/context/missions` | `public.missao` | descoberta |
| `GET /v1/context/rules/parameter-definitions` | `public.parametro_def` | regras sem valores |

Pontuação, ranking e conquistas ficam sem rota até haver fonte, unidade,
permissão e regra de atualização confirmadas.

## 5. Segurança e falhas

- API key administrativa obrigatório nesta fase; substituir por escopo de
  leitura separado antes de abrir para consumidores externos.
- Nenhuma resposta deve carregar senha, token, prompt, telefone ou e-mail por
  padrão.
- Timeout e indisponibilidade retornam `503 context_source_unavailable`; um
  identificador inexistente retorna `404 context_not_found`, e uma consulta
  sem medição retorna `status=empty`. Nunca retornam zero como se fosse valor
  real.
- Dados stale devem informar `fresh=false` e o instante da última leitura.
- Para presença, `fresh` descreve o snapshot agregado consultado em `as_of`;
  um check-in aberto antigo continua sendo ocupação corrente. O último evento
  permanece disponível em `latest_event_at`, e timestamps futuros invalidam a
  freshness com `clock_skew=true`.
- `occupancy_pct` pode ultrapassar 100 quando a fonte registrar superlotação;
  o valor não é artificialmente limitado.
- Os adapters canônicos recusam transporte PostgreSQL sem TLS; aceitam
  `REMOTE_PG_SSLMODE=require`, `verify-ca` ou `verify-full`, mesmo fora do modo
  de produção.
- O agente não pode escrever nas fontes nem chamar endpoints com efeito lateral.

## 6. Aceite e dependências

O código local possui schemas, adapters, unidades e testes para perfil,
atividades, telemetria, presença, missões, parâmetros, freshness, ausência,
falha de fonte e redaction de campos pessoais. O aceite de produção ainda exige
TLS/túnel privado, papel não privilegiado e validação remota dos sete contratos.

### 6.1 Integração local com geração

`POST /v1/notifications/generate` aceita `use_canonical_context=true` como
opt-in. Nesse modo:

- a chamada exige chave administrativa, como os endpoints `/v1/context/*`;
- `pessoa_id`, `room_id` e `sensor_external_id` selecionam apenas adapters
  canônicos;
- somente snapshots `fresh` são usados; `stale`, `empty` e clock skew falham
  fechado antes de chamar o LLM;
- apenas campos conhecidos pela missão ou pelo template são propagados;
- valores fornecidos que divirjam da fonte retornam
  `409 canonical_context_conflict`, sem precedência silenciosa;
- o contexto combinado é revalidado contra 32 chaves e 8 KiB;
- o enriquecedor operacional legado não é chamado novamente nesse fluxo.
- `prompt_used` não é persistido, pois pode conter o nome mínimo e telemetria;
- a auditoria registra apenas o ID técnico da candidata, nomes dos campos e
  tipos de fonte, sem IDs de pessoa, sala ou sensor.

O assembler não cria baseline, ranking, recompensas, progresso ou valores de
consumo derivados. Essas variáveis continuam obrigatórias no payload até que
exista fonte e regra canônica confirmada.

Como alternativa à conexão direta, a [SPEC-008](08-canonical-snapshot-bridge.md)
define uma ponte host isolada. Nesse modo, o backend lê um snapshot sanitizado
e não recebe host, usuário ou senha do PostgreSQL.
