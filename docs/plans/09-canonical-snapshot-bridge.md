# Plano 09 — Ponte local de snapshots canônicos

**Status:** Implementado localmente; publicação aguardando túnel SSH/VPN  
**Data:** 2026-08-11  
**Base:** [SPEC-008](../specs/08-canonical-snapshot-bridge.md)

## Entregas locais

1. exportador com consultas fixas e transação `REPEATABLE READ, READ ONLY`;
2. allowlist de campos e métricas, sem credenciais ou PII desnecessária;
3. arquivo JSON atômico, modo `0640` e schema versionado;
4. repositório backend com proteção contra symlink/tamanho/schema;
5. freshness baseada em `generated_at`;
6. unit systemd endurecida e credencial em ambiente separado;
7. compose sem senha PostgreSQL e bind mount `:ro`;
8. testes unitários e documentação de instalação/rollback.

## Gate de publicação

- confirmar um endpoint SSH/bastion ou VPN que alcance `187.77.58.122:4343`;
- verificar o fingerprint SSH por um canal confiável;
- criar usuário/grupo host `procelbot-context` e compartilhar somente seu GID
  com o container;
- executar o sincronizador uma vez e inspecionar apenas schema, permissões e
  contagens;
- remover toda credencial `REMOTE_PG_PASSWORD` do `backend.env`;
- validar os sete endpoints e a geração opt-in com chave administrativa;
- executar Grok 4.5 e Kimi K3 sobre a configuração final sem fornecer segredos.
