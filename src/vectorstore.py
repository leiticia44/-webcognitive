"""Base de données vectorielle : stockage durable des segments et de leurs vecteurs.

Pour chaque segment, la base enregistre de manière liée :
- son identifiant unique (ex. doc_001_s0004) ;
- son vecteur (384 nombres) ;
- son texte original ;
- ses métadonnées : fichier source, page ou section, titre, auteur, date…

Deux implémentations ont la même interface :
- `BaseChroma` : ChromaDB, base vectorielle locale et persistante (utilisée par l'API) ;
- `BaseMemoire` : une base en mémoire en numpy, utile pour les tests.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np

NOM_COLLECTION = "webcognitive"
TAILLE_LOT = 500  # nombre de segments envoyés à la base en une fois

# Métadonnées de segment conservées dans la base (ChromaDB n'accepte que str, int, float, bool)
CHAMPS_SEGMENT = ["doc_id", "titre", "fichier", "format", "position", "page", "section",
                  "bloc", "rang_dans_bloc", "debut", "fin", "nombre_caracteres",
                  "auteur", "source", "date"]


def metadonnees_segment(segment: dict) -> dict:
    """Garde les champs utiles et retire les valeurs vides (refusées par ChromaDB)."""
    return {c: segment[c] for c in CHAMPS_SEGMENT
            if segment.get(c) is not None and segment.get(c) != ""}


def _par_lots(n: int, taille: int) -> Iterable[tuple[int, int]]:
    for debut in range(0, n, taille):
        yield debut, min(debut + taille, n)


def _resultat(identifiant: str, score: float, texte: str, meta: dict) -> dict:
    return {"id": identifiant, "score": round(float(score), 4), "texte": texte, "metadonnees": meta}


def resume_documents(metadonnees: list[dict]) -> list[dict]:
    """Regroupe les métadonnées des segments par document (pour /documents et /stats)."""
    documents: dict[str, dict] = {}
    for m in metadonnees:
        d = documents.setdefault(m["doc_id"], {
            "doc_id": m["doc_id"], "titre": m.get("titre"), "fichier": m.get("fichier"),
            "format": m.get("format"), "segments": 0})
        d["segments"] += 1
    return sorted(documents.values(), key=lambda d: d["doc_id"])


class BaseChroma:
    """Base vectorielle ChromaDB persistée dans un dossier local (par défaut data/chroma/)."""

    def __init__(self, dossier: Path, nom: str = NOM_COLLECTION):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as erreur:
            raise ImportError("chromadb n'est pas installé : pip install -r requirements.txt") from erreur
        self.dossier = Path(dossier)
        self.nom = nom
        self._client = chromadb.PersistentClient(
            path=str(self.dossier), settings=Settings(anonymized_telemetry=False))
        self._collection = self._client.get_or_create_collection(nom, metadata={"hnsw:space": "cosine"})

    # -- écriture -----------------------------------------------------------------

    def reinitialiser(self, reglages: dict) -> None:
        """Vide la base et enregistre les réglages (modèle, taille…) de la nouvelle indexation."""
        try:
            self._client.delete_collection(self.nom)
        except Exception:  # la collection n'existait pas encore
            pass
        metadata = {"hnsw:space": "cosine"}
        metadata.update({k: v for k, v in reglages.items() if isinstance(v, (str, int, float, bool))})
        self._collection = self._client.create_collection(self.nom, metadata=metadata)

    def ajouter(self, segments: list[dict], vecteurs: np.ndarray, taille_lot: int = TAILLE_LOT) -> None:
        """Enregistre les segments par lots : identifiant, vecteur, texte et métadonnées liés."""
        for debut, fin in _par_lots(len(segments), taille_lot):
            lot = segments[debut:fin]
            self._collection.upsert(
                ids=[s["id"] for s in lot],
                embeddings=vecteurs[debut:fin].tolist(),
                documents=[s["texte"] for s in lot],
                metadatas=[metadonnees_segment(s) for s in lot],
            )

    # -- lecture ------------------------------------------------------------------

    def reglages(self) -> dict:
        meta = dict(self._collection.metadata or {})
        meta.pop("hnsw:space", None)
        return meta

    def compter(self) -> int:
        return self._collection.count()

    def documents(self) -> list[dict]:
        if not self.compter():
            return []
        tout = self._collection.get(include=["metadatas"])
        return resume_documents(tout["metadatas"])

    def segment(self, identifiant: str) -> dict | None:
        r = self._collection.get(ids=[identifiant], include=["documents", "metadatas"])
        if not r["ids"]:
            return None
        return _resultat(r["ids"][0], 1.0, r["documents"][0], r["metadatas"][0])

    def rechercher(self, vecteur: np.ndarray, k: int = 5, filtre: dict | None = None) -> list[dict]:
        """Les k segments les plus proches. score = similarité cosinus (1 = sens identique)."""
        if not self.compter():
            return []
        where = None
        if filtre:  # ChromaDB veut {"$and": […]} dès qu'il y a plus d'une condition
            where = filtre if len(filtre) == 1 else {"$and": [{c: v} for c, v in filtre.items()]}
        r = self._collection.query(
            query_embeddings=[np.asarray(vecteur).tolist()],
            n_results=min(k, self.compter()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        # ChromaDB renvoie une distance cosinus : distance = 1 - similarité
        return [_resultat(i, 1 - d, t, m) for i, d, t, m in
                zip(r["ids"][0], r["distances"][0], r["documents"][0], r["metadatas"][0])]


class BaseMemoire:
    """Même interface que BaseChroma, en mémoire avec numpy (tests, démonstrations)."""

    def __init__(self):
        self._reglages: dict = {}
        self._ids: list[str] = []
        self._textes: list[str] = []
        self._metas: list[dict] = []
        self._vecteurs = np.zeros((0, 0), dtype=np.float32)

    def reinitialiser(self, reglages: dict) -> None:
        self.__init__()
        self._reglages = {k: v for k, v in reglages.items() if isinstance(v, (str, int, float, bool))}

    def ajouter(self, segments: list[dict], vecteurs: np.ndarray, taille_lot: int = TAILLE_LOT) -> None:
        for debut, fin in _par_lots(len(segments), taille_lot):
            for s, v in zip(segments[debut:fin], vecteurs[debut:fin]):
                if s["id"] in self._ids:  # même comportement que upsert : on remplace
                    i = self._ids.index(s["id"])
                    self._textes[i], self._metas[i] = s["texte"], metadonnees_segment(s)
                    self._vecteurs[i] = v
                    continue
                self._ids.append(s["id"])
                self._textes.append(s["texte"])
                self._metas.append(metadonnees_segment(s))
                self._vecteurs = v[None, :].astype(np.float32) if not len(self._vecteurs) \
                    else np.vstack([self._vecteurs, v[None, :]])

    def reglages(self) -> dict:
        return dict(self._reglages)

    def compter(self) -> int:
        return len(self._ids)

    def documents(self) -> list[dict]:
        return resume_documents(self._metas)

    def segment(self, identifiant: str) -> dict | None:
        if identifiant not in self._ids:
            return None
        i = self._ids.index(identifiant)
        return _resultat(self._ids[i], 1.0, self._textes[i], self._metas[i])

    def rechercher(self, vecteur: np.ndarray, k: int = 5, filtre: dict | None = None) -> list[dict]:
        if not self._ids:
            return []
        scores = self._vecteurs @ np.asarray(vecteur, dtype=np.float32)
        ordre = np.argsort(-scores)
        resultats = []
        for i in ordre:
            if filtre and any(self._metas[i].get(c) != v for c, v in filtre.items()):
                continue
            resultats.append(_resultat(self._ids[i], scores[i], self._textes[i], self._metas[i]))
            if len(resultats) == k:
                break
        return resultats


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")
