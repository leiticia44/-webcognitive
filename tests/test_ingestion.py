"""Tests du pipeline d'ingestion (étape 2).

Lancer depuis la racine du projet :  python -m pytest -v
Les fichiers de test sont fabriqués à la volée dans un dossier temporaire :
aucun document du vrai corpus n'est nécessaire.
"""

import json

import pytest

from src.cleaning import nettoyer, recoller_cesures, retirer_entetes_pieds
from src.ingest import executer
from src.parsers import parser_fichier


# ------------------------------------------------------------------- nettoyage

def test_espaces_et_ligatures():
    assert nettoyer("Les  ﬁbres : bien") == "Les fibres : bien"


def test_cesures():
    assert recoller_cesures("nutri-\ntionnel") == "nutritionnel"
    assert recoller_cesures("Nutri-\nScore") == "Nutri-Score"


def test_recollage_des_lignes_pdf():
    texte = "Manger au moins 5 fruits et\nlégumes par jour.\n- puce 1\n- puce 2"
    assert nettoyer(texte, mode_pdf=True) == (
        "Manger au moins 5 fruits et légumes par jour.\n- puce 1\n- puce 2"
    )


def test_titre_pdf_non_recolle():
    texte = "Les fruits et légumes\nManger au moins 5 portions de fruits et légu-\nmes par jour."
    assert nettoyer(texte, mode_pdf=True) == (
        "Les fruits et légumes\nManger au moins 5 portions de fruits et légumes par jour."
    )


def test_entetes_et_numeros_de_page():
    pages = [f"Guide nutrition 2019\nRepère {i}\nGuide nutrition - page {i}\n{i}" for i in range(1, 5)]
    assert retirer_entetes_pieds(pages) == [f"Repère {i}" for i in range(1, 5)]


# --------------------------------------------------------------------- formats

def test_txt_cp1252_et_sections(tmp_path):
    f = tmp_path / "article.txt"
    f.write_bytes("Les fibres\n\nTexte d'intro.\n\n# Bienfaits\n\nLes fibres régulent le transit.".encode("cp1252"))
    doc = parser_fichier(f)
    assert doc.titre == "Les fibres"
    assert [b.section for b in doc.blocs] == ["Les fibres", "Bienfaits"]
    assert "régulent" in doc.blocs[1].texte
    assert any("cp1252" in a for a in doc.avertissements)


def test_html_sections_tableau_et_parasites(tmp_path):
    f = tmp_path / "page.html"
    f.write_text("""<html><head><meta charset="utf-8"><title>Le sel — Manger Bouger</title></head>
    <body><nav>Menu Accueil</nav><main>
      <h1>Le sel</h1><p>Pas plus de 5 g par jour.</p>
      <h2>Où se cache-t-il ?</h2><ul><li><p>Pain</p></li><li>Charcuterie</li></ul>
      <table><tr><th>Aliment</th><th>Sel</th></tr><tr><td>Pain</td><td>1,2 g</td></tr></table>
      <script>alert(1)</script>
    </main><footer>Mentions légales</footer></body></html>""", encoding="utf-8")
    doc = parser_fichier(f)
    assert doc.titre == "Le sel"
    tout = "\n".join(b.texte for b in doc.blocs)
    assert "Menu" not in tout and "Mentions" not in tout and "alert" not in tout
    assert doc.blocs[0].section == "Le sel" and "5 g" in doc.blocs[0].texte
    assert doc.blocs[1].section == "Où se cache-t-il ?"
    assert "- Pain" in doc.blocs[1].texte and "Pain | 1,2 g" in doc.blocs[1].texte
    assert tout.count("Pain") == 2  # le <p> dans le <li> n'est pas compté deux fois


def test_docx_titres_et_tableau(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Les groupes d'aliments", level=1)
    d.add_paragraph("Introduction.")
    d.add_heading("Féculents", level=2)
    d.add_paragraph("Source d'énergie.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Pâtes", "glucides"
    f = tmp_path / "note.docx"
    d.save(f)
    doc = parser_fichier(f)
    assert doc.titre == "Les groupes d'aliments"
    assert [b.section for b in doc.blocs] == ["Les groupes d'aliments", "Féculents"]
    assert "Pâtes | glucides" in doc.blocs[1].texte


def _creer_pdf(chemin, pages):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    c = canvas.Canvas(str(chemin))
    for lignes in pages:
        y = 800
        for ligne in lignes:
            c.drawString(50, y, ligne)
            y -= 15
        c.showPage()
    c.save()


def test_pdf_pages_et_entetes(tmp_path):
    f = tmp_path / "guide.pdf"
    _creer_pdf(f, [["Guide PNNS", f"Repere numero {i} : manger", f"des legumes {i} fois.", "Fin de page", str(i)]
                    for i in range(1, 4)])
    doc = parser_fichier(f)
    assert doc.nombre_pages == 3
    assert [b.page for b in doc.blocs] == [1, 2, 3]
    assert doc.blocs[1].texte == "Repere numero 2 : manger des legumes 2 fois."


def test_pdf_scanne_signale(tmp_path):
    f = tmp_path / "scan.pdf"
    _creer_pdf(f, [[""], [""]])
    doc = parser_fichier(f)
    assert any("scanné" in a for a in doc.avertissements)


# ---------------------------------------------------------------- pipeline complet

def test_pipeline_et_controles_metadonnees(tmp_path):
    (tmp_path / "data/raw/txt").mkdir(parents=True)
    (tmp_path / "data/raw/txt/eau.txt").write_text("L'eau\n\nLa seule boisson indispensable.", encoding="utf-8")
    (tmp_path / "data/raw/txt/orphelin.txt").write_text("Sans fiche", encoding="utf-8")
    meta = tmp_path / "corpus_metadata.json"
    meta.write_text(json.dumps({
        "nombre_documents": 2,
        "documents": [
            {"id": "doc_001", "fichier": "data/raw/txt/eau.txt", "format": "txt", "titre": "Hydratation"},
            {"id": "doc_002", "fichier": "data/raw/pdf/absent.pdf", "format": "pdf"},
        ],
    }), encoding="utf-8")

    rapport = executer(tmp_path / "data/raw", tmp_path / "data/processed", meta, tmp_path)

    assert rapport["documents_traites"] == 2
    sortie = json.loads((tmp_path / "data/processed/doc_001.json").read_text(encoding="utf-8"))
    assert sortie["titre"] == "Hydratation"
    assert sortie["blocs"][0]["position"] == "section : L'eau"
    assert (tmp_path / "data/processed/sans_meta_orphelin.json").exists()
    controles = "\n".join(rapport["controles_metadonnees"])
    assert "introuvable : data/raw/pdf/absent.pdf" in controles
    assert "sans entrée dans corpus_metadata.json : data/raw/txt/orphelin.txt" in controles
    assert (tmp_path / "data/processed/rapport_ingestion.json").exists()
