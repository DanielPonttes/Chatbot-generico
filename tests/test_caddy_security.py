"""Regressões estáticas do gateway Caddy atrás do Cloudflare Tunnel."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
CADDYFILE = ROOT / "deploy" / "procelbot" / "Caddyfile"
COMPOSE = ROOT / "deploy" / "procelbot" / "compose.yaml"


def _admin_site() -> str:
    content = CADDYFILE.read_text(encoding="utf-8")
    return content[content.index("http://admin.procel-chatbot.com") :]


def test_cloudflare_access_gate_precedes_admin_upstreams():
    admin_site = _admin_site()
    route_start = admin_site.index("route {")
    route = admin_site[route_start:]

    assert route.index("respond @admin_without_access 403") < route.index("handle @admin_status")
    assert route.index("respond @admin_without_access 403") < route.index("handle @admin_openapi")
    assert route.index("respond @admin_without_access 403") < route.index("handle @admin_swagger")


def test_proxy_origin_is_not_published_on_all_interfaces():
    compose = COMPOSE.read_text(encoding="utf-8")

    assert '"127.0.0.1:80:80"' in compose
