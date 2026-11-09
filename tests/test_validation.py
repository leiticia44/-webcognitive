"""Tests de l'étape 8 : rapport de validation (LLM factice, base en mémoire)."""

from src.indexation import indexer
from src.validation import chiffres_retrouves, lire_jeu, rapport_markdown, valider
from src.vectorstore import BaseMemoire
from tests.test_rag import LLMFactice
from tests.test_vectorisation import EncodeurFactice, _corpus

JEU = """# Questions

| # | Question | Réponse attendue | Source de référence | Format visé | Fichier source | Page / section | Vérifiée |
|---|---|---|---|---|---|---|---|
| 1 | Combien de fois par semaine manger du poisson ? | 2 fois par semaine, dont 1 poisson gras | SPF | PDF | data/raw/pdf/reperes.pdf | page 1 | ✅ |
| 2 | Quelle quantité de sel par jour ? | 5 g de sel | Santé.fr | HTML | | | ⬜ |

| Question | Comportement attendu |
|---|---|
| Quelle est la recette de la blanquette de veau ? | L'application indique que l'information n'est pas dans le corpus |
"""


def _base(tmp_path):
    _corpus(tmp_path / "processed")
    base = BaseMemoire()
    indexer(base, EncodeurFactice(), tmp_path / "processed")
    return base


def test_lire_jeu(tmp_path):
    (tmp_path / "q.md").write_text(JEU, encoding="utf-8")
    questions, pieges = lire_jeu(tmp_path / "q.md")
    assert [q["numero"] for q in questions] == ["1", "2"]          # même sans fichier source
    assert questions[0]["fichier"] == "data/raw/pdf/reperes.pdf" and questions[1]["fichier"] == ""
    assert questions[0]["attendue"].startswith("2 fois")
    assert pieges == [{"question": "Quelle est la recette de la blanquette de veau ?",
                       "attendu": "L'application indique que l'information n'est pas dans le corpus"}]


def test_chiffres_retrouves():
    assert chiffres_retrouves("5 g de sel (soit 2,4 g de sodium)", "Pas plus de 5 g, soit 2.4 g de sodium [1].")
    assert chiffres_retrouves("2 fois par semaine, dont 1 poisson gras", "Deux fois par semaine.") is False
    assert chiffres_retrouves("L'eau", "L'eau est la seule boisson indispensable.") is None


def test_valider_et_rapport(tmp_path):
    (tmp_path / "q.md").write_text(JEU, encoding="utf-8")
    questions, pieges = lire_jeu(tmp_path / "q.md")
    vus = []
    resultats = valider(questions, pieges, _base(tmp_path), EncodeurFactice(),
                        LLMFactice("Il faut en manger 2 fois par semaine, dont 1 poisson gras [1]."),
                        k=3, seuil=0.2, progression=lambda r, t, q: vus.append((r, t)))
    assert vus == [(1, 3), (2, 3), (3, 3)]

    [poisson, sel] = resultats["questions"]
    assert poisson["a_repondu"] and poisson["source_retrouvee"] and poisson["source_citee"]
    assert poisson["chiffres_retrouves"] is True
    assert sel["source_retrouvee"] is None                     # pas de fichier source renseigné
    [piege] = resultats["pieges"]
    assert piege["evite"] and not piege["llm_appele"]           # sous le seuil : LLM non appelé

    r = resultats["resume"]
    assert r["questions"] == 2 and r["questions_avec_source"] == 1 and r["source_citee"] == 1
    assert r["pieges_evites"] == 1 and r["pieges"] == 1

    md = rapport_markdown(resultats)
    assert md.startswith("# Rapport de validation")
    assert "| Questions pièges : « je ne sais pas » | 1 / 1 |" in md
    assert "✅ piège évité" in md and "reperes.pdf — page 1" in md
    assert md.count("⬜") == 2                                   # une case « Correcte » par question


def test_validation_sans_ollama(tmp_path):
    """Ollama arrêté : la validation tourne quand même, en mode extractif, et liste les sources."""
    from tests.test_rag import LLMEnPanne

    (tmp_path / "q.md").write_text(JEU, encoding="utf-8")
    questions, pieges = lire_jeu(tmp_path / "q.md")
    resultats = valider(questions, pieges, _base(tmp_path), EncodeurFactice(), LLMEnPanne(), k=3, seuil=0.2)
    poisson = resultats["questions"][0]
    assert poisson["mode"] == "extractif" and poisson["a_repondu"] and poisson["source_citee"]
    assert resultats["pieges"][0]["evite"]
    md = rapport_markdown(resultats)
    assert "Mode **extractif**" in md and "## Sources retrouvées pour chaque question" in md
    assert "- **1.** [1] reperes.pdf — page 1" in md

