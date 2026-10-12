"""Pipeline d'indexation complet, appelé par la route POST /index de l'API.

    (data/raw/ → ingestion →) data/processed/ → découpage → vectorisation → base vectorielle

Chaque phase est chronométrée et le résultat est un rapport JSON.
La logique ne dépend ni de FastAPI ni de ChromaDB : la base et l'encodeur sont
passés en paramètres, ce qui permet de la tester avec des versions légères.
"""

from __future__ import annotations

import time
from pathlib import Path

from .chunking import CHEVAUCHEMENT_PAR_DEFAUT, TAILLE_PAR_DEFAUT
from .embeddings import Encodeur
from .vectorize import charger_documents, construire_segments, statistiques
from .vectorstore import maintenant


class Chrono:
    """Mesure la durée de chaque phase."""

    def __init__(self):
        self.durees: dict[str, float] = {}
        self._debut = time.perf_counter()

    def etape(self, nom: str) -> None:
        maintenant_ = time.perf_counter()
        self.durees[nom] = round(maintenant_ - self._debut, 2)
        self._debut = maintenant_


def enrichir(segments: list[dict], documents: list[dict]) -> None:
    """Ajoute à chaque segment l'auteur, l'URL source et la date du document (corpus_metadata.json)."""
    infos = {d["id"]: d.get("metadonnees") or {} for d in documents}
    for s in segments:
        meta = infos.get(s["doc_id"], {})
        for champ in ("auteur", "source", "date"):
            if meta.get(champ):
                s[champ] = str(meta[champ])


def indexer(base, encodeur: Encodeur, dossier_processed: Path,
            taille: int = TAILLE_PAR_DEFAUT, chevauchement: int = CHEVAUCHEMENT_PAR_DEFAUT,
            avec_contexte: bool = True, ingestion: bool = False,
            dossier_raw: Path | None = None, fichier_metadonnees: Path | None = None,
            racine: Path | None = None) -> dict:
    """Indexe tout le corpus et renvoie un rapport.

    - `ingestion=True` relance d'abord l'étape 2 (data/raw → data/processed).
    - La base est vidée puis reconstruite : pas de segment périmé si un document
      a été modifié ou supprimé.
    """
    chrono = Chrono()
    rapport: dict = {"statut": "termine", "debut": maintenant()}

    if ingestion:
        from .ingest import executer as executer_ingestion
        r = executer_ingestion(dossier_raw, dossier_processed, fichier_metadonnees, racine)
        rapport["ingestion"] = {
            "documents_traites": r["documents_traites"],
            "par_format": r["par_format"],
            "erreurs": r["erreurs"],
            "avertissements": r["avertissements"],
            "controles_metadonnees": r["controles_metadonnees"],
        }
        chrono.etape("ingestion")

    documents = charger_documents(dossier_processed)
    if not documents:
        rapport.update(statut="vide", message="Aucun document dans data/processed/ : "
                       "ajoutez des fichiers dans data/raw/ et relancez avec ingestion=true.")
        return rapport
    chrono.etape("lecture")

    segments = construire_segments(documents, taille, chevauchement, avec_contexte)
    enrichir(segments, documents)
    chrono.etape("decoupage")

    vecteurs = encodeur.encoder([s["texte_a_vectoriser"] for s in segments])
    chrono.etape("vectorisation")

    reglages = {
        "modele": getattr(encodeur, "nom", "?"),
        "dimensions": int(vecteurs.shape[1]),
        "taille": taille,
        "chevauchement": chevauchement,
        "avec_contexte": avec_contexte,
        "date_indexation": maintenant(),
        "nombre_documents": len(documents),
        "nombre_segments": len(segments),
    }
    base.reinitialiser(reglages)
    base.ajouter(segments, vecteurs)
    chrono.etape("enregistrement")

    stats = statistiques(segments)
    rapport.update({
        "fin": maintenant(),
        "reglages": reglages,
        "documents": len(documents),
        "segments": len(segments),
        "segments_en_base": base.compter(),
        "taille_segments": {k: stats[k] for k in ("taille_min", "taille_moyenne", "taille_max", "segments_courts")},
        "durees_s": chrono.durees,
        "duree_totale_s": round(sum(chrono.durees.values()), 2),
    })
    return rapport
