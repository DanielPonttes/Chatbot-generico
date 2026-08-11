# Plano 08 — Contratos canônicos de contexto do agente

**Status:** Em implementação local — deploy bloqueado pelo gate de segurança da origem  
**Data:** 2026-08-11  
**Base:** [SPEC-007](../specs/07-canonical-data-contracts.md)

## Objetivo

Transformar dados reais de usuário, presença, telemetria, consumo e atividades
em contratos estáveis para o agente de notificações. A etapa não deve criar
valores sintéticos nem permitir que o modelo invente pontuação, ranking ou
estado de sensor.

## Evidência disponível

- `187.77.58.122:4343` aceita o protocolo PostgreSQL a partir da rede da 5090;
  não é uma API HTTP.
- O banco correto é `procel-analitical-db`. O schema `public` contém as tabelas
  `pessoa`, `atividade`, `missao`, `compartimento`, `sensor`, `medicao`,
  `parametro_def`, `parametro_valor` e `presenca`, entre outras.
- O catálogo agregado confirmou 2 pessoas, 2 sensores, 61 medições, 11
  definições de parâmetro, 33 missões, 5 atividades e 1 registro de presença;
  nenhuma linha pessoal foi registrada nas fixtures ou nos logs.
- O PostgreSQL está com `ssl=off` e a regra externa usa `scram-sha-256` para
  qualquer origem. A senha não é enviada em claro pelo SCRAM, mas os dados
  trafegam sem criptografia.
- A credencial fornecida é superusuária (`SUPERUSER`, `CREATEROLE` e
  `CREATEDB`); ela não pode ser configurada no chatbot.

## Mapa preliminar de fontes

| Domínio | Fonte esperada | Situação | Contrato candidato |
| --- | --- | --- | --- |
| Perfil | `public.pessoa` (`id`, `nome`) | schema confirmado; adapter implementado sem e-mail/telefone/senha | `CanonicalUserProfile` |
| Atividades | `public.atividade` + `public.missao` | schema confirmado; adapter implementado | `CanonicalActivities` |
| Telemetria de sensor | `public.medicao` + `parametro_valor` + `parametro_def` | schema confirmado; adapter implementado com unidades | `CanonicalTelemetry` |
| Telemetria de sala | sensores da sala + mesmas tabelas de medição | schema confirmado; adapter implementado | `CanonicalTelemetry` |
| Presença | `public.presenca` + capacidade de `public.compartimento` | agregado sem IDs de pessoas; adapter implementado | `CanonicalPresence` |
| Missões | `public.missao` + catálogo local V3 | schema confirmado; adapter implementado | `CanonicalMissions` |
| Parâmetros de regras | `public.parametro_def` | schema confirmado; adapter implementado | `CanonicalParameterDefinitions` |
| Pontuação/ranking | nenhuma fonte read-only confirmada | ausente | não implementar ainda |

## Fases de implementação

1. [x] Confirmar protocolo, banco, tabelas, tipos, unidades e timezone.
2. [x] Criar adapters com limite, erro de fonte, freshness e estado `empty`.
3. [x] Publicar schemas Pydantic e endpoints `/v1/context/*` protegidos por
   chave administrativa nesta primeira versão.
4. [ ] Criar papel PostgreSQL não privilegiado com `SELECT` apenas e habilitar
   TLS ou túnel privado.
5. [ ] Validar os endpoints no ambiente remoto com a credencial read-only.
6. [x] Integrar localmente o assembler de contexto ao
   `POST /v1/notifications/generate`, com opt-in administrativo, freshness
   obrigatória e rejeição de conflitos com dados da fonte. A publicação segue
   bloqueada pelos itens 4 e 5.

## Critérios de aceite

- Cada domínio possui uma fonte canônica confirmada e uma fixture sanitizada.
- Valores têm unidade, instante de observação e política de dados ausentes.
- Falha ou atraso da fonte gera estado explícito, nunca um valor inventado.
- PII é minimizada e não aparece em logs, prompts persistidos ou catálogo.
- Endpoints de leitura são autenticados; nesta etapa o escopo provisório é a
  chave administrativa até existir uma chave de leitura separada por identidade.
- Testes cobrem payload válido, payload incompleto, timeout, fonte indisponível
  e dados stale.

## Bloqueadores atuais

Não publicar a configuração de produção ainda. A origem aceita conexão sem TLS
e a única credencial disponível é superusuária. O próximo gate exige uma destas
opções:

- habilitar TLS no PostgreSQL e usar `REMOTE_PG_SSLMODE=require`; ou
- fornecer túnel/VPN privado entre a 5090 e o PostgreSQL.

Em ambos os casos, criar um papel como `procelbot_reader` com `NOSUPERUSER`,
`NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS` e `SELECT` apenas
nas tabelas necessárias. O chatbot não deve receber a senha do DBA.

## Próxima ação operacional

Corrigir o transporte seguro e provisionar a credencial limitada; depois
recriar somente o container `procelbot-chatbot`, validar os sete contratos e
executar a revisão automatizada e os smoke tests do assembler já integrado.
