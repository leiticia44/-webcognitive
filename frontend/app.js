/* WebCognitive — interface de chat (étape 6).
 *
 * Toutes les requêtes vers l'API REST sont asynchrones (fetch + async/await) :
 *   GET  /sante   état de la base et du LLM
 *   POST /chat    question → réponse du LLM local + sources
 *   POST /index   réindexation du corpus
 *
 * Par défaut l'interface interroge l'API qui la sert (même adresse).
 * Pour viser une autre adresse : index.html?api=http://127.0.0.1:8000
 */

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const nombre = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

const el = (id) => document.getElementById(id);
const conversation = el("conversation");
const champ = el("question");
const bouton = el("envoyer");

// ------------------------------------------------------------------ appels à l'API

async function appeler(chemin, options = {}) {
  let reponse;
  try {
    reponse = await fetch(API + chemin, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new Error("L'API ne répond pas. Lancez-la avec « uvicorn src.api:app » puis rechargez la page.");
  }
  const donnees = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const detail = Array.isArray(donnees.detail)
      ? donnees.detail.map((d) => d.msg).join(" ; ")
      : donnees.detail;
    throw new Error(detail || `Erreur ${reponse.status} de l'API.`);
  }
  return donnees;
}

// ------------------------------------------------------------------ état de l'application

async function verifierEtat() {
  const pastille = document.querySelector(".pastille");
  const texte = el("etat-texte");
  try {
    const etat = await appeler("/sante");
    const segments = etat.segments_en_base;
    const llm = etat.llm || {};
    const morceaux = [];
    morceaux.push(segments ? `${nombre.format(segments)} passages indexés` : "Base vide : réindexez le corpus");
    morceaux.push(llm.disponible ? `${llm.modele} prêt` : `${llm.modele || "LLM"} indisponible (Ollama)`);
    texte.textContent = morceaux.join(", ");
    pastille.dataset.etat = segments && llm.disponible ? "ok" : "partiel";
  } catch (erreur) {
    texte.textContent = "API injoignable";
    pastille.dataset.etat = "erreur";
  }
}

// ------------------------------------------------------------------ affichage

function cloner(id) {
  return el(id).content.firstElementChild.cloneNode(true);
}

function defiler(element) {
  element.scrollIntoView({ block: "end", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

/** Texte de la réponse, avec les citations [1], [2, 3] transformées en boutons. */
function remplirTexte(paragraphe, texte, numerosValides) {
  paragraphe.textContent = "";
  const motif = /\[(\d+(?:\s*[,;]\s*\d+)*)\]/g;
  let position = 0;
  for (const m of texte.matchAll(motif)) {
    paragraphe.append(texte.slice(position, m.index));
    for (const n of m[1].split(/\s*[,;]\s*/).map(Number)) {
      if (!numerosValides.has(n)) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "citation";
      b.textContent = n;
      b.dataset.source = n;
      b.setAttribute("aria-label", `Voir la source ${n}`);
      paragraphe.append(b);
    }
    position = m.index + m[0].length;
  }
  paragraphe.append(texte.slice(position));
}

function niveauPertinence(score) {
  if (score >= 0.7) return 5;
  if (score >= 0.55) return 4;
  if (score >= 0.4) return 3;
  if (score >= 0.25) return 2;
  return 1;
}

function carteSource(source) {
  const carte = cloner("modele-source");
  carte.dataset.numero = source.numero;
  carte.classList.toggle("non-citee", !source.citee);
  carte.querySelector(".source-numero").textContent = source.numero;
  carte.querySelector(".source-fichier").textContent = (source.fichier || source.doc_id || "").split("/").pop();
  carte.querySelector(".source-position").textContent = source.position || "";
  const titre = [source.titre, source.auteur].filter(Boolean).join(", ");
  carte.querySelector(".source-titre").textContent = titre;
  const jauge = carte.querySelector(".pertinence");
  jauge.dataset.niveau = niveauPertinence(source.score);
  jauge.setAttribute("aria-label", `Pertinence ${nombre.format(source.score)} sur 1`);
  jauge.title = `Similarité avec la question : ${nombre.format(source.score)}`;
  carte.querySelector("blockquote").textContent = source.extrait;
  return carte;
}

function afficherReponse(tour, r) {
  tour.classList.remove("attente");
  tour.classList.toggle("hors-corpus", r.hors_corpus);
  const numeros = new Set(r.sources.map((s) => s.numero));
  remplirTexte(tour.querySelector(".reponse-texte"), r.reponse, numeros);

  const note = tour.querySelector(".reponse-note");
  if (!r.llm_appele) {
    note.textContent = `Aucun passage du corpus n'est assez proche de la question ` +
      `(meilleur score ${nombre.format(r.meilleur_score)}, seuil ${nombre.format(r.seuil)}). ` +
      `Le modèle de langage n'a pas été interrogé.`;
  } else {
    const d = r.durees_s || {};
    note.textContent = `Rédigé par ${r.modele_llm} en ${nombre.format((d.recherche || 0) + (d.generation || 0))} s ` +
      `à partir de ${r.sources.length} passage${r.sources.length > 1 ? "s" : ""} du corpus.`;
  }

  if (!r.sources.length) return;
  const section = tour.querySelector(".sources");
  section.hidden = false;
  const citees = r.sources.filter((s) => s.citee);
  const principales = citees.length ? citees : r.sources;
  const autres = citees.length ? r.sources.filter((s) => !s.citee) : [];

  section.querySelector(".sources-titre").textContent =
    citees.length ? (citees.length > 1 ? "Sources citées" : "Source citée") : "Passages consultés";
  section.querySelector(".sources-liste").append(...principales.map(carteSource));
  if (autres.length) {
    const bloc = section.querySelector(".sources-autres");
    bloc.hidden = false;
    bloc.querySelector("summary").textContent =
      `${autres.length} autre${autres.length > 1 ? "s" : ""} passage${autres.length > 1 ? "s" : ""} consulté${autres.length > 1 ? "s" : ""}`;
    bloc.querySelector(".sources-liste").append(...autres.map(carteSource));
  }
}

function afficherErreur(tour, message) {
  tour.classList.remove("attente");
  tour.classList.add("erreur");
  tour.querySelector(".reponse-texte").textContent = message;
}

// ------------------------------------------------------------------ poser une question

async function poser(question) {
  question = question.trim();
  if (!question || bouton.disabled) return;
  el("accueil").hidden = true;

  const bulle = cloner("modele-question");
  bulle.querySelector(".bulle").textContent = question;
  conversation.append(bulle);

  const tour = cloner("modele-reponse");
  tour.classList.add("attente");
  const texte = tour.querySelector(".reponse-texte");
  texte.textContent = "Recherche des passages et rédaction de la réponse…";
  conversation.append(tour);
  defiler(tour);

  // Un LLM sur processeur peut prendre plusieurs dizaines de secondes : on affiche le temps écoulé
  const debut = Date.now();
  const minuteur = setInterval(() => {
    const s = Math.round((Date.now() - debut) / 1000);
    texte.textContent = `Recherche des passages et rédaction de la réponse… ${s} s`;
  }, 1000);

  bouton.disabled = true;
  champ.value = "";
  ajusterHauteur();
  try {
    const corps = {
      question,
      k: Number(el("k").value) || 5,
      seuil: Number(el("seuil").value),
      modele_llm: el("modele").value.trim() || "mistral",
    };
    if (el("format").value) corps.format = el("format").value;
    afficherReponse(tour, await appeler("/chat", { method: "POST", body: corps }));
  } catch (erreur) {
    afficherErreur(tour, erreur.message);
  } finally {
    clearInterval(minuteur);
    bouton.disabled = false;
    champ.focus();
    defiler(tour);
  }
}

// ------------------------------------------------------------------ réindexation

async function reindexer() {
  const b = el("indexer");
  const etat = el("indexation-etat");
  b.disabled = true;
  etat.textContent = "Indexation en cours : lecture, découpage, vectorisation…";
  try {
    const r = await appeler("/index", { method: "POST", body: { ingestion: true } });
    etat.textContent = r.statut === "vide"
      ? r.message
      : `${nombre.format(r.segments_en_base)} passages indexés depuis ${r.documents} documents en ${nombre.format(r.duree_totale_s)} s.`;
  } catch (erreur) {
    etat.textContent = erreur.message;
  } finally {
    b.disabled = false;
    verifierEtat();
  }
}

// ------------------------------------------------------------------ interactions

function ajusterHauteur() {
  champ.style.height = "auto";
  champ.style.height = `${champ.scrollHeight}px`;
}

el("formulaire").addEventListener("submit", (e) => {
  e.preventDefault();
  poser(champ.value);
});

champ.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    poser(champ.value);
  }
});
champ.addEventListener("input", ajusterHauteur);

el("suggestions").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b) poser(b.textContent);
});

// Clic sur une citation [n] : ouvre et met en évidence la source correspondante
conversation.addEventListener("click", (e) => {
  const citation = e.target.closest(".citation");
  if (!citation) return;
  const reponse = citation.closest(".reponse");
  const carte = reponse.querySelector(`.source[data-numero="${citation.dataset.source}"]`);
  if (!carte) return;
  const autres = carte.closest(".sources-autres");
  if (autres) autres.open = true;
  carte.querySelector(".source-extrait").open = true;
  reponse.querySelectorAll(".surlignee").forEach((c) => c.classList.remove("surlignee"));
  carte.classList.add("surlignee");
  carte.scrollIntoView({ block: "nearest", behavior: "smooth" });
});

el("indexer").addEventListener("click", reindexer);

verifierEtat();
champ.focus();
