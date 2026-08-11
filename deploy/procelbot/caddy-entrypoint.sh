#!/bin/sh

set -eu

if [ -z "${PROCELBOT_API_KEY:-}" ] || [ -z "${PROCELBOT_ADMIN_API_KEY:-}" ]; then
    echo "PROCELBOT_API_KEY e PROCELBOT_ADMIN_API_KEY precisam estar configuradas no proxy.env" >&2
    exit 1
fi

export PROCELBOT_BASIC_AUTH_HASH="$(tr -d '\r\n' < /run/secrets/procelbot_basic_auth_hash)"

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
