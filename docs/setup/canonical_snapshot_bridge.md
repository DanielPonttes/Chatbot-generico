# Ponte local de contexto canônico

Esta instalação não altera o PostgreSQL. Ela exige um túnel SSH ou VPN que
alcance a porta `187.77.58.122:4343`; sem transporte criptografado, não execute
o sincronizador.

## 1. Usuário, grupo e diretórios

Escolha um GID livre no host (o exemplo usa `1100`) e use o mesmo valor no
Compose:

```bash
sudo groupadd --system --gid 1100 procelbot-context
sudo useradd --system --gid procelbot-context --home-dir /nonexistent \
  --shell /usr/sbin/nologin procelbot-context
sudo install -d -o procelbot-context -g procelbot-context -m 0750 \
  /var/lib/procelbot/canonical-context
sudo install -d -o root -g procelbot-context -m 0750 \
  /etc/procelbot/context-sync
```

Em `deploy/backend/.env`, configure:

```dotenv
CANONICAL_SNAPSHOT_GID=1100
```

## 2. Transporte criptografado

Copie os exemplos sem preencher credenciais no repositório:

```bash
sudo install -o root -g procelbot-context -m 0640 \
  deploy/context_sync/context-tunnel.env.example \
  /etc/procelbot/context-tunnel.env
sudo install -o root -g root -m 0644 \
  deploy/context_sync/procelbot-context-tunnel.service.example \
  /etc/systemd/system/procelbot-context-tunnel.service
```

Instale uma chave dedicada sem senha, pertencente a
`procelbot-context:procelbot-context`, em
`/etc/procelbot/context-sync/id_ed25519`, modo `0600`, e um `known_hosts`
obtido após confirmar o fingerprint com o responsável pelo host SSH. A chave
deve permitir apenas port forwarding quando o servidor SSH suportar essa
restrição.

Preencha `/etc/procelbot/context-tunnel.env` e valide:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now procelbot-context-tunnel.service
sudo -u procelbot-context nc -vz 127.0.0.1 5433
```

Se uma VPN já fornecer transporte privado, não instale a unit SSH. Configure o
IP privado com `REMOTE_PG_SSLMODE=require` quando o PostgreSQL oferecer TLS; se
o endpoint privado continuar sem TLS, encaminhe-o para loopback com uma
ferramenta de túnel autenticada.

A unit do sincronizador usa `Requires`/`BindsTo` para parar junto com a unit SSH.
Em uma instalação baseada em VPN, crie um drop-in que limpe essas dependências
e adicione dependência equivalente à unit da VPN antes de habilitar o sync.

## 3. Sincronizador

Prepare o ambiente Python do host, separado do container:

```bash
cd /opt/procelbot-backend
python3 -m venv .venv
.venv/bin/pip install --requirement requirements.txt
```

```bash
sudo install -o root -g procelbot-context -m 0640 \
  deploy/context_sync/context-sync.env.example \
  /etc/procelbot/context-sync.env
sudo install -o root -g root -m 0644 \
  deploy/context_sync/procelbot-context-sync.service \
  /etc/systemd/system/procelbot-context-sync.service
```

Preencha a credencial somente em `/etc/procelbot/context-sync.env`. Execute o
primeiro ciclo manualmente e não imprima o conteúdo do snapshot:

```bash
sudo -u procelbot-context \
  /opt/procelbot-backend/.venv/bin/python \
  /opt/procelbot-backend/deploy/context_sync/procelbot_context_sync.py \
  --output /var/lib/procelbot/canonical-context/latest.json --once
sudo stat -c '%U %G %a %s %n' \
  /var/lib/procelbot/canonical-context/latest.json
```

O esperado é proprietário/grupo `procelbot-context`, modo `640` e tamanho
inferior a 4 MiB. Depois:

```bash
sudo systemctl enable --now procelbot-context-sync.service
```

## 4. Backend sem credencial remota

No `backend.env`, mantenha:

```dotenv
CANONICAL_CONTEXT_SOURCE=snapshot
CANONICAL_SNAPSHOT_PATH=/run/procelbot/canonical-context/latest.json
CANONICAL_SNAPSHOT_MAX_BYTES=4194304
CONTEXT_MAX_AGE_SECONDS=300
```

Remova `REMOTE_PG_PASSWORD`, `REMOTE_PG_USER` e qualquer segredo PostgreSQL do
arquivo do backend. Recrie apenas o container e valide com a chave
administrativa:

```bash
docker compose -f deploy/backend/compose.yaml up -d --build chatbot
curl -fsS -H 'X-API-Key: <ADMIN_API_KEY>' \
  http://127.0.0.1:8000/v1/context/missions >/dev/null
```

Não registre payloads de perfil, presença ou telemetria no terminal ou em logs
de implantação.
