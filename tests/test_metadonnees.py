"""Tests du script qui complète corpus_metadata.json."""

import json

from src.metadonnees import ecrire, proposer


def _projet(tmp_path):
    raw = tmp_path / "data" / "raw"
    for chemin in ["pdf/spf00001656.pdf", "pdf/NUT2012SA0103Ra-1.pdf", "docx/note.docx",
                   "html/Augmenter les légumes secs _ Manger Bouger.html", "txt/kk.txt"]:
        (raw / chemin).parent.mkdir(parents=True, exist_ok=True)
        (raw / chemin).write_bytes(b"x")
    meta = tmp_path / "corpus_metadata.json"
    meta.write_text(json.dumps({"nombre_documents": 1, "documents": [
        {"id": "doc_001", "fichier": "data/raw/docx/note.docx", "format": "docx", "titre": "Ma note"}]}),
        encoding="utf-8")
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "sans_meta_nut.json").write_text(json.dumps({
        "id": "sans_meta_nut", "fichier": "data/raw/pdf/NUT2012SA0103Ra-1.pdf",
        "titre": "Actualisation des repères du PNNS", "statistiques": {"nombre_pages": 280, "nombre_mots": 113239},
        "avertissements": ["pages sans texte : [2, 4]"]}), encoding="utf-8")
    return meta, raw, processed


def test_proposer_complete_les_fichiers_sans_fiche(tmp_path):
    meta, raw, processed = _projet(tmp_path)
    fiches = proposer(tmp_path, meta, raw, processed)
    par_fichier = {f["fichier"]: f for f in fiches}

    assert len(fiches) == 4 and "data/raw/docx/note.docx" not in par_fichier   # fiche existante gardée
    assert [f["id"] for f in fiches] == ["doc_002", "doc_003", "doc_004", "doc_005"]

    nut = par_fichier["data/raw/pdf/NUT2012SA0103Ra-1.pdf"]
    assert nut["titre"] == "Actualisation des repères du PNNS" and nut["auteur"] == "Anses"
    assert nut["nombre_pages"] == 280 and "pages sans texte" in nut["audit"] and nut["format"] == "pdf"

    html = par_fichier["data/raw/html/Augmenter les légumes secs _ Manger Bouger.html"]
    assert html["titre"] == "Augmenter les légumes secs" and html["format"] == "html"
    assert html["source"] == "https://www.mangerbouger.fr" and html["sous_theme"] == "repères de consommation"

    assert par_fichier["data/raw/pdf/spf00001656.pdf"]["auteur"] == "Santé publique France"
    assert par_fichier["data/raw/txt/kk.txt"]["auteur"] == "à compléter"


def test_ecrire_ajoute_et_met_a_jour_le_nombre(tmp_path):
    meta, raw, processed = _projet(tmp_path)
    ecrire(meta, proposer(tmp_path, meta, raw, processed))
    contenu = json.loads(meta.read_text(encoding="utf-8"))
    assert contenu["nombre_documents"] == 5 and contenu["documents"][0]["titre"] == "Ma note"
    assert proposer(tmp_path, meta, raw, processed) == []          # plus rien à compléter
