# SPEC-008 — Ponte local de snapshots canônicos

**Status:** In progress — implementação local concluída; ativação depende de túnel SSH/VPN  
**Base:** SPEC-007  
**Escopo:** remover credenciais PostgreSQL do chatbot sem alterar o banco remoto

## 1. Objetivo

Sincronizar os sete contratos canônicos para um arquivo local sanitizado. Um
processo host isolado é a única peça que recebe a credencial PostgreSQL; o
backend recebe somente um bind mount read-only.

## 2. Arquitetura

```text
PostgreSQL sem TLS
        │
        │ túnel SSH/VPN criptografado
        ▼
127.0.0.1:5433
        │
        ▼
procelbot-context-sync (transação READ ONLY)
        │ escrita atômica 0640
        ▼
/var/lib/procelbot/canonical-context/latest.json
        │ bind mount :ro + GID dedicado
        ▼
container chatbot (sem REMOTE_PG_PASSWORD)
```

## 3. Dados permitidos

- perfil: `id` e `nome`;
- atividades: IDs, status, timestamps e metadados mínimos da missão;
- salas: `id`, `nome` e `capacidade`;
- presença: somente agregados por sala, sem IDs de pessoas;
- telemetria: última medição por sala/sensor e allowlist de métricas;
- missões e definições de parâmetros canônicas.

O snapshot não contém host, porta, banco, usuário, senha, e-mail, telefone,
matrícula ou linhas individuais de presença.

## 4. Segurança e falhas

- a primeira instrução do ciclo define `REPEATABLE READ, READ ONLY`, garantindo
  uma visão consistente para o código fixo do sincronizador;
- `sslmode=disable`, `allow` ou `prefer` só é aceito para loopback;
- conexões remotas exigem `require`, `verify-ca` ou `verify-full`;
- o sincronizador registra apenas tipo da falha e contagens sanitizadas;
- falha de sincronização preserva o último arquivo válido;
- escrita usa arquivo temporário, `fsync`, modo `0640` e `os.replace`;
- o leitor recusa symlink, arquivo não regular, JSON inválido, versão desconhecida
  e tamanho superior ao limite;
- `generated_at` controla freshness. Sincronizador parado produz `stale`, nunca
  dados aparentemente atuais.

## 5. Critérios de aceite

- [x] Backend opera com `CANONICAL_CONTEXT_SOURCE=snapshot`.
- [x] Backend não precisa de nenhuma variável `REMOTE_PG_*` sensível.
- [x] Exportação usa transação PostgreSQL `REPEATABLE READ, READ ONLY`.
- [x] Snapshot possui allowlists e escrita atômica.
- [x] Leitor falha fechado para arquivo ausente, inválido ou inseguro; stale é
  exposto nos GETs como `fresh=false` e recusado na geração opt-in.
- [x] Compose monta o diretório como `:ro` com grupo suplementar dedicado.
- [x] Testes cobrem leitura, freshness, symlink, tamanho, permissões e transporte.
- [ ] Túnel SSH/VPN provisionado e fingerprint verificado no host da RTX 5090.
- [ ] Serviço publicado e sete endpoints validados no ambiente remoto.

## 6. Rollback

1. definir `CANONICAL_CONTEXT_SOURCE=postgresql` somente se existir TLS e uma
   credencial read-only; caso contrário, manter os endpoints indisponíveis;
2. parar e desabilitar `procelbot-context-sync` e o túnel;
3. remover o bind mount após recriar o container;
4. remover a credencial isolada apenas depois de parar o sincronizador;
5. preservar o último snapshot até concluir a análise de rollback.
