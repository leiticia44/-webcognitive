"""Découpage du texte en segments (chunking) avec chevauchement.

Principe :
- on découpe d'abord chaque bloc (page d'un PDF, section d'une page web…) en phrases ;
- on regroupe les phrases jusqu'à atteindre la taille visée (par défaut 500 caractères) ;
- le segment suivant reprend les dernières phrases du précédent (chevauchement),
  pour ne jamais couper une idée en deux entre deux segments.

On ne coupe jamais au milieu d'une phrase, sauf si une phrase seule dépasse la taille
maximale : elle est alors découpée sur les espaces, avec chevauchement.

Un segment ne dépasse jamais les limites de son bloc : il hérite ainsi de la position
d'origine (« page 3 », « section : Le sel ») pour pouvoir citer la source plus tard.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

TAILLE_PAR_DEFAUT = 500        # caractères visés par segment
CHEVAUCHEMENT_PAR_DEFAUT = 100  # caractères repris du segment précédent

# Fin de phrase : . ! ? … suivi d'un espace puis d'une majuscule, d'un chiffre,
# d'un guillemet, d'une parenthèse ou d'un tiret de liste.
# Les abréviations courtes (« p. 12 », « env. 5 », « M. Dupont ») ne coupent pas.
_FIN_PHRASE = re.compile(
    r"(?<!\bM)(?<!\bp)(?<!\benv)(?<!\bex)(?<!\bcf)(?<!\bvol)(?<!\bfig)"
    r"([.!?…]+[»”)]?)\s+(?=[A-ZÀ-ÖØ-Þ0-9«“(\-–•])"
)


@dataclass
class Segment:
    texte: str
    debut: int  # position du premier caractère dans le bloc d'origine
    fin: int    # position après le dernier caractère dans le bloc d'origine


def decouper_phrases(texte: str) -> list[tuple[int, int]]:
    """Renvoie les phrases d'un texte sous forme d'intervalles (début, fin).

    Les sauts de ligne (paragraphes, éléments de liste, rangées de tableau)
    sont aussi des frontières de phrase.
    """
    intervalles: list[tuple[int, int]] = []
    debut_ligne = 0
    for ligne in texte.split("\n"):
        fin_ligne = debut_ligne + len(ligne)
        curseur = debut_ligne
        for m in _FIN_PHRASE.finditer(ligne):
            fin = debut_ligne + m.end(1)
            intervalles.append((curseur, fin))
            curseur = debut_ligne + m.end()
        if ligne[curseur - debut_ligne:].strip():
            intervalles.append((curseur, fin_ligne))
        debut_ligne = fin_ligne + 1  # +1 pour le \n

    # On retire les espaces en bordure de chaque phrase
    propres = []
    for d, f in intervalles:
        while d < f and texte[d].isspace():
            d += 1
        while f > d and texte[f - 1].isspace():
            f -= 1
        if f > d:
            propres.append((d, f))
    return propres


def _couper_phrase_longue(texte: str, d: int, f: int, taille: int, chevauchement: int) -> list[tuple[int, int]]:
    """Découpe une phrase plus longue que `taille` sur les espaces, avec chevauchement."""
    morceaux = []
    debut = d
    while debut < f:
        fin = min(debut + taille, f)
        if fin < f:
            espace = texte.rfind(" ", debut + taille // 2, fin)
            if espace != -1:
                fin = espace
        morceaux.append((debut, fin))
        if fin >= f:
            break
        # Reprise en arrière pour le chevauchement, au début d'un mot
        reprise = max(fin - chevauchement, debut + 1)
        espace = texte.find(" ", reprise, fin)
        debut = espace + 1 if espace != -1 else fin
    return morceaux


def decouper(texte: str, taille: int = TAILLE_PAR_DEFAUT,
             chevauchement: int = CHEVAUCHEMENT_PAR_DEFAUT) -> list[Segment]:
    """Découpe un texte en segments d'environ `taille` caractères.

    - `chevauchement` : nombre de caractères (environ) repris à la fin du segment
      précédent. On reprend des phrases entières, jamais des morceaux de mots.
    - Un dernier segment trop petit (moins d'un quart de la taille) est fusionné
      avec le précédent, pour éviter les segments sans contexte.
    """
    if taille <= 0:
        raise ValueError("la taille doit être positive")
    if not 0 <= chevauchement < taille:
        raise ValueError("le chevauchement doit être compris entre 0 et la taille")

    # 1. Phrases, en découpant celles qui dépassent la taille
    unites: list[tuple[int, int]] = []
    for d, f in decouper_phrases(texte):
        if f - d > taille:
            unites.extend(_couper_phrase_longue(texte, d, f, taille, chevauchement))
        else:
            unites.append((d, f))
    if not unites:
        return []

    # 2. Regroupement des phrases jusqu'à la taille visée
    groupes: list[list[int]] = []  # indices des unités de chaque segment
    i = 0
    while i < len(unites):
        groupe = [i]
        j = i + 1
        while j < len(unites) and unites[j][1] - unites[groupe[0]][0] <= taille:
            groupe.append(j)
            j += 1
        groupes.append(groupe)
        if j >= len(unites):
            break
        # 3. Chevauchement : on recule sur les dernières phrases du groupe
        k = j
        while k - 1 > groupe[0] and unites[j - 1][1] - unites[k - 1][0] <= chevauchement:
            k -= 1
        i = k

    # 4. Fusion d'un dernier segment trop petit avec le précédent
    if len(groupes) >= 2:
        dernier = groupes[-1]
        nouveau = [u for u in dernier if u not in groupes[-2]]
        longueur_nouveau = sum(unites[u][1] - unites[u][0] for u in nouveau)
        if longueur_nouveau < taille // 4:
            groupes[-2] = sorted(set(groupes[-2]) | set(dernier))
            groupes.pop()

    segments = []
    for groupe in groupes:
        d, f = unites[groupe[0]][0], unites[groupe[-1]][1]
        segments.append(Segment(texte=texte[d:f], debut=d, fin=f))
    return segments


def decouper_document(document: dict, taille: int = TAILLE_PAR_DEFAUT,
                      chevauchement: int = CHEVAUCHEMENT_PAR_DEFAUT,
                      avec_contexte: bool = True) -> list[dict]:
    """Découpe un document produit par l'étape 2 (data/processed/<id>.json).

    Chaque segment garde : le document, le titre, la position (page / section),
    le numéro de bloc et ses positions de début et de fin dans le bloc.

    `avec_contexte=True` : le texte envoyé au modèle commence par le titre du
    document et la section. Un petit segment comme « Pas plus de 5 g par jour. »
    devient alors « Le sel — Le sel : Pas plus de 5 g par jour. », bien plus
    facile à retrouver par une question sur le sel.
    """
    segments = []
    for bloc in document.get("blocs", []):
        for rang, seg in enumerate(decouper(bloc["texte"], taille, chevauchement), start=1):
            contexte = document.get("titre") or ""
            if bloc.get("section") and bloc["section"].casefold() != contexte.casefold():
                contexte = f"{contexte} — {bloc['section']}" if contexte else bloc["section"]
            numero = len(segments) + 1
            segments.append({
                "id": f"{document['id']}_s{numero:04d}",
                "doc_id": document["id"],
                "titre": document.get("titre"),
                "fichier": document.get("fichier"),
                "format": document.get("format"),
                "position": bloc.get("position"),
                "page": bloc.get("page"),
                "section": bloc.get("section"),
                "bloc": bloc.get("numero"),
                "rang_dans_bloc": rang,
                "debut": seg.debut,
                "fin": seg.fin,
                "nombre_caracteres": len(seg.texte),
                "texte": seg.texte,
                "texte_a_vectoriser": f"{contexte} : {seg.texte}" if (avec_contexte and contexte) else seg.texte,
            })
    return segments


__all__ = ["Segment", "decouper", "decouper_document", "decouper_phrases",
           "TAILLE_PAR_DEFAUT", "CHEVAUCHEMENT_PAR_DEFAUT", "asdict"]
