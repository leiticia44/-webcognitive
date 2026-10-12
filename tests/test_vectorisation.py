"""Tests de l'étape 3 : découpage, vectorisation, évaluation.

Pour rester rapides et ne rien télécharger, les tests remplacent le vrai modèle
par un « encodeur factice » : un sac de mots haché en 384 dimensions. Il ne
comprend pas le sens, mais il suffit à vérifier toute la mécanique
(formes des matrices, sauvegarde, classement, métriques).
"""

import json
import re
import zlib

import numpy as np

from src.chunking import decouper, decouper_document, decouper_phrases
from src.embeddings import plus_proches
from src.evaluate import Question, bonne_position, evaluer, lire_questions
from src.vectorize import charger_index, executer


class EncodeurFactice:
    nom = "factice"

    def encoder(self, textes):
        vecteurs = np.zeros((len(textes), 384), dtype=np.float32)
        for i, texte in enumerate(textes):
            for mot in re.findall(r"\w{3,}", texte.lower()):
                vecteurs[i, zlib.crc32(mot.encode()) % 384] += 1
        normes = np.linalg.norm(vecteurs, axis=1, keepdims=True)
        return vecteurs / np.where(normes == 0, 1, normes)


TEXTE = " ".join(f"Phrase numéro {i} sur les repères alimentaires des adultes." for i in range(30))


# ------------------------------------------------------------------- phrases

def test_phrases_et_abreviations():
    t = "Le Nutri-Score va de A à E. Selon la p. 12, env. 5 portions ! « Oui » dit M. Dupont.\n- une puce"
    phrases = [t[d:f] for d, f in decouper_phrases(t)]
    assert phrases == [
        "Le Nutri-Score va de A à E.",
        "Selon la p. 12, env. 5 portions !",
        "« Oui » dit M. Dupont.",
        "- une puce",
    ]


# ------------------------------------------------------------------- découpage

def test_taille_respectee_et_phrases_entieres():
    segments = decouper(TEXTE, taille=200, chevauchement=60)
    assert len(segments) > 1
    for s in segments:
        assert len(s.texte) <= 200
        assert s.texte.startswith("Phrase") and s.texte.endswith(".")  # jamais coupé en pleine phrase
        assert TEXTE[s.debut:s.fin] == s.texte                          # positions exactes dans le bloc


def test_chevauchement():
    segments = decouper(TEXTE, taille=200, chevauchement=60)
    for precedent, suivant in zip(segments, segments[1:]):
        assert suivant.debut < precedent.fin                       # les segments se recouvrent
        assert precedent.texte.endswith(TEXTE[suivant.debut:precedent.fin])


def test_tout_le_texte_est_couvert():
    segments = decouper(TEXTE, taille=200, chevauchement=60)
    assert segments[0].debut == 0 and segments[-1].fin == len(TEXTE)
    for precedent, suivant in zip(segments, segments[1:]):
        assert suivant.debut <= precedent.fin + 1


def test_sans_chevauchement():
    segments = decouper(TEXTE, taille=200, chevauchement=0)
    for precedent, suivant in zip(segments, segments[1:]):
        assert suivant.debut > precedent.fin


def test_phrase_trop_longue_coupee_sur_les_espaces():
    texte = " ".join(["légumes"] * 120)
    segments = decouper(texte, taille=200, chevauchement=50)
    assert all(len(s.texte) <= 200 for s in segments)
    assert all(not s.texte.startswith(" ") and set(s.texte.split()) == {"légumes"} for s in segments)


def test_petit_dernier_segment_fusionne():
    # 3 phrases remplissent le segment (143 caractères) ; « Fin. » seul ferait un segment de 4 caractères
    texte = "Une phrase moyenne qui remplit bien le segment. " * 3 + "Fin."
    segments = decouper(texte, taille=145, chevauchement=0)
    assert len(segments) == 1 and segments[0].texte == texte


def test_document_garde_position_et_contexte():
    document = {"id": "doc_002", "titre": "Le sel", "fichier": "data/raw/html/sel.html", "format": "html",
                "blocs": [{"numero": 1, "position": "section : Où se cache le sel ?", "page": None,
                           "section": "Où se cache le sel ?", "texte": "Dans le pain. Dans la charcuterie."}]}
    [segment] = decouper_document(document)
    assert segment["id"] == "doc_002_s0001"
    assert segment["position"] == "section : Où se cache le sel ?"
    assert segment["texte"] == "Dans le pain. Dans la charcuterie."
    assert segment["texte_a_vectoriser"] == "Le sel — Où se cache le sel ? : Dans le pain. Dans la charcuterie."
    assert decouper_document(document, avec_contexte=False)[0]["texte_a_vectoriser"] == segment["texte"]


# ------------------------------------------------------------------ vectorisation

def _corpus(dossier):
    dossier.mkdir(parents=True)
    docs = {
        "doc_001": ("Repères adultes", "data/raw/pdf/reperes.pdf",
                    [(1, "Manger du poisson deux fois par semaine dont un poisson gras."),
                     (2, "Pratiquer trente minutes d'activité physique dynamique chaque jour.")]),
        "doc_002": ("Le sel", "data/raw/html/sel.html",
                    [(None, "Un adulte ne devrait pas consommer plus de cinq grammes de sel par jour.")]),
    }
    for doc_id, (titre, fichier, blocs) in docs.items():
        (dossier / f"{doc_id}.json").write_text(json.dumps({
            "id": doc_id, "titre": titre, "fichier": fichier, "format": fichier.split(".")[-1],
            "blocs": [{"numero": i, "page": p, "section": None if p else titre,
                       "position": f"page {p}" if p else f"section : {titre}", "texte": t}
                      for i, (p, t) in enumerate(blocs, start=1)]}), encoding="utf-8")
    (dossier / "rapport_ingestion.json").write_text("{}", encoding="utf-8")


def test_vectorisation_et_sauvegarde(tmp_path):
    _corpus(tmp_path / "processed")
    reglages = executer(tmp_path / "processed", tmp_path / "vectors", 500, 100, EncodeurFactice())
    assert reglages["statistiques"]["nombre_segments"] == 3
    assert reglages["dimensions"] == 384 and reglages["modele"] == "factice"

    segments, vecteurs, relu = charger_index(tmp_path / "vectors")
    assert vecteurs.shape == (3, 384) and vecteurs.dtype == np.float32
    assert np.allclose(np.linalg.norm(vecteurs, axis=1), 1)
    assert [s["position"] for s in segments] == ["page 1", "page 2", "section : Le sel"]
    assert relu["taille"] == 500


def test_plus_proches_classe_du_meilleur_au_moins_bon():
    vecteurs = np.eye(4, dtype=np.float32)
    question = np.array([0.1, 0.9, 0.3, 0], dtype=np.float32)
    assert [i for i, _ in plus_proches(question, vecteurs, 3)] == [1, 2, 0]


# -------------------------------------------------------------------- évaluation

def test_lecture_des_questions(tmp_path):
    md = tmp_path / "q.md"
    md.write_text(
        "| # | Question | Réponse attendue | Source de référence | Format visé | Fichier source | Page / section | Vérifiée |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| 1 | Combien de sel ? | 5 g | Santé.fr | HTML | sel.html | section : Le sel | ⬜ |\n"
        "| 2 | Question sans source | | | PDF | | | ⬜ |\n\n"
        "| Question | Comportement attendu |\n|---|---|\n| Recette de la blanquette ? | Hors corpus |\n",
        encoding="utf-8")
    questions, pieges = lire_questions(md)
    assert [(q.numero, q.fichier, q.position) for q in questions] == [("1", "sel.html", "section : Le sel")]
    assert pieges == ["Recette de la blanquette ?"]


def test_bonne_position():
    q = Question("1", "?", "reperes.pdf", "page 2")
    assert bonne_position({"page": 2}, q) is True
    assert bonne_position({"page": 3}, q) is False
    q = Question("2", "?", "sel.html", "Le sel")
    assert bonne_position({"page": None, "section": "Le sel"}, q) is True
    assert bonne_position({"page": None, "section": "Autre"}, Question("3", "?", "x", "")) is None


def test_evaluation(tmp_path):
    _corpus(tmp_path / "processed")
    from src.vectorize import charger_documents
    documents = charger_documents(tmp_path / "processed")
    questions = [Question("1", "Combien de grammes de sel par jour ?", "sel.html", "Le sel"),
                 Question("2", "Combien de fois manger du poisson par semaine ?", "reperes.pdf", "page 1")]
    r = evaluer(documents, questions, ["Recette de la blanquette de veau"], EncodeurFactice(), 500, 100)
    assert r.nombre_segments == 3
    assert r.top1 == 1.0 and r.mrr == 1.0 and r.position_top5 == 1.0
    assert r.score_max_pieges < r.score_moyen_corpus
