#!/usr/bin/env bash
set -euo pipefail

REPO_FULL_NAME="${1:-DanielPonttes/Chatbot-generico}"
BRANCH_NAME="${2:-main}"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN nao definido."
  echo "Exemplo:"
  echo "  export GITHUB_TOKEN=seu_token_com_administration_write"
  echo "  ./scripts/apply_branch_protection.sh ${REPO_FULL_NAME} ${BRANCH_NAME}"
  exit 1
fi

read -r -d '' PAYLOAD <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {
        "context": "Pytest",
        "app_id": -1
      },
      {
        "context": "Playwright E2E",
        "app_id": -1
      }
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_linear_history": false,
  "lock_branch": false,
  "allow_fork_syncing": true
}
JSON

echo "Aplicando protecao na branch '${BRANCH_NAME}' do repositorio '${REPO_FULL_NAME}'..."

curl --fail-with-body --silent --show-error \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO_FULL_NAME}/branches/${BRANCH_NAME}/protection" \
  -d "${PAYLOAD}" >/dev/null

echo "Protecao aplicada com sucesso."
