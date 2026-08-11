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
