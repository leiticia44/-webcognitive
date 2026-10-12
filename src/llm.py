"""Client pour le modèle de langage (LLM) local, exécuté par Ollama.

Ollama fait tourner des LLM open-source (Mistral, Llama…) sur l'ordinateur et
les expose sur http://localhost:11434. Aucune donnée ne part sur Internet.

Installation (une seule fois) :
    1. installer Ollama : https://ollama.com
    2. ollama pull mistral        # télécharge le modèle (environ 4 Go)
Ollama démarre ensuite en arrière-plan (sinon : ollama serve).

Réglages possibles par variables d'environnement :
    OLLAMA_URL     (par défaut http://localhost:11434)
    OLLAMA_MODELE  (par défaut mistral)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL_PAR_DEFAUT = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODELE_LLM_PAR_DEFAUT = os.environ.get("OLLAMA_MODELE", "mistral")


class OllamaIndisponible(RuntimeError):
    """Ollama ne répond pas, ou le modèle demandé n'est pas installé."""


class ClientOllama:
    def __init__(self, modele: str = MODELE_LLM_PAR_DEFAUT, url: str = URL_PAR_DEFAUT,
                 temperature: float = 0.1, contexte_max: int = 4096, delai: float = 300):
        self.modele = modele
        self.url = url.rstrip("/")
        self.temperature = temperature    # basse : réponses factuelles et stables
        self.contexte_max = contexte_max  # nombre de tokens que le modèle peut lire
        self.delai = delai                # secondes ; un LLM sur CPU peut être lent

    @property
    def nom(self) -> str:
        return self.modele

    def _appeler(self, chemin: str, donnees: dict | None = None, delai: float | None = None) -> dict:
        requete = urllib.request.Request(
            self.url + chemin,
            data=json.dumps(donnees).encode("utf-8") if donnees is not None else None,
            headers={"Content-Type": "application/json"},
            method="POST" if donnees is not None else "GET",
        )
        try:
            with urllib.request.urlopen(requete, timeout=delai or self.delai) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except urllib.error.HTTPError as erreur:
            detail = erreur.read().decode("utf-8", errors="replace")
            if erreur.code == 404:
                raise OllamaIndisponible(
                    f"Le modèle « {self.modele} » n'est pas installé dans Ollama : "
                    f"lancez « ollama pull {self.modele} ».") from erreur
            raise OllamaIndisponible(f"Erreur Ollama {erreur.code} : {detail}") from erreur
        except (urllib.error.URLError, ConnectionError, TimeoutError) as erreur:
            raise OllamaIndisponible(
                f"Ollama ne répond pas sur {self.url} : vérifiez qu'il est lancé (ollama serve).") from erreur

    def modeles_installes(self) -> list[str]:
        return [m["name"] for m in self._appeler("/api/tags", delai=5).get("models", [])]

    def disponible(self) -> bool:
        """Ollama répond-il, et le modèle est-il installé ?"""
        try:
            installes = self.modeles_installes()
        except OllamaIndisponible:
            return False
        return any(nom == self.modele or nom.split(":")[0] == self.modele for nom in installes)

    def generer(self, messages: list[dict]) -> str:
        """Envoie une conversation (rôles system / user / assistant) et renvoie la réponse du modèle."""
        reponse = self._appeler("/api/chat", {
            "model": self.modele,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.contexte_max},
        })
        return reponse.get("message", {}).get("content", "").strip()
