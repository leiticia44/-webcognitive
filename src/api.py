"""API REST du WebCognitive Engine — FastAPI (étapes 4 et 5).

Lancement, depuis la racine du projet :

    uvicorn src.api:app --reload
    # ou : python -m src.api

Documentation interactive (Swagger) : http://127.0.0.1:8000/docs

Routes :
    GET    /                 informations sur l'API
    GET    /sante            l'API répond-elle ? combien de segments en base ?
    POST   /index            indexation complète : ingestion → découpage → vectorisation → base
    DELETE /index            vide la base vectorielle
    GET    /stats            réglages de la dernière indexation et statistiques
    GET    /documents        documents indexés et nombre de segments par document
    GET    /segments/{id}    un segment, avec son texte et ses métadonnées
    GET    /recherche?q=…    recherche sémantique : les K segments les plus proches d'une question
    POST   /chat             RAG : réponse du LLM local fondée sur le corpus, avec ses sources
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from .chunking import CHEVAUCHEMENT_PAR_DEFAUT, TAILLE_PAR_DEFAUT
from .embeddings import MODELE_PAR_DEFAUT, MODELES_CONNUS
from .indexation import indexer
from .llm import MODELE_LLM_PAR_DEFAUT, ClientOllama, OllamaIndisponible
from .rag import K_PAR_DEFAUT, SEUIL_PAR_DEFAUT, repondre

RACINE = Path(__file__).resolve().parent.parent
VERSION = "0.5.0"


# --------------------------------------------------------------------- modèles de données

class RequeteIndexation(BaseModel):
    ingestion: bool = Field(True, description="Relancer d'abord l'étape 2 (data/raw → data/processed)")
    taille: int = Field(TAILLE_PAR_DEFAUT, ge=50, le=5000, description="Taille visée des segments, en caractères")
    chevauchement: int = Field(CHEVAUCHEMENT_PAR_DEFAUT, ge=0, description="Caractères repris du segment précédent")
    modele: str = Field(MODELE_PAR_DEFAUT, description="Modèle d'embedding (nom Hugging Face, 'multilingue' ou 'minilm')")
    avec_contexte: bool = Field(True, description="Ajouter le titre et la section devant chaque segment")

    @model_validator(mode="after")
    def verifier_chevauchement(self):
        if self.chevauchement >= self.taille:
            raise ValueError("le chevauchement doit être inférieur à la taille")
        return self

    model_config = {"json_schema_extra": {"examples": [
        {"ingestion": True, "taille": 500, "chevauchement": 100, "modele": "multilingue", "avec_contexte": True}]}}


class Segment(BaseModel):
    id: str = Field(description="Identifiant unique du segment, ex. doc_001_s0004")
    score: float = Field(description="Similarité cosinus avec la question (1 = sens identique)")
    texte: str
    metadonnees: dict = Field(description="Fichier source, page ou section, titre, auteur, date…")


class RequeteChat(BaseModel):
    question: str = Field(..., min_length=2, description="La question, en langage naturel")
    k: int = Field(K_PAR_DEFAUT, ge=1, le=20, description="Nombre de segments donnés au LLM (Top-K)")
    seuil: float = Field(SEUIL_PAR_DEFAUT, ge=0, le=1,
                         description="Score minimal du meilleur segment pour interroger le LLM")
    modele_llm: str = Field(MODELE_LLM_PAR_DEFAUT, description="Modèle Ollama : mistral, llama3.1…")
    doc_id: Optional[str] = Field(None, description="Limiter la recherche à un document")
    format: Optional[str] = Field(None, description="Limiter à un format : pdf, html, docx, txt")

    model_config = {"json_schema_extra": {"examples": [
        {"question": "Combien de fois par semaine faut-il manger du poisson ?", "k": 5}]}}


class Source(BaseModel):
    numero: int = Field(description="Numéro utilisé dans la réponse : [1], [2]…")
    citee: bool = Field(description="Le LLM a-t-il cité cette source dans sa réponse ?")
    score: float
    segments: list[str]
    doc_id: Optional[str] = None
    titre: Optional[str] = None
    fichier: Optional[str] = None
    position: Optional[str] = None
    auteur: Optional[str] = None
    source: Optional[str] = None
    extrait: str


class ReponseChat(BaseModel):
    question: str
    reponse: str
    hors_corpus: bool = Field(description="Vrai si l'information n'est pas dans le corpus")
    llm_appele: bool = Field(description="Faux si aucun segment n'a dépassé le seuil")
    modele_llm: str
    seuil: float
    meilleur_score: float
    sources: list[Source]
    durees_s: dict


class ReponseRecherche(BaseModel):
    question: str
    modele: str
    resultats: list[Segment]


# --------------------------------------------------------------------- service

class Moteur:
    """Regroupe la base vectorielle et les modèles d'embedding, chargés une seule fois."""

    def __init__(self, racine: Path = RACINE, dossier_base: Path | None = None):
        self.racine = racine
        self.dossier_base = dossier_base or racine / "data" / "chroma"
        self.verrou = threading.Lock()  # une seule indexation à la fois
        self._base = None
        self._encodeurs: dict = {}
        self._llms: dict = {}

    @property
    def base(self):
        if self._base is None:
            from .vectorstore import BaseChroma
            self._base = BaseChroma(self.dossier_base)
        return self._base

    def encodeur(self, modele: str):
        nom = MODELES_CONNUS.get(modele, modele)
        if nom not in self._encodeurs:
            from .embeddings import EncodeurLocal
            self._encodeurs[nom] = EncodeurLocal(nom)
        return self._encodeurs[nom]

    def encodeur_de_la_base(self):
        """Le modèle d'embedding qui a servi à indexer (obligatoire pour comparer les vecteurs)."""
        return self.encodeur(self.base.reglages().get("modele", MODELE_PAR_DEFAUT))

    def llm(self, modele: str = MODELE_LLM_PAR_DEFAUT):
        if modele not in self._llms:
            self._llms[modele] = ClientOllama(modele)
        return self._llms[modele]


_moteur: Moteur | None = None


def obtenir_moteur() -> Moteur:
    global _moteur
    if _moteur is None:
        _moteur = Moteur()
    return _moteur


# --------------------------------------------------------------------- application

app = FastAPI(
    title="WebCognitive Engine — API d'indexation",
    version=VERSION,
    description="Indexation du corpus « alimentation et nutrition » dans une base vectorielle locale "
                "(ChromaDB), avec des embeddings calculés en local. Projet M2 THYP — étape 4.",
)


@app.get("/", tags=["Informations"])
def accueil():
    return {"nom": "WebCognitive Engine", "version": VERSION, "documentation": "/docs",
            "routes": ["/sante", "/index", "/stats", "/documents", "/segments/{id}", "/recherche", "/chat"]}


@app.get("/sante", tags=["Informations"])
def sante(moteur: Moteur = Depends(obtenir_moteur)):
    llm = moteur.llm()
    return {"statut": "ok", "segments_en_base": moteur.base.compter(),
            "indexation_en_cours": moteur.verrou.locked(),
            "llm": {"modele": llm.nom, "disponible": llm.disponible()}}


@app.post("/index", tags=["Indexation"], summary="Indexer tout le corpus")
def indexer_corpus(requete: RequeteIndexation = RequeteIndexation(),
                   moteur: Moteur = Depends(obtenir_moteur)):
    """Enchaîne tout le pipeline et renvoie un rapport JSON une fois l'opération terminée :

    1. (si `ingestion`) lecture et nettoyage des fichiers de `data/raw/` ;
    2. lecture des fichiers nettoyés de `data/processed/` ;
    3. découpage en segments avec chevauchement ;
    4. vectorisation locale ;
    5. enregistrement par lots dans la base vectorielle (la base est d'abord vidée).
    """
    if not moteur.verrou.acquire(blocking=False):
        raise HTTPException(409, "Une indexation est déjà en cours.")
    try:
        try:
            encodeur = moteur.encodeur(requete.modele)
        except ImportError as erreur:
            raise HTTPException(500, str(erreur))
        return indexer(
            moteur.base, encodeur, moteur.racine / "data" / "processed",
            taille=requete.taille, chevauchement=requete.chevauchement,
            avec_contexte=requete.avec_contexte, ingestion=requete.ingestion,
            dossier_raw=moteur.racine / "data" / "raw",
            fichier_metadonnees=moteur.racine / "corpus_metadata.json",
            racine=moteur.racine,
        )
    finally:
        moteur.verrou.release()


@app.delete("/index", tags=["Indexation"], summary="Vider la base vectorielle")
def vider(moteur: Moteur = Depends(obtenir_moteur)):
    if moteur.verrou.locked():
        raise HTTPException(409, "Une indexation est en cours.")
    moteur.base.reinitialiser({})
    return {"statut": "vide", "segments_en_base": moteur.base.compter()}


@app.get("/stats", tags=["Consultation"])
def stats(moteur: Moteur = Depends(obtenir_moteur)):
    documents = moteur.base.documents()
    par_format: dict[str, int] = {}
    for d in documents:
        par_format[d.get("format") or "?"] = par_format.get(d.get("format") or "?", 0) + 1
    return {"reglages": moteur.base.reglages(), "segments_en_base": moteur.base.compter(),
            "documents": len(documents), "documents_par_format": par_format}


@app.get("/documents", tags=["Consultation"])
def documents(moteur: Moteur = Depends(obtenir_moteur)):
    return moteur.base.documents()


@app.get("/segments/{identifiant}", tags=["Consultation"], response_model=Segment)
def segment(identifiant: str, moteur: Moteur = Depends(obtenir_moteur)):
    resultat = moteur.base.segment(identifiant)
    if resultat is None:
        raise HTTPException(404, f"Segment introuvable : {identifiant}")
    return resultat


@app.get("/recherche", tags=["Recherche et RAG"], response_model=ReponseRecherche,
         summary="Recherche sémantique : les K segments les plus proches")
def recherche(q: str = Query(..., min_length=2, description="La question, en langage naturel"),
              k: int = Query(5, ge=1, le=50, description="Nombre de segments renvoyés"),
              doc_id: Optional[str] = Query(None, description="Limiter à un document"),
              format: Optional[str] = Query(None, description="Limiter à un format : pdf, html, docx, txt"),
              moteur: Moteur = Depends(obtenir_moteur)):
    """La question est vectorisée avec **le même modèle que celui utilisé pour l'indexation**
    (sinon les vecteurs ne seraient pas comparables), puis comparée à tous les segments
    par similarité cosinus. Seuls les passages sont renvoyés, sans appel au LLM."""
    if not moteur.base.compter():
        raise HTTPException(409, "La base est vide : lancez d'abord POST /index.")
    modele = moteur.base.reglages().get("modele", MODELE_PAR_DEFAUT)
    vecteur = moteur.encodeur_de_la_base().encoder([q])[0]
    filtre = {c: v for c, v in (("doc_id", doc_id), ("format", format)) if v}
    return {"question": q, "modele": modele, "resultats": moteur.base.rechercher(vecteur, k, filtre)}


@app.post("/chat", tags=["Recherche et RAG"], response_model=ReponseChat,
          summary="Poser une question : réponse du LLM local avec ses sources")
def chat(requete: RequeteChat, moteur: Moteur = Depends(obtenir_moteur)):
    """Pipeline RAG complet :

    1. la question est vectorisée et comparée aux segments (similarité cosinus, Top-K) ;
    2. si le meilleur segment est sous le `seuil`, la réponse est « je ne sais pas » **sans appeler le LLM** ;
    3. sinon les segments sont injectés, numérotés [1], [2]…, dans un prompt strict qui oblige
       le LLM à répondre **uniquement** à partir de ce contexte et à citer ses sources ;
    4. le LLM local (Ollama) génère la réponse, renvoyée avec les sources et leurs extraits.
    """
    if not moteur.base.compter():
        raise HTTPException(409, "La base est vide : lancez d'abord POST /index.")
    filtre = {c: v for c, v in (("doc_id", requete.doc_id), ("format", requete.format)) if v}
    try:
        return repondre(requete.question, moteur.base, moteur.encodeur_de_la_base(),
                        moteur.llm(requete.modele_llm), requete.k, requete.seuil, filtre)
    except OllamaIndisponible as erreur:
        raise HTTPException(503, str(erreur))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=False)
