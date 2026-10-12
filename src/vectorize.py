"""Étape 3 : data/processed/  ->  data/vectors/

Usage (depuis la racine du projet, venv activé) :

    python -m src.vectorize                         # 500 caractères, chevauchement 100
    python -m src.vectorize --taille 800 --chevauchement 150
    python -m src.vectorize --modele minilm         # all-MiniLM-L6-v2 (cité dans la fiche)
    python -m src.vectorize --sans-vecteurs         # découpage seul, sans charger de modèle

Produit dans data/vectors/ :
- segments.jsonl  : un segment par ligne (texte + document + page/section d'origine)
- embeddings.npy  : la matrice des vecteurs (une ligne par segment, dans le même ordre)
- index.json      : les réglages utilisés (modèle, taille, chevauchement) et des statistiques
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .chunking import CHEVAUCHEMENT_PAR_DEFAUT, TAILLE_PAR_DEFAUT, decouper_document
from .embeddings import MODELE_PAR_DEFAUT, Encodeur

RACINE = Path(__file__).resolve().parent.parent


def charger_documents(dossier: Path) -> list[dict]:
    """Charge les documents produits par l'étape 2 (le rapport d'ingestion est ignoré)."""
    documents = []
    for chemin in sorted(dossier.glob("*.json")):
        if chemin.name.startswith("rapport"):
            continue
        documents.append(json.loads(chemin.read_text(encoding="utf-8")))
    return documents


def construire_segments(documents: list[dict], taille: int = TAILLE_PAR_DEFAUT,
                        chevauchement: int = CHEVAUCHEMENT_PAR_DEFAUT,
                        avec_contexte: bool = True) -> list[dict]:
    segments = []
    for document in documents:
        segments.extend(decouper_document(document, taille, chevauchement, avec_contexte))
    return segments


def statistiques(segments: list[dict]) -> dict:
    if not segments:
        return {"nombre_segments": 0}
    tailles = np.array([s["nombre_caracteres"] for s in segments])
    par_document: dict[str, int] = {}
    for s in segments:
        par_document[s["doc_id"]] = par_document.get(s["doc_id"], 0) + 1
    return {
        "nombre_segments": len(segments),
        "nombre_documents": len(par_document),
        "taille_min": int(tailles.min()),
        "taille_moyenne": round(float(tailles.mean()), 1),
        "taille_mediane": int(np.median(tailles)),
        "taille_max": int(tailles.max()),
        "segments_courts": int((tailles < 100).sum()),  # moins de 100 caractères : peu de contexte
        "segments_par_document": par_document,
    }


def vectoriser(segments: list[dict], encodeur: Encodeur) -> np.ndarray:
    return encodeur.encoder([s["texte_a_vectoriser"] for s in segments])


def sauvegarder(dossier: Path, segments: list[dict], vecteurs: np.ndarray | None, reglages: dict) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    with (dossier / "segments.jsonl").open("w", encoding="utf-8") as f:
        for s in segments:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    if vecteurs is not None:
        np.save(dossier / "embeddings.npy", vecteurs)
    (dossier / "index.json").write_text(json.dumps(reglages, ensure_ascii=False, indent=2), encoding="utf-8")


def charger_index(dossier: Path) -> tuple[list[dict], np.ndarray, dict]:
    """Recharge ce qu'a produit `sauvegarder` (utile pour l'étape 4)."""
    segments = [json.loads(l) for l in (dossier / "segments.jsonl").read_text(encoding="utf-8").splitlines() if l]
    vecteurs = np.load(dossier / "embeddings.npy")
    reglages = json.loads((dossier / "index.json").read_text(encoding="utf-8"))
    return segments, vecteurs, reglages


def executer(dossier_processed: Path, dossier_sortie: Path, taille: int, chevauchement: int,
             encodeur: Encodeur | None, avec_contexte: bool = True) -> dict:
    documents = charger_documents(dossier_processed)
    segments = construire_segments(documents, taille, chevauchement, avec_contexte)

    vecteurs = None
    duree = None
    if encodeur is not None and segments:
        debut = time.perf_counter()
        vecteurs = vectoriser(segments, encodeur)
        duree = round(time.perf_counter() - debut, 2)

    reglages = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "modele": getattr(encodeur, "nom", None),
        "dimensions": int(vecteurs.shape[1]) if vecteurs is not None else None,
        "taille": taille,
        "chevauchement": chevauchement,
        "avec_contexte": avec_contexte,
        "duree_vectorisation_s": duree,
        "statistiques": statistiques(segments),
    }
    sauvegarder(dossier_sortie, segments, vecteurs, reglages)
    return reglages


def afficher(reglages: dict, dossier_sortie: Path) -> None:
    st = reglages["statistiques"]
    print()
    if not st["nombre_segments"]:
        print("Aucun segment : lancez d'abord l'étape 2 (python -m src.ingest).\n")
        return
    print(f"Découpage : taille {reglages['taille']} caractères, chevauchement {reglages['chevauchement']}")
    print(f"  {st['nombre_segments']} segments pour {st['nombre_documents']} documents")
    print(f"  taille min / moyenne / max : {st['taille_min']} / {st['taille_moyenne']} / {st['taille_max']} caractères")
    if st["segments_courts"]:
        print(f"  ⚠ {st['segments_courts']} segments de moins de 100 caractères (peu de contexte)")
    if reglages["modele"]:
        print(f"Vectorisation : {reglages['modele']}")
        print(f"  {st['nombre_segments']} vecteurs de {reglages['dimensions']} dimensions "
              f"en {reglages['duree_vectorisation_s']} s")
    else:
        print("Vectorisation : non faite (--sans-vecteurs)")
    print(f"Sortie : {dossier_sortie}\n")


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Découpage et vectorisation du corpus WebCognitive")
    analyseur.add_argument("--processed", type=Path, default=RACINE / "data" / "processed")
    analyseur.add_argument("--sortie", type=Path, default=RACINE / "data" / "vectors")
    analyseur.add_argument("--taille", type=int, default=TAILLE_PAR_DEFAUT)
    analyseur.add_argument("--chevauchement", type=int, default=CHEVAUCHEMENT_PAR_DEFAUT)
    analyseur.add_argument("--modele", default=MODELE_PAR_DEFAUT,
                           help="nom Hugging Face, ou 'multilingue' / 'minilm'")
    analyseur.add_argument("--sans-contexte", action="store_true",
                           help="ne pas ajouter le titre et la section devant chaque segment")
    analyseur.add_argument("--sans-vecteurs", action="store_true",
                           help="découper seulement, sans charger de modèle")
    args = analyseur.parse_args(argv)

    encodeur = None
    if not args.sans_vecteurs:
        from .embeddings import EncodeurLocal
        print(f"Chargement du modèle {args.modele}… (téléchargé une seule fois)")
        try:
            encodeur = EncodeurLocal(args.modele)
        except ImportError as erreur:
            print(f"\n✘ {erreur}\n  (ou relancez avec --sans-vecteurs pour tester le découpage seul)\n")
            return 1

    reglages = executer(args.processed.resolve(), args.sortie.resolve(), args.taille,
                        args.chevauchement, encodeur, not args.sans_contexte)
    afficher(reglages, args.sortie)
    return 0


if __name__ == "__main__":
    sys.exit(main())
