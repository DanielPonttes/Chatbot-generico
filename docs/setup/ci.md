# CI e Proteção de Branch

Este documento descreve o pipeline de qualidade do projeto e a política recomendada para a branch principal.

## Workflow Versionado

Arquivo: `.github/workflows/ci.yml`

O workflow roda em `push` e `pull_request` com duas jobs:

- `Pytest`
  - instala as dependências Python
  - executa `pytest tests/test_api.py tests/test_integrations_api.py tests/test_proactive_context.py -q`
- `Playwright E2E`
  - instala Python e Node
  - executa `npm ci`
  - instala o Chromium com `npx playwright install --with-deps chromium`
  - roda `npm run test:e2e`
  - publica `playwright-report` e `test-results` quando há falha

## Paridade Local

Os mesmos checks podem ser executados localmente com:

```bash
./venv/bin/pytest tests/test_api.py tests/test_integrations_api.py tests/test_proactive_context.py -q
npm ci
npx playwright install chromium
npm run test:e2e
```

Em Linux/WSL, se o Chromium reclamar de dependências do sistema:

```bash
sudo npx playwright install --with-deps chromium
```

## Política Recomendada para `main`

A branch `main` deve exigir:

- pull request antes de merge
- pelo menos 1 aprovação
- dismiss de reviews obsoletos após novo push
- conversation resolution obrigatória
- status checks obrigatórios:
  - `Pytest`
  - `Playwright E2E`
- force-push desabilitado
- deleção da branch desabilitada
- proteção aplicada também para administradores

## Aplicação Automatizada

Script versionado:

- `scripts/apply_branch_protection.sh`

Exemplo:

```bash
export GITHUB_TOKEN=seu_token_com_permissao_administrativa
./scripts/apply_branch_protection.sh DanielPonttes/Chatbot-generico main
```

Requisitos do token:

- acesso ao repositório
- permissão de administração da branch ou do repositório

## Limitação Atual

Nesta sessão, a proteção da branch não pôde ser aplicada diretamente pelo conector do GitHub porque a operação administrativa retornou `403 Resource not accessible by integration`, e não havia `GITHUB_TOKEN` nem `gh` configurados no ambiente.
