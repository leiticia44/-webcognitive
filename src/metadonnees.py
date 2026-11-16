"""Compléter corpus_metadata.json pour les fichiers de data/raw/ qui n'ont pas encore de fiche.

Usage (depuis la racine du projet, après `python -m src.ingest`) :

    python -m src.metadonnees            # affiche les fiches proposées, sans rien écrire
    python -m src.metadonnees --ecrire   # les ajoute à corpus_metadata.json

Pour chaque fichier sans fiche, une entrée est créée avec :
- un identifiant à la suite des existants (doc_007, doc_008…) ;
- le titre détecté à l'ingestion (titre du PDF, balise <title> de la page web…) ou, à défaut, le nom du fichier ;
- l'auteur et la source quand le nom du fichier les indique (Santé publique France, Anses, Manger Bouger…) ;
- le nombre de pages et un champ « audit » qui reprend les avertissements de l'ingestion.

Les champs impossibles à deviner (date de publication, URL exacte) restent à compléter
à la main : ils sont marqués « à compléter ». Les fiches existantes ne sont jamais modifiées.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from .ingest import charger_metadonnees, lister_fichiers, normaliser_chemin
from .parsers import EXTENSIONS

RACINE = Path(__file__).resolve().parent.parent
A_COMPLETER = "à compléter"

# (motif dans le nom du fichier, auteur, source) — le premier qui correspond l'emporte
ORIGINES = [
    (r"manger bouger", "Santé publique France (Manger Bouger)", "https://www.mangerbouger.fr"),
    (r"^nut20\d\d", "Anses", "https://www.anses.fr"),
    (r"pnns", "Ministère des Solidarités et de la Santé", "https://sante.gouv.fr"),
    (r"faq-updatedalgo|nutri-?score", "Santé publique France", "https://www.santepubliquefrance.fr"),
    (r"spf\d+", "Santé publique France", "https://www.santepubliquefrance.fr"),
]

# (mots du titre ou du nom de fichier, sous-thème)
SOUS_THEMES = [
    (r"nutri-?score|algo", "Nutri-Score"),
    (r"activit[ée] physique|s[ée]dentarit", "activité physique"),
    (r"poisson|laitier|l[ée]gume|fruit|viande|f[ée]culent|sucre|sel\b|fibre", "repères de consommation"),
    (r"pnns|programme national", "politique de santé publique"),
    (r"rep[èe]res|recommandation", "recommandations"),
    (r"ob[ée]sit|surpoids|corpulence|esteban", "surpoids et obésité"),
    (r"ultra-?transform", "aliments ultra-transformés"),
    (r"[âa]g[ée]e?s|aidant|enfant|grossesse", "publics spécifiques"),
]


def _origine(nom: str) -> tuple[str, str]:
    nom = nom.lower()
    for motif, auteur, source in ORIGINES:
        if re.search(motif, nom):
            return auteur, source
    return A_COMPLETER, A_COMPLETER


def _sous_theme(*textes: str) -> str:
    texte = " ".join(t for t in textes if t).lower()
    for motif, theme in SOUS_THEMES:
        if re.search(motif, texte):
            return theme
    return A_COMPLETER


def _titre_depuis_nom(chemin: Path) -> str:
    """« Augmenter les légumes secs _ Manger Bouger » -> « Augmenter les légumes secs »."""
    titre = re.split(r"\s+_\s+", chemin.stem)[0]
    titre = re.sub(r"[_]+", " ", titre).strip()
    return titre[:1].upper() + titre[1:] if titre else chemin.name


def _ingestion_par_fichier(dossier_processed: Path) -> dict[str, dict]:
    """Les fichiers JSON produits par l'ingestion, indexés par chemin du document d'origine."""
    resultat = {}
    if not dossier_processed.is_dir():
        return resultat
    for f in dossier_processed.glob("*.json"):
        if f.name.startswith("rapport"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("fichier"):
            resultat[normaliser_chemin(d["fichier"])] = d
    return resultat


def _prochain_numero(documents: list[dict]) -> int:
    numeros = [int(m.group(1)) for d in documents if (m := re.fullmatch(r"doc_(\d+)", str(d.get("id", ""))))]
    return max(numeros, default=0) + 1


def proposer(racine: Path, fichier_meta: Path, dossier_raw: Path, dossier_processed: Path) -> list[dict]:
    """Fiches proposées pour les fichiers de data/raw/ qui n'en ont pas."""
    _, documents = charger_metadonnees(fichier_meta)
    declares = {normaliser_chemin(d.get("fichier", "")) for d in documents}
    ingestion = _ingestion_par_fichier(dossier_processed)
    numero = _prochain_numero(documents)

    fiches = []
    for chemin in lister_fichiers(dossier_raw):
        relatif = chemin.relative_to(racine).as_posix()
        if normaliser_chemin(relatif) in declares:
            continue
        info = ingestion.get(normaliser_chemin(relatif), {})
        stats = info.get("statistiques") or {}
        titre_detecte = (info.get("titre") or "").strip()
        # Un titre détecté identique au nom du fichier n'apporte rien : on reformule le nom
        if not titre_detecte or titre_detecte == chemin.stem:
            titre_detecte = _titre_depuis_nom(chemin)
        auteur, source = _origine(chemin.name)
        audit = [f"{stats['nombre_mots']} mots"] if stats.get("nombre_mots") else []
        audit += info.get("avertissements") or []
        audit.append("Fiche générée par src.metadonnees : vérifier le titre, compléter la date et l'URL exacte.")
        fiches.append({
            "id": f"doc_{numero:03d}",
            "fichier": relatif,
            "format": EXTENSIONS.get(chemin.suffix.lower(), chemin.suffix.lower().lstrip(".")),
            "titre": titre_detecte,
            "auteur": auteur,
            "source": source,
            "date": A_COMPLETER,
            "date_telechargement": date.today().isoformat(),
            "langue": "fr",
            "nombre_pages": stats.get("nombre_pages"),
            "sous_theme": _sous_theme(titre_detecte, chemin.name),
            "audit": " ; ".join(audit),
        })
        numero += 1
    return fiches


def ecrire(fichier_meta: Path, fiches: list[dict]) -> None:
    meta = json.loads(fichier_meta.read_text(encoding="utf-8"))
    meta.setdefault("documents", []).extend(fiches)
    meta["nombre_documents"] = len(meta["documents"])
    fichier_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Compléter corpus_metadata.json")
    analyseur.add_argument("--ecrire", action="store_true", help="ajouter les fiches au fichier (sinon : simple aperçu)")
    analyseur.add_argument("--metadonnees", type=Path, default=RACINE / "corpus_metadata.json")
    args = analyseur.parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    fiches = proposer(RACINE, args.metadonnees, RACINE / "data" / "raw", RACINE / "data" / "processed")
    if not fiches:
        print("Tous les fichiers de data/raw/ ont déjà une fiche dans corpus_metadata.json.")
        return 0
    for f in fiches:
        print(f"{f['id']}  {f['format']:<4}  {f['titre'][:70]}")
        print(f"        {f['auteur']} · {f['sous_theme']} · {f['nombre_pages'] or '-'} pages")
    if args.ecrire:
        ecrire(args.metadonnees, fiches)
        print(f"\n{len(fiches)} fiches ajoutées à {args.metadonnees.name}. "
              f"Relancez « python -m src.ingest » pour en tenir compte.")
    else:
        print(f"\n{len(fiches)} fiches proposées. Ajoutez --ecrire pour les enregistrer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
