"""Étape 8 — Recette : tests d'intégration de toute la chaîne.

Un mini-corpus dans les 4 formats (PDF, HTML, DOCX, TXT) traverse tout le pipeline,
comme le vrai corpus :

    fichiers bruts -> ingestion -> découpage -> vecteurs -> base -> recherche
    -> réponse avec sources (mode extractif, Ollama arrêté) -> validation -> tableau de bord

Le premier test appelle directement les modules Python ; le second passe par l'API REST
(POST /index, /recherche, /chat, /dataviz) et l'interface web, comme un utilisateur.
Aucun téléchargement : encodeur et LLM factices, base en mémoire.
"""

import json

import pytest

from src.dataviz import calculer
from src.indexation import indexer
from src.rag import rechercher, repondre
from src.validation import lire_jeu, rapport_markdown, valider
from src.vectorstore import BaseMemoire
from tests.test_ingestion import _creer_pdf
from tests.test_rag import LLMEnPanne
from tests.test_vectorisation import EncodeurFactice

QUESTIONS = """# Questions

| # | Question | Réponse attendue | Source de référence | Format visé | Fichier source | Page / section | Vérifiée |
|---|---|---|---|---|---|---|---|
| 1 | Combien de fois par semaine manger du poisson ? | 2 fois par semaine | Manger Bouger | HTML | poisson.html | section : Le poisson | ✅ |
| 2 | Combien de grammes de sel par jour au maximum ? | 5 g de sel | PNNS | PDF | reperes.pdf | page 2 | ✅ |

| Question | Comportement attendu |
|---|---|
| Qui a gagné la Coupe du monde de football ? | L'application indique que l'information n'est pas dans le corpus |
"""


def _corpus_brut(racine):
    """Un document par format, avec sa fiche dans corpus_metadata.json."""
    raw = racine / "data" / "raw"
    for dossier in ("pdf", "html", "docx", "txt"):
        (raw / dossier).mkdir(parents=True, exist_ok=True)

    _creer_pdf(raw / "pdf" / "reperes.pdf", [
        ["Reperes PNNS", "Les fruits et legumes : au moins 5 portions par jour."],
        ["Reperes PNNS", "Le sel : pas plus de 5 g de sel par jour pour un adulte."],
    ])
    (raw / "html" / "poisson.html").write_text(
        "<html><head><title>Le poisson</title></head><body><nav>Menu</nav><main>"
        "<h1>Le poisson</h1><p>Manger du poisson 2 fois par semaine, dont un poisson gras.</p>"
        "</main></body></html>", encoding="utf-8")
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Les groupes d'aliments", level=1)
    d.add_paragraph("Les féculents apportent de l'énergie. Les produits laitiers apportent du calcium.")
    d.save(raw / "docx" / "groupes.docx")
    (raw / "txt" / "eau.txt").write_bytes("L'eau\n\nL'eau est la seule boisson indispensable.".encode("cp1252"))

    fiches = [("doc_001", "pdf/reperes.pdf", "pdf", "Repères PNNS"),
              ("doc_002", "html/poisson.html", "html", "Le poisson"),
              ("doc_003", "docx/groupes.docx", "docx", "Les groupes d'aliments"),
              ("doc_004", "txt/eau.txt", "txt", "L'eau")]
    (racine / "corpus_metadata.json").write_text(json.dumps({
        "nombre_documents": 4,
        "documents": [{"id": i, "fichier": f"data/raw/{f}", "format": fmt, "titre": t} for i, f, fmt, t in fiches],
    }, ensure_ascii=False), encoding="utf-8")
    (racine / "questions.md").write_text(QUESTIONS, encoding="utf-8")


def test_chaine_complete_des_fichiers_au_rapport(tmp_path):
    _corpus_brut(tmp_path)
    base, encodeur = BaseMemoire(), EncodeurFactice()

    # 1-4. Ingestion des 4 formats, découpage, vecteurs et enregistrement dans la base
    rapport = indexer(base, encodeur, tmp_path / "data" / "processed", ingestion=True,
                      dossier_raw=tmp_path / "data" / "raw", fichier_metadonnees=tmp_path / "corpus_metadata.json",
                      racine=tmp_path)
    assert rapport["ingestion"]["documents_traites"] == 4 and rapport["ingestion"]["erreurs"] == []
    assert rapport["ingestion"]["par_format"] == {"docx": 1, "html": 1, "pdf": 1, "txt": 1}
    assert rapport["ingestion"]["controles_metadonnees"] == []
    assert base.compter() >= 4

    # 5. Recherche sémantique : la bonne source, avec sa page ou sa section
    [premier, *_] = rechercher("Combien de grammes de sel par jour ?", base, encodeur, k=3)
    assert premier["metadonnees"]["fichier"].endswith("reperes.pdf")
    assert premier["metadonnees"]["position"] == "page 2"

    # 5 bis. Réponse avec sources, Ollama arrêté : mode extractif
    r = repondre("Combien de fois par semaine manger du poisson ?", base, encodeur, LLMEnPanne(),
                 k=3, seuil=0.1, secours_extractif=True)
    assert r["mode"] == "extractif" and "2 fois par semaine" in r["reponse"]
    assert r["sources"][0]["citee"] and r["sources"][0]["fichier"].endswith("poisson.html")

    # 8. Validation : questions de l'étape 1 et rapport
    questions, pieges = lire_jeu(tmp_path / "questions.md")
    resultats = valider(questions, pieges, base, encodeur, LLMEnPanne(), k=3, seuil=0.1)
    assert resultats["resume"]["questions"] == 2 and resultats["resume"]["source_retrouvee"] == 2
    assert "# Rapport de validation" in rapport_markdown(resultats)

    # 7. Tableau de bord : les 4 formats et tous les segments
    donnees = calculer(base, tmp_path / "data" / "processed")
    assert donnees["totaux"]["documents"] == 4 and donnees["totaux"]["formats"] == 4
    assert len(donnees["carte"]["points"]) == base.compter()


def test_recette_par_l_api_et_l_interface(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from src.api import Moteur, app, obtenir_moteur

    class MoteurDeRecette(Moteur):
        def __init__(self):
            super().__init__(racine=tmp_path)
            self._base = BaseMemoire()

        def encodeur(self, modele):
            return EncodeurFactice()

        def llm(self, modele="mistral"):
            return LLMEnPanne()

    _corpus_brut(tmp_path)
    moteur = MoteurDeRecette()
    app.dependency_overrides[obtenir_moteur] = lambda: moteur
    try:
        client = TestClient(app)
        # Ingestion automatique des documents via l'API REST
        r = client.post("/index", json={"ingestion": True})
        assert r.status_code == 200 and r.json()["ingestion"]["documents_traites"] == 4

        assert client.get("/stats").json()["documents"] == 4
        trouves = client.get("/recherche", params={"q": "grammes de sel par jour", "k": 2}).json()["resultats"]
        assert trouves[0]["metadonnees"]["position"] == "page 2"

        chat = client.post("/chat", json={"question": "Combien de fois par semaine manger du poisson ?",
                                          "seuil": 0.1}).json()
        assert chat["mode"] == "extractif" and chat["sources"]

        assert client.get("/dataviz").json()["totaux"]["formats"] == 4

        # L'interface et le tableau de bord sont servis par FastAPI
        assert client.get("/app/").status_code == 200
        assert client.get("/app/dataviz.html").status_code == 200
    finally:
        app.dependency_overrides.clear()
