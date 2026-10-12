"""Test et optimisation de l'étape 3 avec les questions de validation.

Pour chaque combinaison (modèle × taille de segment), on découpe et on vectorise
le corpus, puis on pose chaque question de docs/questions_validation.md :
le bon document apparaît-il parmi les segments les plus proches ?

Usage :
    python -m src.evaluate                                  # tailles 250, 500, 800, 1200 ; modèle multilingue
    python -m src.evaluate --modeles multilingue,minilm     # compare aussi all-MiniLM-L6-v2
    python -m src.evaluate --tailles 400,600 --details      # détail question par question

Seules les questions dont la colonne « Fichier source » est remplie sont évaluées.
Les questions « pièges » (hors corpus) servent à mesurer le score obtenu quand
la réponse n'existe pas : il devra rester sous un seuil à l'étape 5.

Résultats : affichés et enregistrés dans data/vectors/evaluation.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .embeddings import Encodeur, plus_proches
from .vectorize import RACINE, charger_documents, construire_segments

K = 5  # nombre de segments regardés pour chaque question


@dataclass
class Question:
    numero: str
    texte: str
    fichier: str = ""
    position: str = ""


@dataclass
class Resultat:
    modele: str
    taille: int
    chevauchement: int
    nombre_segments: int
    top1: float = 0.0
    top3: float = 0.0
    top5: float = 0.0
    mrr: float = 0.0
    position_top5: float | None = None
    score_moyen_corpus: float = 0.0
    score_max_pieges: float | None = None
    details: list = field(default_factory=list)


# --------------------------------------------------------------- lecture des questions

def _lignes_tableau(texte: str, entete: str) -> list[list[str]]:
    """Lignes du premier tableau Markdown dont l'en-tête commence par `entete`."""
    lignes = texte.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith(entete):
            colonnes = [c.strip() for c in ligne.strip().strip("|").split("|")]
            rangees = []
            for l in lignes[i + 2:]:
                if not l.strip().startswith("|"):
                    break
                cellules = [c.strip() for c in l.strip().strip("|").split("|")]
                rangees.append(dict(zip(colonnes, cellules)))
            return rangees
    return []


def lire_questions(chemin: Path) -> tuple[list[Question], list[str]]:
    """Renvoie (questions avec source renseignée, questions pièges)."""
    texte = chemin.read_text(encoding="utf-8")
    questions = []
    for r in _lignes_tableau(texte, "| # |"):
        if r.get("Question") and r.get("Fichier source"):
            questions.append(Question(r["#"], r["Question"], r["Fichier source"], r.get("Page / section", "")))
    pieges = [r["Question"] for r in _lignes_tableau(texte, "| Question | Comportement") if r.get("Question")]
    return questions, pieges


# --------------------------------------------------------------- correspondances

def _nom(chemin: str | None) -> str:
    return Path((chemin or "").strip("` ")).name.lower()


def bon_document(segment: dict, question: Question) -> bool:
    return _nom(segment.get("fichier")) == _nom(question.fichier)


def bonne_position(segment: dict, question: Question) -> bool | None:
    """Compare la page ou la section attendue (None si non renseignée)."""
    attendu = question.position.strip().lower()
    if not attendu:
        return None
    nombres = re.findall(r"\d+", attendu)
    if segment.get("page") is not None and nombres and re.search(r"\bp(age|\.)?", attendu):
        return str(segment["page"]) in nombres
    section = (segment.get("section") or "").lower()
    attendu = re.sub(r"^section\s*:\s*", "", attendu)
    return bool(section) and (attendu in section or section in attendu)


# --------------------------------------------------------------- évaluation

def evaluer(documents: list[dict], questions: list[Question], pieges: list[str],
            encodeur: Encodeur, taille: int, chevauchement: int) -> Resultat:
    segments = construire_segments(documents, taille, chevauchement)
    resultat = Resultat(getattr(encodeur, "nom", "?"), taille, chevauchement, len(segments))
    if not segments or not questions:
        return resultat

    vecteurs = encodeur.encoder([s["texte_a_vectoriser"] for s in segments])
    vq = encodeur.encoder([q.texte for q in questions])

    rangs, positions, meilleurs_scores = [], [], []
    for q, v in zip(questions, vq):
        voisins = plus_proches(v, vecteurs, K)
        meilleurs_scores.append(voisins[0][1])
        rang = next((r for r, (i, _) in enumerate(voisins, start=1) if bon_document(segments[i], q)), None)
        rangs.append(rang)
        pos = [bonne_position(segments[i], q) for i, _ in voisins if bon_document(segments[i], q)]
        if q.position:
            positions.append(any(p for p in pos))
        premier = segments[voisins[0][0]]
        resultat.details.append({
            "question": q.numero, "texte": q.texte, "rang_bon_document": rang,
            "meilleur_segment": premier["id"], "meilleur_fichier": premier["fichier"],
            "meilleure_position": premier["position"], "score": round(voisins[0][1], 3),
        })

    n = len(questions)
    resultat.top1 = sum(r == 1 for r in rangs) / n
    resultat.top3 = sum(r is not None and r <= 3 for r in rangs) / n
    resultat.top5 = sum(r is not None for r in rangs) / n
    resultat.mrr = sum(1 / r for r in rangs if r) / n
    resultat.position_top5 = (sum(positions) / len(positions)) if positions else None
    resultat.score_moyen_corpus = float(np.mean(meilleurs_scores))

    if pieges:
        vp = encodeur.encoder(pieges)
        resultat.score_max_pieges = max(plus_proches(v, vecteurs, 1)[0][1] for v in vp)
    return resultat


def afficher(resultats: list[Resultat], nombre_questions: int, details: bool) -> None:
    print(f"\n{nombre_questions} questions évaluées — bon document parmi les {K} segments les plus proches\n")
    print(f"{'Modèle':<44}{'Taille':>7}{'Segm.':>7}{'Top-1':>7}{'Top-3':>7}{'Top-5':>7}"
          f"{'MRR':>7}{'Pos.':>7}{'Score':>7}{'Piège':>7}")
    meilleur = max(resultats, key=lambda r: (r.mrr, r.top1))
    for r in resultats:
        pos = f"{r.position_top5:.0%}" if r.position_top5 is not None else "—"
        piege = f"{r.score_max_pieges:.2f}" if r.score_max_pieges is not None else "—"
        marque = " ◀" if r is meilleur else ""
        print(f"{r.modele.split('/')[-1][:43]:<44}{r.taille:>7}{r.nombre_segments:>7}{r.top1:>7.0%}"
              f"{r.top3:>7.0%}{r.top5:>7.0%}{r.mrr:>7.2f}{pos:>7}{r.score_moyen_corpus:>7.2f}{piege:>7}{marque}")
    print("\nTop-k : part des questions dont le bon document est dans les k premiers segments.")
    print("MRR : moyenne de 1/rang du premier bon segment (1 = toujours premier).")
    print("Pos. : bonne page ou section dans le top-5 (si renseignée).")
    print("Score / Piège : similarité moyenne du meilleur segment pour les vraies questions,")
    print("                et la plus haute obtenue par une question piège (doit rester nettement plus basse).")
    if details:
        print(f"\nDétail — {meilleur.modele.split('/')[-1]}, taille {meilleur.taille} :")
        for d in meilleur.details:
            rang = d["rang_bon_document"] or "absent"
            print(f"  Q{d['question']:<3} rang {rang!s:<7} score {d['score']:.2f}  → "
                  f"{Path(d['meilleur_fichier']).name} ({d['meilleure_position']})")
    print()


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Évaluation du découpage et des embeddings")
    analyseur.add_argument("--processed", type=Path, default=RACINE / "data" / "processed")
    analyseur.add_argument("--questions", type=Path, default=RACINE / "docs" / "questions_validation.md")
    analyseur.add_argument("--tailles", default="250,500,800,1200")
    analyseur.add_argument("--ratio-chevauchement", type=float, default=0.2,
                           help="chevauchement = taille × ratio (0.2 par défaut)")
    analyseur.add_argument("--modeles", default="multilingue")
    analyseur.add_argument("--details", action="store_true")
    analyseur.add_argument("--sortie", type=Path, default=RACINE / "data" / "vectors" / "evaluation.json")
    args = analyseur.parse_args(argv)

    questions, pieges = lire_questions(args.questions)
    if not questions:
        print("\nAucune question évaluable : remplissez la colonne « Fichier source » de "
              "docs/questions_validation.md (et si possible « Page / section »).\n")
        return 1
    documents = charger_documents(args.processed)
    if not documents:
        print("\nAucun document dans data/processed/ : lancez d'abord python -m src.ingest\n")
        return 1

    from .embeddings import EncodeurLocal
    resultats = []
    for modele in args.modeles.split(","):
        print(f"Chargement du modèle {modele.strip()}…")
        try:
            encodeur = EncodeurLocal(modele.strip())
        except ImportError as erreur:
            print(f"\n✘ {erreur}\n")
            return 1
        for taille in (int(t) for t in args.tailles.split(",")):
            resultats.append(evaluer(documents, questions, pieges, encodeur, taille,
                                     int(taille * args.ratio_chevauchement)))

    afficher(resultats, len(questions), args.details)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps([r.__dict__ for r in resultats], ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
