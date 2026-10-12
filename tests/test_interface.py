"""Tests de l'étape 6 : l'API sert l'interface web (ignorés si FastAPI n'est pas installé)."""

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def test_fichiers_de_l_interface_presents():
    for nom in ("index.html", "style.css", "app.js"):
        assert (FRONTEND / nom).is_file()
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in html and 'href="style.css"' in html
    # L'interface fonctionne hors ligne : aucune ressource chargée depuis Internet
    assert "http://" not in html and "https://" not in html


def test_l_interface_appelle_les_routes_de_l_api():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    for route in ('"/sante"', '"/chat"', '"/index"'):
        assert route in js


def test_api_sert_l_interface():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from src.api import app

    client = TestClient(app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    page = client.get("/app/")
    assert page.status_code == 200 and "WebCognitive" in page.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/api").json()["interface"] == "/app/"
