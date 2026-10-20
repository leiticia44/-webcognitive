"""Étape 7 — Visualisation du corpus : les données du tableau de bord.

Toutes les statistiques sont calculées à partir de la base vectorielle (étape 4),
c'est-à-dire de ce que le moteur utilise réellement pour répondre :

- chiffres clés : documents, segments, mots, formats ;
- répartition par format et nombre de segments par document ;
- distribution de la longueur des segments (contrôle du chunking de l'étape 3) ;
- mots-clés du corpus et de chaque document (TF-IDF, sans bibliothèque externe) ;
- carte sémantique : les vecteurs à 384 dimensions projetés en 2D par ACP ;
- similarité entre documents (cosinus entre les vecteurs moyens).

Utilisé par la route GET /dataviz de l'API et par la page /app/dataviz.html.
En ligne de commande, `python -m src.dataviz` affiche un résumé et écrit
data/dataviz.json (utile pour vérifier les chiffres sans lancer l'API).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent

LARGEUR_CLASSE = 50       # largeur des barres de l'histogramme des longueurs, en caractères
POINTS_MAX_CARTE = 2000   # au-delà, la carte sémantique montre un échantillon régulier
MOTS_CLES_CORPUS = 25
MOTS_CLES_DOCUMENT = 6

# Mots vides du français (articles, pronoms, prépositions, auxiliaires…) et mots
# trop généraux dans ce corpus (dont « publique » et « france », venus de « Santé publique
# France », cité dans presque chaque document). Liste courte et lisible plutôt qu'exhaustive.
MOTS_VIDES = set("""
a à afin ai aie aient ainsi alors as au aucun aucune auquel aussi autre autres aux avec avez avoir avons
c ça car ce ceci cela celle celles celui cependant ces cet cette ceux chaque chez ci comme comment
d dans de des donc dont du elle elles en encore entre est et étaient était étant été être eu eux
fait faire fois font hors il ils j je jusqu l la laquelle le lequel les lesquels leur leurs lors lui
m ma mais me même mêmes mes moins mon n ne ni non nos notre nous on ont ou où par parce pas peu peut
peuvent plus plutôt pour pourquoi qu quand que quel quelle quelles quels qui quoi s sa sans se selon
ses si sinon soit son sont sous sur t ta te tel telle tels tes toi ton tous tout toute toutes très
tu un une unes uns v vers via voici voilà vos votre vous y
cas chez dont ici ainsi etc page section note document documents
publique france
""".split())

_MOT = re.compile(r"[a-zàâäçéèêëîïôöùûüÿœæ]+(?:-[a-zàâäçéèêëîïôöùûüÿœæ]+)*")


# --------------------------------------------------------------------- outils

def mots(texte: str) -> list[str]:
    """Mots significatifs d'un texte : minuscules, au moins 3 lettres, sans mots vides."""
    texte = texte.lower().replace("’", "'")
    return [m for m in _MOT.findall(texte) if len(m) >= 3 and m not in MOTS_VIDES]


def mots_cles(textes_par_doc: dict[str, str], n_corpus: int = MOTS_CLES_CORPUS,
              n_doc: int = MOTS_CLES_DOCUMENT) -> tuple[list[dict], dict[str, list[str]]]:
    """Mots-clés du corpus (fréquence totale) et de chaque document (TF-IDF).

    TF-IDF : un mot caractérise un document s'il y est fréquent (TF)
    et rare dans les autres documents (IDF = log(N / nombre de documents qui le contiennent)).
    """
    compteurs = {d: Counter(mots(t)) for d, t in textes_par_doc.items()}
    total: Counter = Counter()
    presence: Counter = Counter()
    for c in compteurs.values():
        total.update(c)
        presence.update(c.keys())

    corpus = [{"mot": m, "occurrences": n, "documents": presence[m]} for m, n in total.most_common(n_corpus)]

    n = len(compteurs)
    par_doc = {}
    for d, c in compteurs.items():
        nb = sum(c.values()) or 1
        poids = {m: (k / nb) * math.log((1 + n) / (1 + presence[m]) + 1) for m, k in c.items()}
        par_doc[d] = [m for m, _ in sorted(poids.items(), key=lambda x: (-x[1], x[0]))[:n_doc]]
    return corpus, par_doc


def projection_acp(vecteurs: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """Projette les vecteurs sur leurs 2 axes principaux (ACP par décomposition SVD).

    Renvoie les coordonnées (n × 2) et la part de variance expliquée par chaque axe.
    Deux segments proches sur la carte ont un sens proche.
    """
    if len(vecteurs) < 2:
        return np.zeros((len(vecteurs), 2)), [0.0, 0.0]
    centres = vecteurs - vecteurs.mean(axis=0)
    _, valeurs, axes = np.linalg.svd(centres, full_matrices=False)
    coords = centres @ axes[:2].T
    if coords.shape[1] < 2:  # un seul axe possible (ex. 2 points)
        coords = np.hstack([coords, np.zeros((len(coords), 1))])
    variance = valeurs ** 2
    part = (variance / variance.sum()).tolist() if variance.sum() else [0.0]
    part = (part + [0.0, 0.0])[:2]
    # Orientation stable d'une exécution à l'autre : le point le plus à droite est positif
    for j in range(2):
        if coords[np.argmax(np.abs(coords[:, j])), j] < 0:
            coords[:, j] *= -1
    return coords, [round(p, 4) for p in part]


def histogramme(longueurs: list[int], largeur: int = LARGEUR_CLASSE) -> list[dict]:
    if not longueurs:
        return []
    fin = (max(longueurs) // largeur + 1) * largeur
    comptes = Counter(l // largeur for l in longueurs)
    return [{"debut": i * largeur, "fin": (i + 1) * largeur, "segments": comptes.get(i, 0)}
            for i in range(fin // largeur)]


def _normaliser(v: np.ndarray) -> np.ndarray:
    normes = np.linalg.norm(v, axis=1, keepdims=True)
    normes[normes == 0] = 1
    return v / normes


def _infos_ingestion(dossier_processed: Path | None) -> dict[str, dict]:
    """Mots et pages de chaque document, lus dans data/processed/ (étape 2), si disponibles."""
    infos: dict[str, dict] = {}
    if not dossier_processed or not Path(dossier_processed).is_dir():
        return infos
    for f in Path(dossier_processed).glob("*.json"):
        if f.name.startswith("rapport"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("id"):
            stats = d.get("statistiques") or {}
            meta = d.get("metadonnees") or {}
            infos[d["id"]] = {"mots": stats.get("nombre_mots"), "pages": stats.get("nombre_pages"),
                              "sous_theme": meta.get("sous_theme"), "source": meta.get("source")}
    return infos


def _evaluation(fichier: Path | None) -> list[dict]:
    """Résultats de python -m src.evaluate (étape 3), s'ils existent."""
    if not fichier or not Path(fichier).is_file():
        return []
    try:
        lignes = json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    champs = ("modele", "taille", "chevauchement", "nombre_segments", "top1", "top3", "top5", "mrr",
              "score_moyen_corpus", "score_max_pieges")
    return [{c: l.get(c) for c in champs} for l in lignes if isinstance(l, dict)]


# --------------------------------------------------------------------- calcul principal

def calculer(base, dossier_processed: Path | None = None, fichier_evaluation: Path | None = None,
             points_max: int = POINTS_MAX_CARTE) -> dict:
    """Toutes les données du tableau de bord, à partir du contenu de la base vectorielle."""
    ids, textes, metas, vecteurs = base.exporter()
    reglages = base.reglages()
    resultat: dict = {"reglages": reglages, "evaluation": _evaluation(fichier_evaluation)}
    if not ids:
        resultat.update(vide=True, totaux={"documents": 0, "segments": 0, "mots": 0, "formats": 0},
                        formats=[], documents=[], longueurs=[], mots_cles=[], carte={"points": []},
                        similarites={"documents": [], "matrice": []})
        return resultat

    vecteurs = _normaliser(np.asarray(vecteurs, dtype=np.float64))
    infos = _infos_ingestion(dossier_processed)

    # -- documents (dans l'ordre des identifiants) ---------------------------
    docs: dict[str, dict] = {}
    lignes_par_doc: dict[str, list[int]] = {}
    textes_par_doc: dict[str, list[str]] = {}
    for i, (t, m) in enumerate(zip(textes, metas)):
        d = m.get("doc_id") or "?"
        if d not in docs:
            info = infos.get(d, {})
            docs[d] = {"doc_id": d, "titre": m.get("titre") or d, "fichier": m.get("fichier"),
                       "format": m.get("format") or "?", "segments": 0, "caracteres": 0,
                       "mots": info.get("mots"), "pages": info.get("pages"),
                       "sous_theme": info.get("sous_theme"), "source": info.get("source") or m.get("source")}
        docs[d]["segments"] += 1
        docs[d]["caracteres"] += int(m.get("nombre_caracteres") or len(t))
        lignes_par_doc.setdefault(d, []).append(i)
        # le texte du segment, sans le titre ajouté en contexte pour la vectorisation
        textes_par_doc.setdefault(d, []).append(t)
    ordre = sorted(docs)

    corpus_mots, mots_doc = mots_cles({d: " ".join(textes_par_doc[d]) for d in ordre})
    for d in ordre:
        docs[d]["mots_cles"] = mots_doc.get(d, [])
        if docs[d]["mots"] is None:  # pas de fichier d'ingestion : estimation depuis les segments
            docs[d]["mots"] = sum(len(t.split()) for t in textes_par_doc[d])
        docs[d]["longueur_moyenne"] = round(docs[d]["caracteres"] / docs[d]["segments"])

    # -- formats -------------------------------------------------------------
    formats: dict[str, dict] = {}
    for d in ordre:
        f = formats.setdefault(docs[d]["format"], {"format": docs[d]["format"], "documents": 0, "segments": 0, "mots": 0})
        f["documents"] += 1
        f["segments"] += docs[d]["segments"]
        f["mots"] += docs[d]["mots"] or 0
    ordre_formats = ["pdf", "html", "docx", "txt"]
    liste_formats = sorted(formats.values(),
                           key=lambda f: (ordre_formats.index(f["format"]) if f["format"] in ordre_formats else 99, f["format"]))

    # -- longueur des segments -----------------------------------------------
    longueurs = [int(m.get("nombre_caracteres") or len(t)) for t, m in zip(textes, metas)]

    # -- carte sémantique (ACP) ----------------------------------------------
    coords, variance = projection_acp(vecteurs)
    pas = max(1, math.ceil(len(ids) / points_max))
    points = [{"id": ids[i], "doc_id": metas[i].get("doc_id"), "format": metas[i].get("format") or "?",
               "titre": metas[i].get("titre"), "position": metas[i].get("position"),
               "x": round(float(coords[i, 0]), 4), "y": round(float(coords[i, 1]), 4),
               "extrait": re.sub(r"\s+", " ", textes[i])[:160]}
              for i in range(0, len(ids), pas)]

    # -- similarité entre documents ------------------------------------------
    centres = _normaliser(np.vstack([vecteurs[lignes_par_doc[d]].mean(axis=0) for d in ordre]))
    matrice = np.clip(centres @ centres.T, -1, 1)

    resultat.update(
        vide=False,
        totaux={"documents": len(ordre), "segments": len(ids),
                "mots": sum(docs[d]["mots"] or 0 for d in ordre), "formats": len(formats),
                "longueur_moyenne": round(sum(longueurs) / len(longueurs)),
                "longueur_mediane": int(np.median(longueurs))},
        formats=liste_formats,
        documents=[docs[d] for d in ordre],
        longueurs=histogramme(longueurs),
        mots_cles=corpus_mots,
        carte={"points": points, "variance_expliquee": variance, "echantillon": pas > 1,
               "segments_total": len(ids)},
        similarites={"documents": ordre, "matrice": [[round(float(v), 3) for v in ligne] for ligne in matrice]},
    )
    return resultat


# --------------------------------------------------------------------- ligne de commande

def afficher(donnees: dict) -> None:
    if donnees.get("vide"):
        print("La base est vide : lancez d'abord l'indexation (POST /index).")
        return
    t = donnees["totaux"]
    print(f"\n{t['documents']} documents · {t['segments']} segments · {t['mots']} mots · {t['formats']} formats")
    print(f"Longueur des segments : moyenne {t['longueur_moyenne']} caractères, médiane {t['longueur_mediane']}\n")
    for f in donnees["formats"]:
        print(f"  {f['format']:<5} {f['documents']:>3} documents {f['segments']:>6} segments")
    print("\nMots les plus fréquents : " + ", ".join(m["mot"] for m in donnees["mots_cles"][:12]))
    v = donnees["carte"]["variance_expliquee"]
    print(f"Carte sémantique : les 2 axes résument {100 * (v[0] + v[1]):.0f} % de la variance des vecteurs\n")


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Données du tableau de bord (étape 7)")
    analyseur.add_argument("--base", type=Path, default=RACINE / "data" / "chroma")
    analyseur.add_argument("--sortie", type=Path, default=RACINE / "data" / "dataviz.json")
    args = analyseur.parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    from .vectorstore import BaseChroma
    donnees = calculer(BaseChroma(args.base), RACINE / "data" / "processed",
                       RACINE / "data" / "vectors" / "evaluation.json")
    afficher(donnees)
    args.sortie.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Données écrites dans {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
