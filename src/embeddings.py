"""Vectorisation locale des segments avec sentence-transformers.

Un modèle d'embedding transforme un texte en une liste de nombres (un vecteur).
Deux textes de sens proche donnent des vecteurs proches : c'est ce qui permet
la recherche sémantique, même quand la question n'emploie pas les mêmes mots
que le document.

Le modèle est téléchargé une seule fois depuis Hugging Face, puis exécuté
entièrement en local (CPU suffisant) : aucune donnée ne quitte l'ordinateur.
"""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

# Modèle par défaut : multilingue, entraîné notamment sur du français.
# Il produit, comme all-MiniLM-L6-v2, des vecteurs de 384 dimensions.
MODELE_PAR_DEFAUT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Modèle cité dans la fiche pédagogique : rapide, mais entraîné surtout sur de l'anglais.
MODELE_ANGLAIS = "sentence-transformers/all-MiniLM-L6-v2"

MODELES_CONNUS = {
    "multilingue": MODELE_PAR_DEFAUT,
    "minilm": MODELE_ANGLAIS,
}


class Encodeur(Protocol):
    """Tout objet qui sait transformer une liste de textes en matrice de vecteurs."""

    nom: str

    def encoder(self, textes: Sequence[str]) -> np.ndarray: ...


class EncodeurLocal:
    """Encodeur basé sur sentence-transformers, exécuté en local."""

    def __init__(self, modele: str = MODELE_PAR_DEFAUT, taille_lot: int = 32):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as erreur:
            raise ImportError(
                "sentence-transformers n'est pas installé : pip install -r requirements.txt"
            ) from erreur
        self.nom = MODELES_CONNUS.get(modele, modele)
        self.taille_lot = taille_lot
        self._modele = SentenceTransformer(self.nom, device="cpu")

    @property
    def dimensions(self) -> int:
        return self._modele.get_sentence_embedding_dimension()

    def encoder(self, textes: Sequence[str]) -> np.ndarray:
        vecteurs = self._modele.encode(
            list(textes),
            batch_size=self.taille_lot,
            normalize_embeddings=True,  # norme 1 : la similarité cosinus devient un simple produit scalaire
            show_progress_bar=len(textes) > 200,
            convert_to_numpy=True,
        )
        return vecteurs.astype(np.float32)


def similarites(vecteur_question: np.ndarray, vecteurs: np.ndarray) -> np.ndarray:
    """Similarité cosinus entre une question et tous les segments.

    Les vecteurs sont normalisés (norme 1) : le cosinus est donc le produit scalaire.
    Résultat entre -1 et 1 ; plus c'est proche de 1, plus le sens est proche.
    """
    return vecteurs @ vecteur_question


def plus_proches(vecteur_question: np.ndarray, vecteurs: np.ndarray, k: int = 5) -> list[tuple[int, float]]:
    """Les k segments les plus proches : liste de (indice, score), du meilleur au moins bon."""
    scores = similarites(vecteur_question, vecteurs)
    k = min(k, len(scores))
    meilleurs = np.argpartition(-scores, k - 1)[:k]
    meilleurs = meilleurs[np.argsort(-scores[meilleurs])]
    return [(int(i), float(scores[i])) for i in meilleurs]
