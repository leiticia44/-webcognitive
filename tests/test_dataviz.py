"""Tests de l'étape 7 : données du tableau de bord et page de visualisation.

La base ChromaDB et le vrai modèle sont remplacés par la base en mémoire et
l'encodeur factice : rien n'est téléchargé. Le test de la route /dataviz est
ignoré si FastAPI n'est pas installé.
"""

from pathlib import Path

import numpy as np
import pytest

from src.dataviz import calculer, histogramme, mots, mots_cles, projection_acp
from src.indexation import indexer
from src.vectorstore import BaseMemoire
from tests.test_vectorisation import EncodeurFactice, _corpus

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _base_indexee(tmp_path):
    _corpus(tmp_path / "processed")
    base = BaseMemoire()
    indexer(base, EncodeurFactice(), tmp_path / "processed", taille=500, chevauchement=100)
    return base


# --------------------------------------------------------------------- outils de calcul

def test_mots_sans_mots_vides_ni_mots_courts():
    assert mots("Le sel : pas plus de 5 g par jour, l’eau à volonté !") == ["sel", "jour", "eau", "volonté"]
    assert mots("Les fruits et légumes, c'est au moins cinq portions") == ["fruits", "légumes", "cinq", "portions"]


def test_mots_cles_tf_idf():
    corpus, par_doc = mots_cles({
        "a": "poisson poisson gras poisson semaine",
        "b": "sel sel sel semaine",
    })
    assert corpus[0] == {"mot": "poisson", "occurrences": 3, "documents": 1}
    # « semaine » est dans les deux documents : il caractérise moins chacun d'eux
    assert par_doc["a"][0] == "poisson" and par_doc["b"][0] == "sel"
    assert par_doc["a"].index("semaine") > par_doc["a"].index("gras")


def test_projection_acp():
    rng = np.random.default_rng(0)
    # deux nuages bien séparés le long d'une direction : l'axe 1 doit les distinguer
    a = rng.normal(0, 0.05, (20, 10)) + np.eye(1, 10, 0)
    b = rng.normal(0, 0.05, (20, 10)) - np.eye(1, 10, 0)
    coords, variance = projection_acp(np.vstack([a, b]))
    assert coords.shape == (40, 2)
    assert (np.sign(coords[:20, 0]) == np.sign(coords[0, 0])).all()
    assert (np.sign(coords[20:, 0]) == -np.sign(coords[0, 0])).all()
    assert variance[0] > 0.8 and variance[0] + variance[1] <= 1.0001
    assert projection_acp(np.ones((1, 10)))[0].shape == (1, 2)


def test_histogramme():
    assert histogramme([10, 60, 70, 140]) == [
        {"debut": 0, "fin": 50, "segments": 1},
        {"debut": 50, "fin": 100, "segments": 2},
        {"debut": 100, "fin": 150, "segments": 1},
    ]
    assert histogramme([]) == []


# --------------------------------------------------------------------- calcul complet

def test_calculer_sur_une_base_indexee(tmp_path):
    donnees = calculer(_base_indexee(tmp_path), tmp_path / "processed")
    assert donnees["vide"] is False
    assert donnees["totaux"]["documents"] == 2 and donnees["totaux"]["segments"] == 3
    assert donnees["totaux"]["formats"] == 2

    assert [f["format"] for f in donnees["formats"]] == ["pdf", "html"]   # ordre fixe des formats
    pdf = donnees["formats"][0]
    assert pdf == {"format": "pdf", "documents": 1, "segments": 2, "mots": pdf["mots"]} and pdf["mots"] > 0

    doc = donnees["documents"][0]
    assert doc["doc_id"] == "doc_001" and doc["segments"] == 2 and doc["mots_cles"]
    assert sum(c["segments"] for c in donnees["longueurs"]) == 3

    points = donnees["carte"]["points"]
    assert len(points) == 3 and {"x", "y", "doc_id", "format", "extrait"} <= set(points[0])
    assert donnees["carte"]["echantillon"] is False

    sim = donnees["similarites"]
    assert sim["documents"] == ["doc_001", "doc_002"]
    m = np.array(sim["matrice"])
    assert m.shape == (2, 2) and np.allclose(np.diag(m), 1) and np.allclose(m, m.T)


def test_calculer_echantillonne_la_carte(tmp_path):
    donnees = calculer(_base_indexee(tmp_path), points_max=2)
    assert len(donnees["carte"]["points"]) == 2 and donnees["carte"]["echantillon"] is True
    assert donnees["carte"]["segments_total"] == 3


def test_calculer_base_vide():
    donnees = calculer(BaseMemoire())
    assert donnees["vide"] is True and donnees["totaux"]["segments"] == 0
    assert donnees["carte"]["points"] == [] and donnees["documents"] == []


def test_calculer_lit_l_evaluation(tmp_path):
    fichier = tmp_path / "evaluation.json"
    fichier.write_text('[{"modele": "m", "taille": 500, "top1": 0.6, "top5": 0.9, "details": [1, 2]}]',
                       encoding="utf-8")
    [ligne] = calculer(BaseMemoire(), fichier_evaluation=fichier)["evaluation"]
    assert ligne["taille"] == 500 and ligne["top5"] == 0.9 and "details" not in ligne


# --------------------------------------------------------------------- page et API

def test_page_du_tableau_de_bord():
    html = (FRONTEND / "dataviz.html").read_text(encoding="utf-8")
    assert 'src="dataviz.js"' in html and 'href="dataviz.css"' in html
    assert "http://" not in html and "https://" not in html      # fonctionne hors ligne
    assert '"/dataviz"' in (FRONTEND / "dataviz.js").read_text(encoding="utf-8")
    assert 'href="dataviz.html"' in (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_route_dataviz(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from src.api import Moteur, app, obtenir_moteur

    moteur = Moteur(racine=tmp_path)
    moteur._base = _base_indexee(tmp_path / "data")
    app.dependency_overrides[obtenir_moteur] = lambda: moteur
    try:
        r = TestClient(app).get("/dataviz")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["totaux"]["segments"] == 3
