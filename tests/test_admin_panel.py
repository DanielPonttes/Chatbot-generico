"""Garantias estáticas do painel: as chaves ficam fora dos assets do browser."""

from pathlib import Path


ADMIN_DIR = Path(__file__).parents[1] / "deploy/procelbot/admin"
CADDYFILE = Path(__file__).parents[1] / "deploy/procelbot/Caddyfile"


def test_admin_assets_have_no_infrastructure_credentials():
    assets = "\n".join(path.read_text(encoding="utf-8") for path in ADMIN_DIR.iterdir())

    assert "ADMIN_API_KEY" not in assets
    assert "PROCELBOT_ADMIN_API_KEY" not in assets
    assert "X-API-Key" not in assets


def test_admin_panel_uses_same_origin_server_side_routes():
    html = (ADMIN_DIR / "index.html").read_text(encoding="utf-8")
    javascript = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")

    assert 'fetch("/api/status"' in javascript
    assert 'href="/swagger"' in html
    assert 'href="/notifications"' in html
    assert 'href="/notifications/docs"' in html
    assert 'id="docs-launch-title"' in html


def test_admin_assets_remain_local_and_dom_safe():
    assets = "\n".join(path.read_text(encoding="utf-8") for path in ADMIN_DIR.iterdir())

    assert "https://" not in assets
    assert "innerHTML" not in assets
    javascript = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")
    assert "window.setInterval(refresh, REFRESH_MS)" in javascript
    assert "window.setInterval(updateCountdown, 1000)" in javascript


def test_admin_origin_requires_cloudflare_access_assertion():
    caddyfile = CADDYFILE.read_text(encoding="utf-8")

    assert "@admin_without_access not header Cf-Access-Jwt-Assertion *" in caddyfile
    assert "respond @admin_without_access 403" in caddyfile
    assert "@admin_swagger path /swagger /swagger/*" not in caddyfile


def test_notification_studio_is_local_dom_safe_and_manual_only():
    html = (ADMIN_DIR / "notifications.html").read_text(encoding="utf-8")
    javascript = (ADMIN_DIR / "notifications.js").read_text(encoding="utf-8")

    assert 'id="notification-form"' in html
    assert 'id="push-preview"' in html
    assert 'id="history-list"' in html
    assert 'src="/notifications.js"' in html
    assert 'href="/notifications.css"' in html
    assert "innerHTML" not in javascript
    assert "use_canonical_context: false" in javascript
    assert 'generate: "/v1/notifications/generate"' in javascript
    assert 'saved: "/v1/notifications/saved"' in javascript
    assert '"/v1/chat"' not in javascript


def test_notification_studio_proxy_has_method_and_path_allowlists():
    caddyfile = CADDYFILE.read_text(encoding="utf-8")

    assert "@notification_studio {\n            method GET HEAD\n            path /notifications" in caddyfile
    assert "rewrite * /notifications.html" in caddyfile
    assert "@notification_catalog {" in caddyfile
    assert "method GET" in caddyfile
    assert "@notification_generate {" in caddyfile
    assert "method POST" in caddyfile
    assert "@notification_review {" in caddyfile
    assert "method PATCH" in caddyfile
    assert "path /v1/notifications/saved/*" in caddyfile
    assert caddyfile.index("respond @admin_without_access 403") < caddyfile.index("@notification_catalog {")
    assert caddyfile.count("header_up X-API-Key {$PROCELBOT_ADMIN_API_KEY}") >= 4
    assert caddyfile.count("header_up -Cf-Access-Jwt-Assertion") >= 6
    assert "@admin_status {\n            method GET" in caddyfile
    assert "file_server\n        respond 404" in caddyfile
