# CI e Protecao de Branch

O projeto possui workflow em `.github/workflows/ci.yml` para validar backend e frontend em `push` e `pull_request`.

## Jobs

### `Pytest`

Executa:

```bash
pytest tests/test_api.py tests/test_integrations_api.py tests/test_proactive_context.py -q
```

Cobertura:

- `/health`
- `/chat`
- contexto operacional proativo
- catalogo de integracoes
- endpoints auxiliares mockados

### `Playwright E2E`

Executa:

```bash
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
```

Cobertura:

- tela `/notifications`;
- bootstrap inicial;
- modal de configuracao;
- geracao mockada;
- feedback salvo;
- tratamento de erro.

Em falha, o workflow publica:

- `playwright-report`;
- `test-results`.

## Paridade Local

```bash
.\.venv\Scripts\python.exe -m pytest
npm run test:e2e
```

Linux/macOS:

```bash
.venv/bin/python -m pytest
npm run test:e2e
```

## Protecao Recomendada para `main`

Regras recomendadas:

- exigir pull request antes de merge;
- exigir pelo menos 1 aprovacao;
- descartar aprovacoes antigas apos novo push;
- exigir resolucao de conversas;
- exigir checks:
  - `Pytest`;
  - `Playwright E2E`;
- bloquear force-push;
- bloquear delete da branch;
- aplicar tambem para administradores quando o fluxo do time permitir.

## Script de Protecao

Arquivo:

```text
scripts/apply_branch_protection.sh
```

Uso:

```bash
export GITHUB_TOKEN=token_com_permissao_administrativa
./scripts/apply_branch_protection.sh DanielPonttes/Chatbot-generico main
```

Requisitos do token:

- acesso ao repositorio;
- permissao administrativa para alterar protecao da branch.

## Observacao

Se o GitHub retornar `403 Resource not accessible by integration`, use um token pessoal com permissao administrativa ou aplique a protecao pela interface do GitHub.
