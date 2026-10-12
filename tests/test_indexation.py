"""Tests de l'étape 4 : base vectorielle, pipeline d'indexation et API.

La base ChromaDB et le vrai modèle sont remplacés par une base en mémoire
(même interface) et l'encodeur factice de l'étape 3 : les tests ne téléchargent rien.
Les tests de l'API sont ignorés si FastAPI n'est pas installé.
"""

import json

import numpy as np
import pytest

from src.indexation import indexer
from src.vectorstore import BaseMemoire, metadonnees_segment
from tests.test_vectorisation import EncodeurFactice, _corpus


def _segments():
    return [
        {"id": "doc_001_s0001", "doc_id": "doc_001", "titre": "Repères", "fichier": "data/raw/pdf/r.pdf",
         "format": "pdf", "position": "page 1", "page": 1, "section": None, "texte": "Poisson deux fois."},
        {"id": "doc_002_s0001", "doc_id": "doc_002", "titre": "Le sel", "fichier": "data/raw/html/s.html",
         "format": "html", "position": "section : Le sel", "page": None, "section": "Le sel", "texte": "Cinq grammes."},
    ]


# --------------------------------------------------------------------- base vectorielle

def test_metadonnees_sans_valeurs_vides():
    meta = metadonnees_segment(_segments()[1] | {"auteur": ""})
    assert "page" not in meta and "auteur" not in meta     # ChromaDB refuse None
    assert meta["section"] == "Le sel" and meta["fichier"] == "data/raw/html/s.html"


def test_base_memoire_stocke_vecteurs_textes_et_metadonnees_lies():
    base = BaseMemoire()
    base.reinitialiser({"modele": "factice", "taille": 500, "ignore": None})
    base.ajouter(_segments(), np.eye(2, 384, dtype=np.float32), taille_lot=1)
    assert base.compter() == 2 and base.reglages() == {"modele": "factice", "taille": 500}

    seg = base.segment("doc_001_s0001")
    assert seg["texte"] == "Poisson deux fois." and seg["metadonnees"]["page"] == 1
    assert base.segment("inconnu") is None

    [premier, second] = base.rechercher(np.eye(1, 384, 1, dtype=np.float32)[0], k=2)
    assert premier["id"] == "doc_002_s0001" and premier["score"] == 1.0
    assert second["score"] == 0.0
    assert [r["id"] for r in base.rechercher(np.ones(384), 5, {"format": "pdf"})] == ["doc_001_s0001"]
    assert base.documents() == [
        {"doc_id": "doc_001", "titre": "Repères", "fichier": "data/raw/pdf/r.pdf", "format": "pdf", "segments": 1},
        {"doc_id": "doc_002", "titre": "Le sel", "fichier": "data/raw/html/s.html", "format": "html", "segments": 1}]


def test_ajouter_deux_fois_remplace_sans_doublon():
    base = BaseMemoire()
    base.ajouter(_segments(), np.eye(2, 384, dtype=np.float32))
    modifie = [_segments()[0] | {"texte": "Nouveau texte."}]
    base.ajouter(modifie, np.eye(1, 384, dtype=np.float32))
    assert base.compter() == 2 and base.segment("doc_001_s0001")["texte"] == "Nouveau texte."


# --------------------------------------------------------------------- pipeline

def test_indexation_complete(tmp_path):
    _corpus(tmp_path / "processed")
    doc = json.loads((tmp_path / "processed/doc_002.json").read_text(encoding="utf-8"))
    doc["metadonnees"] = {"auteur": "Manger Bouger", "source": "https://www.mangerbouger.fr", "date": "2024"}
    (tmp_path / "processed/doc_002.json").write_text(json.dumps(doc), encoding="utf-8")

    base = BaseMemoire()
    rapport = indexer(base, EncodeurFactice(), tmp_path / "processed", taille=500, chevauchement=100)

    assert rapport["statut"] == "termine"
    assert rapport["documents"] == 2 and rapport["segments"] == 3 == rapport["segments_en_base"]
    assert set(rapport["durees_s"]) == {"lecture", "decoupage", "vectorisation", "enregistrement"}
    assert base.reglages()["modele"] == "factice" and base.reglages()["dimensions"] == 384

    # Traçabilité : fichier, position, identifiant et infos du corpus liés à chaque segment
    [meilleur] = base.rechercher(EncodeurFactice().encoder(["grammes de sel par jour"])[0], k=1)
    assert meilleur["id"] == "doc_002_s0001"
    assert meilleur["metadonnees"]["fichier"] == "data/raw/html/sel.html"
    assert meilleur["metadonnees"]["position"] == "section : Le sel"
    assert meilleur["metadonnees"]["auteur"] == "Manger Bouger"


def test_reindexer_vide_d_abord_la_base(tmp_path):
    _corpus(tmp_path / "processed")
    base = BaseMemoire()
    indexer(base, EncodeurFactice(), tmp_path / "processed")
    (tmp_path / "processed/doc_001.json").unlink()            # un document retiré du corpus
    rapport = indexer(base, EncodeurFactice(), tmp_path / "processed")
    assert rapport["segments_en_base"] == 1
    assert [d["doc_id"] for d in base.documents()] == ["doc_002"]


def test_indexation_corpus_vide(tmp_path):
    (tmp_path / "processed").mkdir()
    rapport = indexer(BaseMemoire(), EncodeurFactice(), tmp_path / "processed")
    assert rapport["statut"] == "vide"


def test_indexation_avec_ingestion(tmp_path):
    (tmp_path / "data/raw/txt").mkdir(parents=True)
    (tmp_path / "data/raw/txt/eau.txt").write_text("L'eau\n\nLa seule boisson indispensable.", encoding="utf-8")
    meta = tmp_path / "corpus_metadata.json"
    meta.write_text(json.dumps({"nombre_documents": 1, "documents": [
        {"id": "doc_001", "fichier": "data/raw/txt/eau.txt", "format": "txt", "titre": "Hydratation",
         "auteur": "Manger Bouger"}]}), encoding="utf-8")

    base = BaseMemoire()
    rapport = indexer(base, EncodeurFactice(), tmp_path / "data/processed", ingestion=True,
                      dossier_raw=tmp_path / "data/raw", fichier_metadonnees=meta, racine=tmp_path)
    assert rapport["ingestion"]["documents_traites"] == 1 and rapport["ingestion"]["erreurs"] == []
    assert "ingestion" in rapport["durees_s"]
    seg = base.segment("doc_001_s0001")
    assert seg["metadonnees"]["titre"] == "Hydratation" and seg["metadonnees"]["auteur"] == "Manger Bouger"


# --------------------------------------------------------------------- API

@pytest.fixture
def client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from src.api import Moteur, app, obtenir_moteur

    class MoteurDeTest(Moteur):
        def __init__(self):
            super().__init__(racine=tmp_path)
            self._base = BaseMemoire()

        def encodeur(self, modele):
            return EncodeurFactice()

    _corpus(tmp_path / "data/processed")
    moteur = MoteurDeTest()
    app.dependency_overrides[obtenir_moteur] = lambda: moteur
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_index_puis_recherche(client):
    assert client.get("/sante").json()["segments_en_base"] == 0
    assert client.get("/recherche", params={"q": "sel"}).status_code == 409   # base vide

    r = client.post("/index", json={"ingestion": False, "taille": 500, "chevauchement": 100})
    assert r.status_code == 200 and r.json()["segments_en_base"] == 3

    stats = client.get("/stats").json()
    assert stats["documents"] == 2 and stats["reglages"]["taille"] == 500
    assert [d["doc_id"] for d in client.get("/documents").json()] == ["doc_001", "doc_002"]
    assert client.get("/segments/doc_002_s0001").json()["metadonnees"]["position"] == "section : Le sel"
    assert client.get("/segments/inconnu").status_code == 404

    resultats = client.get("/recherche", params={"q": "grammes de sel par jour", "k": 2}).json()["resultats"]
    assert resultats[0]["id"] == "doc_002_s0001" and len(resultats) == 2
    pdf = client.get("/recherche", params={"q": "sel", "format": "pdf"}).json()["resultats"]
    assert {r["metadonnees"]["format"] for r in pdf} == {"pdf"}

    assert client.delete("/index").json()["segments_en_base"] == 0


def test_api_refuse_un_chevauchement_trop_grand(client):
    assert client.post("/index", json={"taille": 200, "chevauchement": 300}).status_code == 422
