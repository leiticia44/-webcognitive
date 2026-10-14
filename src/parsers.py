"""Lecture des 4 formats du corpus : PDF, HTML, DOCX, TXT.

Chaque parseur renvoie un `DocumentParse` contenant une liste de blocs.
Un bloc = un morceau de texte + sa position dans le document d'origine
(page pour un PDF, section pour HTML/DOCX/TXT). Cette position sera réutilisée
plus tard pour citer précisément la source d'une réponse.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cleaning import nettoyer, normaliser_caracteres, retirer_entetes_pieds

# pypdf affiche de nombreux avertissements techniques sur les polices des PDF
# (« fontTools is required… »). Ils n'empêchent pas l'extraction du texte :
# on n'affiche que les vraies erreurs.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Formats reconnus, d'après l'extension du fichier
EXTENSIONS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".docx": "docx", ".txt": "txt"}

# En dessous de ce nombre moyen de caractères par page, un PDF est probablement scanné
SEUIL_PDF_SCANNE = 100


@dataclass
class Bloc:
    texte: str
    page: int | None = None      # numéro de page (PDF uniquement, à partir de 1)
    section: str | None = None   # titre de la section (HTML, DOCX, TXT)

    @property
    def position(self) -> str:
        """Position lisible, utilisée dans les citations : « page 3 » ou « section : Le sel »."""
        if self.page is not None:
            return f"page {self.page}"
        if self.section:
            return f"section : {self.section}"
        return "document"


@dataclass
class DocumentParse:
    format: str
    titre: str | None = None
    blocs: list[Bloc] = field(default_factory=list)
    nombre_pages: int | None = None
    avertissements: list[str] = field(default_factory=list)


class FormatNonSupporte(ValueError):
    pass


def detecter_format(chemin: Path) -> str:
    try:
        return EXTENSIONS[chemin.suffix.lower()]
    except KeyError:
        raise FormatNonSupporte(f"extension non prise en charge : {chemin.suffix}")


def parser_fichier(chemin: Path) -> DocumentParse:
    """Point d'entrée : choisit le bon parseur selon l'extension."""
    fmt = detecter_format(chemin)
    parseur = {"pdf": parser_pdf, "html": parser_html, "docx": parser_docx, "txt": parser_txt}[fmt]
    doc = parseur(chemin)
    # On écarte les blocs vides après nettoyage
    doc.blocs = [b for b in doc.blocs if b.texte.strip()]
    if not doc.blocs:
        doc.avertissements.append("aucun texte extrait")
    return doc


# --------------------------------------------------------------------------- PDF

def parser_pdf(chemin: Path) -> DocumentParse:
    from pypdf import PdfReader

    lecteur = PdfReader(str(chemin))
    pages_brutes = []
    for page in lecteur.pages:
        try:
            pages_brutes.append(normaliser_caracteres(page.extract_text() or ""))
        except Exception:  # une page abîmée ne doit pas bloquer tout le document
            pages_brutes.append("")
    pages = retirer_entetes_pieds(pages_brutes)

    titre = None
    if lecteur.metadata and lecteur.metadata.title:
        titre = str(lecteur.metadata.title).strip() or None

    doc = DocumentParse(format="pdf", titre=titre, nombre_pages=len(pages))
    for numero, texte in enumerate(pages, start=1):
        doc.blocs.append(Bloc(texte=nettoyer(texte, mode_pdf=True), page=numero))

    total = sum(len(b.texte) for b in doc.blocs)
    if pages and total / len(pages) < SEUIL_PDF_SCANNE:
        doc.avertissements.append(
            f"très peu de texte ({total} caractères pour {len(pages)} pages) : PDF scanné ? à écarter ou à vérifier"
        )
    pages_vides = [b.page for b in doc.blocs if not b.texte]
    if pages_vides and len(pages_vides) < len(pages):
        doc.avertissements.append(f"pages sans texte : {pages_vides}")
    return doc


# -------------------------------------------------------------------------- HTML

# Éléments qui ne font jamais partie du contenu utile
BALISES_A_SUPPRIMER = [
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "button", "svg", "iframe", "template", "link", "meta",
]

# Éléments parasites propres à certains sites (Wikipédia, sites institutionnels)
SELECTEURS_A_SUPPRIMER = [
    ".mw-editsection", "sup.reference", ".navbox", ".metadata", ".bandeau-container",
    "#toc", ".toc", ".mw-jump-link", ".noprint", ".printfooter", "#catlinks",
    ".mw-references-wrap", ".references", "[role=navigation]", "[aria-hidden=true]",
    ".breadcrumb", ".cookie", "#cookie-banner", ".share", ".social",
]

# Où chercher le contenu principal, du plus précis au plus général
SELECTEURS_CONTENU = ["#mw-content-text", "main", "article", "[role=main]", "#content", "body"]

TITRES = ["h1", "h2", "h3", "h4"]
BLOCS_TEXTE = ["p", "li", "table", "blockquote", "dt", "dd", "pre", "figcaption"]


def _texte_tableau(tableau) -> str:
    """Un tableau devient une ligne par rangée, cellules séparées par « | »."""
    lignes = []
    for rangee in tableau.find_all("tr"):
        cellules = [c.get_text(" ", strip=True) for c in rangee.find_all(["th", "td"])]
        cellules = [c for c in cellules if c]
        if cellules:
            lignes.append(" | ".join(cellules))
    return "\n".join(lignes)


def parser_html(chemin: Path) -> DocumentParse:
    from bs4 import BeautifulSoup

    # On lit les octets : BeautifulSoup détecte l'encodage (balise <meta charset>)
    soupe = BeautifulSoup(chemin.read_bytes(), "html.parser")

    titre = None
    if soupe.title and soupe.title.get_text(strip=True):
        titre = soupe.title.get_text(strip=True)
        # « Nutri-Score — Wikipédia » -> « Nutri-Score »
        titre = re.split(r"\s+[—–|-]\s+", titre)[0].strip()

    for balise in soupe(BALISES_A_SUPPRIMER):
        balise.decompose()
    for selecteur in SELECTEURS_A_SUPPRIMER:
        for element in soupe.select(selecteur):
            element.decompose()

    racine = None
    for selecteur in SELECTEURS_CONTENU:
        racine = soupe.select_one(selecteur)
        if racine is not None and racine.get_text(strip=True):
            break
    if racine is None:
        racine = soupe

    doc = DocumentParse(format="html", titre=titre)
    section = titre
    paragraphes: list[str] = []

    def fermer_section():
        if paragraphes:
            doc.blocs.append(Bloc(texte=nettoyer("\n\n".join(paragraphes)), section=section))
            paragraphes.clear()

    for element in racine.find_all(TITRES + BLOCS_TEXTE):
        # On ignore un élément contenu dans un autre déjà traité (ex. <p> dans <li> ou <table>)
        if element.find_parent(BLOCS_TEXTE) is not None:
            continue
        if element.name in TITRES:
            texte_titre = element.get_text(" ", strip=True)
            if texte_titre:
                fermer_section()
                section = texte_titre
                if doc.titre is None and element.name == "h1":
                    doc.titre = texte_titre
            continue
        if element.name == "table":
            texte = _texte_tableau(element)
        else:
            texte = element.get_text(" ", strip=True)
            if element.name == "li":
                texte = "- " + texte
        if texte:
            paragraphes.append(texte)
    fermer_section()

    if not doc.blocs:
        # Page sans structure (pas de <p>) : on garde le texte brut du contenu principal
        texte = nettoyer(racine.get_text("\n", strip=True))
        if texte:
            doc.blocs.append(Bloc(texte=texte, section=titre))
            doc.avertissements.append("structure HTML non reconnue : texte brut conservé")
    return doc


# -------------------------------------------------------------------------- DOCX

def _est_titre(style: str) -> bool:
    style = (style or "").lower()
    return style.startswith(("heading", "titre", "title"))


def parser_docx(chemin: Path) -> DocumentParse:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(chemin))
    titre = (document.core_properties.title or "").strip() or None

    doc = DocumentParse(format="docx", titre=titre)
    section = None
    paragraphes: list[str] = []

    def fermer_section():
        if paragraphes:
            doc.blocs.append(Bloc(texte=nettoyer("\n\n".join(paragraphes)), section=section or doc.titre))
            paragraphes.clear()

    # On parcourt le corps dans l'ordre pour garder paragraphes ET tableaux à leur place
    for enfant in document.element.body.iterchildren():
        balise = enfant.tag.split("}")[-1]
        if balise == "p":
            paragraphe = Paragraph(enfant, document)
            texte = paragraphe.text.strip()
            if not texte:
                continue
            style = paragraphe.style.name if paragraphe.style is not None else ""
            if _est_titre(style):
                fermer_section()
                section = texte
                if doc.titre is None:
                    doc.titre = texte
            else:
                if "list" in style.lower():
                    texte = "- " + texte
                paragraphes.append(texte)
        elif balise == "tbl":
            tableau = Table(enfant, document)
            lignes = []
            for rangee in tableau.rows:
                cellules = []
                for cellule in rangee.cells:
                    t = cellule.text.strip()
                    if t and (not cellules or cellules[-1] != t):  # cellules fusionnées répétées
                        cellules.append(t)
                if cellules:
                    lignes.append(" | ".join(cellules))
            if lignes:
                paragraphes.append("\n".join(lignes))
    fermer_section()
    return doc


# --------------------------------------------------------------------------- TXT

def lire_texte(chemin: Path) -> tuple[str, str]:
    """Lit un fichier texte en devinant son encodage. Renvoie (texte, encodage)."""
    octets = chemin.read_bytes()
    try:
        return octets.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    # Corpus en français : un .txt non UTF-8 vient presque toujours du Bloc-notes Windows (cp1252)
    try:
        return octets.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes

        meilleur = from_bytes(octets).best()
        if meilleur is not None:
            return str(meilleur), meilleur.encoding
    except ImportError:
        pass
    return octets.decode("latin-1"), "latin-1"


def _est_titre_txt(ligne: str) -> str | None:
    """Repère un titre dans un .txt : « # Titre » (Markdown) ou une ligne courte en MAJUSCULES."""
    ligne = ligne.strip()
    if ligne.startswith("#"):
        return ligne.lstrip("#").strip() or None
    lettres = [c for c in ligne if c.isalpha()]
    if 3 <= len(ligne) <= 80 and len(lettres) >= 3 and all(c.isupper() for c in lettres):
        return ligne
    return None


def parser_txt(chemin: Path) -> DocumentParse:
    texte, encodage = lire_texte(chemin)
    texte = normaliser_caracteres(texte)

    doc = DocumentParse(format="txt")
    if encodage != "utf-8":
        doc.avertissements.append(f"encodage {encodage} (pas UTF-8) : converti automatiquement")

    lignes = texte.split("\n")
    # Le titre = première ligne non vide
    premiere = next((l.strip() for l in lignes if l.strip()), None)
    doc.titre = _est_titre_txt(premiere) or premiere if premiere else None

    section = doc.titre
    courant: list[str] = []
    for ligne in lignes:
        titre = _est_titre_txt(ligne)
        if titre:
            if courant and "".join(courant).strip():
                doc.blocs.append(Bloc(texte=nettoyer("\n".join(courant)), section=section))
            courant = []
            section = titre
        else:
            courant.append(ligne)
    if "".join(courant).strip():
        doc.blocs.append(Bloc(texte=nettoyer("\n".join(courant)), section=section))
    return doc
