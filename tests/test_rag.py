"""Tests de l'étape 5 : recherche sémantique, pipeline RAG et client Ollama.

- Le LLM est remplacé par un « LLM factice » qui note ce qu'on lui envoie.
- Le client Ollama est testé contre un faux serveur HTTP local qui imite l'API d'Ollama
  (mêmes routes, même format JSON) : aucun modèle n'est téléchargé.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.indexation import indexer
from src.llm import ClientOllama, OllamaIndisponible
from src.rag import (REPONSE_INCONNUE, construire_messages, est_inconnue, fusionner_voisins,
                     numeros_cites, repondre)
from src.vectorstore import BaseMemoire
from tests.test_vectorisation import EncodeurFactice, _corpus


class LLMFactice:
    nom = "llm-factice"

    def __init__(self, reponse="Il faut manger du poisson deux fois par semaine, dont un poisson gras [1]."):
        self.reponse = reponse
        self.messages = None

    def generer(self, messages):
        self.messages = messages
        return self.reponse


@pytest.fixture
def base(tmp_path):
    _corpus(tmp_path / "processed")
    base = BaseMemoire()
    indexer(base, EncodeurFactice(), tmp_path / "processed")
    return base


# --------------------------------------------------------------------- pipeline RAG

def test_reponse_avec_sources(base):
    llm = LLMFactice()
    r = repondre("Combien de fois par semaine manger du poisson ?", base, EncodeurFactice(), llm, k=3, seuil=0.1)

    assert r["llm_appele"] and not r["hors_corpus"]
    assert r["reponse"].endswith("[1].")
    premiere = r["sources"][0]
    assert premiere["numero"] == 1 and premiere["citee"] is True
    assert premiere["fichier"] == "data/raw/pdf/reperes.pdf" and premiere["position"] == "page 1"
    assert "poisson" in premiere["extrait"]
    assert [s["citee"] for s in r["sources"][1:]] == [False] * (len(r["sources"]) - 1)


def test_prompt_strict_et_contexte_numerote(base):
    llm = LLMFactice()
    repondre("Combien de fois par semaine manger du poisson ?", base, EncodeurFactice(), llm, k=2, seuil=0.1)
    systeme, utilisateur = llm.messages
    assert systeme["role"] == "system" and "uniquement du contexte" in systeme["content"]
    assert REPONSE_INCONNUE in systeme["content"]
    assert utilisateur["content"].startswith("Contexte :\n\n[1] Repères adultes — page 1 (reperes.pdf)\n")
    assert "[2] " in utilisateur["content"]
    assert utilisateur["content"].endswith("Question : Combien de fois par semaine manger du poisson ?")


def test_question_hors_corpus_sans_appel_au_llm(base):
    llm = LLMFactice()
    r = repondre("Recette de la blanquette de veau", base, EncodeurFactice(), llm, seuil=0.3)
    assert r["reponse"] == REPONSE_INCONNUE and r["hors_corpus"] and not r["llm_appele"]
    assert r["sources"] == [] and llm.messages is None


def test_le_llm_dit_ne_pas_savoir(base):
    llm = LLMFactice(reponse=REPONSE_INCONNUE)
    r = repondre("Combien de fois manger du poisson ?", base, EncodeurFactice(), llm, seuil=0.1)
    assert r["llm_appele"] and r["hors_corpus"]


def test_filtre_par_format(base):
    r = repondre("sel par jour poisson", base, EncodeurFactice(), LLMFactice(), k=5, seuil=0.0,
                 filtre={"format": "html"})
    assert {s["fichier"] for s in r["sources"]} == {"data/raw/html/sel.html"}


# --------------------------------------------------------------------- briques

def test_numeros_cites():
    assert numeros_cites("A [1]. B [2][3]. C [1, 4]. D [9].", 4) == [1, 2, 3, 4]
    assert numeros_cites("Aucune citation.", 3) == []


def test_reponse_inconnue_detectee():
    assert est_inconnue(REPONSE_INCONNUE)
    assert est_inconnue("Cette information n'est pas dans le contexte fourni.")
    assert not est_inconnue("Il faut 5 portions par jour [1].")


def test_fusion_des_segments_qui_se_chevauchent():
    bloc = "Phrase un. Phrase deux. Phrase trois. Phrase quatre."

    def seg(i, d, f, score, bloc_no=1):
        return {"id": i, "score": score, "texte": bloc[d:f],
                "metadonnees": {"doc_id": "doc_001", "bloc": bloc_no, "debut": d, "fin": f}}

    [fusion] = fusionner_voisins([seg("b", 11, 37, 0.8), seg("a", 0, 23, 0.9)])
    assert fusion["texte"] == bloc[0:37] and fusion["ids"] == ["b", "a"] and fusion["score"] == 0.9
    [inclus] = fusionner_voisins([seg("a", 11, 23, 0.9), seg("b", 0, 37, 0.7)])
    assert inclus["texte"] == bloc[0:37]
    assert len(fusionner_voisins([seg("a", 0, 10, 0.9), seg("b", 11, 23, 0.8)])) == 2     # pas de chevauchement
    assert len(fusionner_voisins([seg("a", 0, 23, 0.9), seg("b", 11, 37, 0.8, 2)])) == 2  # autre bloc


def test_construire_messages_sans_fichier():
    messages = construire_messages("Q ?", [{"texte": "T", "metadonnees": {"doc_id": "doc_009"}}])
    assert "[1] doc_009\nT" in messages[1]["content"]


# --------------------------------------------------------------------- client Ollama

class FauxOllama(BaseHTTPRequestHandler):
    requetes = []

    def log_message(self, *args):
        pass

    def _envoyer(self, code, donnees):
        corps = json.dumps(donnees).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        if self.path == "/api/tags":
            self._envoyer(200, {"models": [{"name": "mistral:latest"}]})

    def do_POST(self):
        donnees = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FauxOllama.requetes.append(donnees)
        if donnees["model"] != "mistral":
            self._envoyer(404, {"error": f"model '{donnees['model']}' not found"})
        else:
            self._envoyer(200, {"model": "mistral", "message": {"role": "assistant", "content": " Réponse [1]. "},
                                "done": True})


@pytest.fixture
def ollama():
    serveur = HTTPServer(("127.0.0.1", 0), FauxOllama)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    FauxOllama.requetes = []
    yield f"http://127.0.0.1:{serveur.server_port}"
    serveur.shutdown()


def test_client_ollama(ollama):
    client = ClientOllama("mistral", url=ollama, temperature=0.1)
    assert client.disponible() and client.modeles_installes() == ["mistral:latest"]
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    assert client.generer(messages) == "Réponse [1]."
    [envoye] = FauxOllama.requetes
    assert envoye == {"model": "mistral", "messages": messages, "stream": False,
                      "options": {"temperature": 0.1, "num_ctx": 4096}}


def test_client_ollama_modele_absent(ollama):
    client = ClientOllama("llama3.1", url=ollama)
    assert not client.disponible()
    with pytest.raises(OllamaIndisponible, match="ollama pull llama3.1"):
        client.generer([{"role": "user", "content": "Bonjour"}])


def test_client_ollama_eteint():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # port libre : personne n'écoute
    client = ClientOllama(url=f"http://127.0.0.1:{port}", delai=2)
    assert not client.disponible()
    with pytest.raises(OllamaIndisponible, match="ollama serve"):
        client.generer([{"role": "user", "content": "Bonjour"}])


# --------------------------------------------------------------------- API /chat

@pytest.fixture
def client_api(tmp_path):
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

        def llm(self, modele="mistral"):
            return LLMFactice()

    _corpus(tmp_path / "data/processed")
    app.dependency_overrides[obtenir_moteur] = lambda: MoteurDeTest.instance
    MoteurDeTest.instance = MoteurDeTest()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_chat(client_api):
    assert client_api.post("/chat", json={"question": "poisson ?"}).status_code == 409   # base vide
    client_api.post("/index", json={"ingestion": False})
    r = client_api.post("/chat", json={"question": "Combien de fois manger du poisson par semaine ?", "seuil": 0.1})
    assert r.status_code == 200
    corps = r.json()
    assert corps["llm_appele"] and corps["sources"][0]["citee"] and corps["sources"][0]["position"] == "page 1"
    hors = client_api.post("/chat", json={"question": "Recette de la blanquette de veau"}).json()
    assert hors["hors_corpus"] and not hors["llm_appele"]
