/* WebCognitive — tableau de bord du corpus (étape 7).
 *
 * Une seule requête asynchrone : GET /dataviz, qui renvoie toutes les statistiques
 * calculées sur la base vectorielle (voir src/dataviz.py).
 * Les graphiques sont dessinés en SVG, sans bibliothèque : la page fonctionne hors ligne.
 * Pour viser une autre adresse d'API : dataviz.html?api=http://127.0.0.1:8000
 */

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const nombre = new Intl.NumberFormat("fr-FR");
const decimal = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const pourcent = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 0 });
const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

const FORMATS = {
  pdf: { nom: "PDF", couleur: "var(--f-pdf)" },
  html: { nom: "Pages web", couleur: "var(--f-html)" },
  docx: { nom: "Word", couleur: "var(--f-docx)" },
  txt: { nom: "Texte", couleur: "var(--f-txt)" },
};
const infoFormat = (f) => FORMATS[f] || { nom: f || "?", couleur: "var(--f-autre)" };

let donnees = null;
let filtre = "";   // "" = tous les formats

// ------------------------------------------------------------------ outils SVG

function noeud(nom, attributs = {}, parent) {
  const n = document.createElementNS(SVG, nom);
  for (const [k, v] of Object.entries(attributs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function toile(conteneur, hauteur, description) {
  conteneur.replaceChildren();
  const largeur = Math.max(conteneur.clientWidth, 260);
  const svg = noeud("svg", { viewBox: `0 0 ${largeur} ${hauteur}`, role: "img", "aria-label": description }, conteneur);
  return { svg, largeur, hauteur };
}

function texte(parent, x, y, contenu, attributs = {}) {
  const t = noeud("text", { x, y, ...attributs }, parent);
  t.textContent = contenu;
  return t;
}

function couper(chaine, max) {
  return chaine.length > max ? chaine.slice(0, max - 1) + "…" : chaine;
}

// Barre horizontale aux extrémités de données arrondies (4 px), ancrée sur l'axe
function barreH(parent, x, y, longueur, epaisseur, couleur) {
  const r = Math.min(4, epaisseur / 2, longueur / 2);
  const l = Math.max(longueur, 0);
  const d = `M${x},${y} h${l - r} a${r},${r} 0 0 1 ${r},${r} v${epaisseur - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(l - r)} z`;
  return noeud("path", { d, fill: couleur }, parent);
}

function barreV(parent, x, base, hauteur, largeur, couleur) {
  const r = Math.min(4, largeur / 2, hauteur / 2);
  const h = Math.max(hauteur, 0);
  const d = `M${x},${base} v${-(h - r)} a${r},${r} 0 0 1 ${r},${-r} h${largeur - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
  return noeud("path", { d, fill: couleur }, parent);
}

// ------------------------------------------------------------------ infobulle

const bulle = $("infobulle");

function montrer(evenement, contenu) {
  bulle.replaceChildren(...contenu);
  bulle.hidden = false;
  const x = evenement.clientX ?? evenement.target.getBoundingClientRect().right;
  const y = evenement.clientY ?? evenement.target.getBoundingClientRect().top;
  const { width, height } = bulle.getBoundingClientRect();
  bulle.style.left = `${Math.min(x + 14, innerWidth - width - 8)}px`;
  bulle.style.top = `${Math.max(8, y - height - 12)}px`;
}
function cacher() { bulle.hidden = true; }

function ligne(contenu, classe) {
  const n = document.createElement(classe === "titre" ? "strong" : "span");
  if (classe && classe !== "titre") n.className = classe;
  n.textContent = contenu;
  return n;
}
const sautDeLigne = () => document.createElement("br");

// Zone de survol plus grande que la marque, accessible au clavier
function survol(cible, contenu) {
  cible.setAttribute("tabindex", "0");
  cible.style.cursor = "default";
  cible.addEventListener("mousemove", (e) => montrer(e, contenu()));
  cible.addEventListener("mouseleave", cacher);
  cible.addEventListener("focus", (e) => montrer(e, contenu()));
  cible.addEventListener("blur", cacher);
}

// ------------------------------------------------------------------ chiffres et filtres

function chiffres() {
  const t = donnees.totaux;
  const cases = [
    [t.documents, "documents indexés"],
    [t.segments, "segments dans la base"],
    [t.mots, "mots au total"],
    [t.formats, t.formats > 1 ? "formats de fichiers" : "format de fichier"],
    [t.longueur_moyenne, "caractères par segment en moyenne"],
  ];
  $("chiffres").replaceChildren(...cases.map(([valeur, libelle]) => {
    const div = document.createElement("div");
    div.className = "chiffre";
    div.append(ligne(nombre.format(valeur), "titre"), ligne(libelle));
    return div;
  }));
  const r = donnees.reglages || {};
  const morceaux = [];
  if (r.modele) morceaux.push(`Modèle d'embedding : ${String(r.modele).split("/").pop()}`);
  if (r.taille) morceaux.push(`segments de ${r.taille} caractères, chevauchement ${r.chevauchement ?? "?"}`);
  if (r.date) morceaux.push(`indexé le ${new Date(r.date).toLocaleString("fr-FR")}`);
  $("reglages").textContent = morceaux.join(" · ");
}

function puce(format, ronde = false) {
  const i = document.createElement("i");
  i.className = "puce-format" + (ronde ? " ronde" : "");
  i.style.background = infoFormat(format).couleur;
  return i;
}

function filtres() {
  const formats = donnees.formats.map((f) => f.format);
  const boutons = [["", "Tous"], ...formats.map((f) => [f, infoFormat(f).nom])].map(([valeur, nom]) => {
    const b = document.createElement("button");
    b.type = "button";
    if (valeur) b.append(puce(valeur));
    b.append(nom);
    b.setAttribute("aria-pressed", String(valeur === filtre));
    b.addEventListener("click", () => {
      filtre = valeur;
      for (const autre of $("filtres").children) autre.setAttribute("aria-pressed", String(autre === b));
      dessinerFiltres();
    });
    return b;
  });
  $("filtres").replaceChildren(...boutons);
}

function legende(id, formats, ronde) {
  $(id).replaceChildren(...formats.map((f) => {
    const s = document.createElement("span");
    s.append(puce(f, ronde), infoFormat(f).nom);
    return s;
  }));
}

const visibles = () => donnees.documents.filter((d) => !filtre || d.format === filtre);

// ------------------------------------------------------------------ graphiques

function graphiqueFormats() {
  const formats = donnees.formats;
  const pas = 34, marge = { haut: 4, gauche: 82, droite: 150 };
  const { svg, largeur } = toile($("g-formats"), marge.haut + formats.length * pas, "Documents par format");
  const max = Math.max(...formats.map((f) => f.documents), 1);
  const utile = largeur - marge.gauche - marge.droite;
  noeud("line", { x1: marge.gauche, x2: marge.gauche, y1: 0, y2: formats.length * pas + marge.haut, class: "axe" }, svg);
  formats.forEach((f, i) => {
    const y = marge.haut + i * pas;
    const g = noeud("g", { opacity: filtre && filtre !== f.format ? 0.3 : 1 }, svg);
    texte(g, marge.gauche - 8, y + 17, infoFormat(f.format).nom, { "text-anchor": "end" });
    barreH(g, marge.gauche, y + 6, (f.documents / max) * utile, 16, infoFormat(f.format).couleur);
    texte(g, marge.gauche + (f.documents / max) * utile + 6, y + 18,
      `${nombre.format(f.documents)} doc. · ${nombre.format(f.segments)} segments`, { class: "valeur" });
    const zone = noeud("rect", { x: 0, y, width: largeur, height: pas, fill: "transparent" }, g);
    survol(zone, () => [ligne(infoFormat(f.format).nom, "titre"),
      ligne(`${nombre.format(f.documents)} documents, ${nombre.format(f.segments)} segments`), sautDeLigne(),
      ligne(`${nombre.format(f.mots)} mots`, "discret")]);
  });
}

function graphiqueLongueurs() {
  const classes = donnees.longueurs;
  const hauteur = 190, marge = { haut: 10, bas: 26, gauche: 34, droite: 6 };
  const { svg, largeur } = toile($("g-longueurs"), hauteur, "Histogramme de la longueur des segments");
  const max = Math.max(...classes.map((c) => c.segments), 1);
  const utileH = hauteur - marge.haut - marge.bas, utileL = largeur - marge.gauche - marge.droite;
  const pas = utileL / classes.length, base = hauteur - marge.bas;
  for (const v of [0, 0.5, 1]) {
    const y = base - v * utileH;
    noeud("line", { x1: marge.gauche, x2: largeur - marge.droite, y1: y, y2: y, class: "grille-ligne" }, svg);
    texte(svg, marge.gauche - 6, y + 4, nombre.format(Math.round(v * max)), { "text-anchor": "end" });
  }
  const tousLes = Math.ceil(classes.length / Math.max(2, Math.floor(utileL / 60)));
  classes.forEach((c, i) => {
    const x = marge.gauche + i * pas;
    if (c.segments) barreV(svg, x + 1, base, (c.segments / max) * utileH, Math.max(pas - 2, 1), "var(--serie)");
    if (i % tousLes === 0) texte(svg, x, hauteur - 8, nombre.format(c.debut));
    const zone = noeud("rect", { x, y: marge.haut, width: pas, height: utileH, fill: "transparent" }, svg);
    survol(zone, () => [ligne(`${nombre.format(c.debut)} à ${nombre.format(c.fin)} caractères`, "titre"),
      ligne(`${nombre.format(c.segments)} segments`)]);
  });
  noeud("line", { x1: marge.gauche, x2: largeur - marge.droite, y1: base, y2: base, class: "axe" }, svg);
  const t = donnees.totaux;
  $("longueurs-note").textContent = `Nombre de segments par tranche de 50 caractères. ` +
    `Médiane : ${nombre.format(t.longueur_mediane)} caractères${donnees.reglages?.taille ? `, pour une taille visée de ${donnees.reglages.taille}` : ""}.`;
}

function graphiqueDocuments() {
  const docs = [...visibles()].sort((a, b) => b.segments - a.segments || a.doc_id.localeCompare(b.doc_id));
  legende("legende-documents", [...new Set(docs.map((d) => d.format))], false);
  const conteneur = $("g-documents");
  if (!docs.length) { conteneur.replaceChildren(ligne("Aucun document pour ce format.", "vide")); return; }
  const pas = 26, marge = { gauche: Math.min(260, Math.max(140, conteneur.clientWidth * 0.34)), droite: 48 };
  const { svg, largeur } = toile(conteneur, docs.length * pas + 4, "Nombre de segments par document");
  const max = Math.max(...docs.map((d) => d.segments), 1);
  const utile = largeur - marge.gauche - marge.droite;
  const caracteres = Math.floor(marge.gauche / 6.6);
  noeud("line", { x1: marge.gauche, x2: marge.gauche, y1: 0, y2: docs.length * pas + 4, class: "axe" }, svg);
  docs.forEach((d, i) => {
    const y = 2 + i * pas;
    texte(svg, marge.gauche - 8, y + 16, couper(d.titre, caracteres), { "text-anchor": "end" });
    barreH(svg, marge.gauche, y + 4, (d.segments / max) * utile, pas - 8, infoFormat(d.format).couleur);
    texte(svg, marge.gauche + (d.segments / max) * utile + 6, y + 17, nombre.format(d.segments), { class: "valeur" });
    const zone = noeud("rect", { x: 0, y, width: largeur, height: pas, fill: "transparent" }, svg);
    survol(zone, () => [ligne(d.titre, "titre"),
      ligne(`${infoFormat(d.format).nom} · ${nombre.format(d.segments)} segments · ${nombre.format(d.mots || 0)} mots`), sautDeLigne(),
      ligne(d.fichier || d.doc_id, "discret")]);
  });
}

function graphiqueCarte() {
  const carte = donnees.carte;
  const points = carte.points.filter((p) => !filtre || p.format === filtre);
  legende("legende-carte", [...new Set(carte.points.map((p) => p.format))], true);
  const v = carte.variance_expliquee || [0, 0];
  let note = `Chaque point est un segment. Les vecteurs à 384 dimensions sont projetés sur un plan par analyse ` +
    `en composantes principales : deux points proches parlent de la même chose. Les deux axes résument ` +
    `${pourcent.format(v[0] + v[1])} de l'information des vecteurs.`;
  if (carte.echantillon) note += ` Échantillon de ${nombre.format(carte.points.length)} segments sur ${nombre.format(carte.segments_total)}.`;
  $("carte-note").textContent = note;

  const conteneur = $("g-carte");
  const hauteur = Math.round(Math.min(460, Math.max(280, conteneur.clientWidth * 0.55)));
  const { svg, largeur } = toile(conteneur, hauteur, "Carte sémantique des segments");
  const tous = carte.points;
  if (!tous.length) return;
  const xs = tous.map((p) => p.x), ys = tous.map((p) => p.y);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  // Marges intérieures : les libellés des axes restent hors de la zone des points
  const m = { haut: 30, bas: 30, cote: 16 };
  const px = (x) => m.cote + ((x - x0) / (x1 - x0 || 1)) * (largeur - 2 * m.cote);
  const py = (y) => hauteur - m.bas - ((y - y0) / (y1 - y0 || 1)) * (hauteur - m.haut - m.bas);
  noeud("rect", { x: 0.5, y: 0.5, width: largeur - 1, height: hauteur - 1, rx: 8, fill: "none", class: "axe" }, svg);
  texte(svg, largeur - 8, hauteur - 8, "axe principal 1 →", { "text-anchor": "end" });
  texte(svg, 10, 18, "↑ axe principal 2");

  const groupe = noeud("g", {}, svg);
  for (const p of points) {
    // 2 px d'anneau couleur du fond pour séparer les points qui se chevauchent
    noeud("circle", { cx: px(p.x), cy: py(p.y), r: 4.5, fill: infoFormat(p.format).couleur,
      stroke: "var(--surface)", "stroke-width": 2 }, groupe);
  }
  // Survol : le point le plus proche du curseur (rayon de 18 px), plus facile que de viser un point de 9 px
  const actif = noeud("circle", { r: 7, fill: "none", class: "marque-active", visibility: "hidden" }, svg);
  const zone = noeud("rect", { x: 0, y: 0, width: largeur, height: hauteur, fill: "transparent" }, svg);
  zone.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const echelle = largeur / rect.width;
    const cx = (e.clientX - rect.left) * echelle, cy = (e.clientY - rect.top) * echelle;
    let meilleur = null, distance = 18 * echelle;
    for (const p of points) {
      const d = Math.hypot(px(p.x) - cx, py(p.y) - cy);
      if (d < distance) { meilleur = p; distance = d; }
    }
    if (!meilleur) { cacher(); actif.setAttribute("visibility", "hidden"); return; }
    actif.setAttribute("cx", px(meilleur.x)); actif.setAttribute("cy", py(meilleur.y));
    actif.setAttribute("visibility", "visible");
    montrer(e, [ligne(meilleur.titre || meilleur.doc_id, "titre"),
      ligne(`${infoFormat(meilleur.format).nom}${meilleur.position ? " · " + meilleur.position : ""}`, "discret"), sautDeLigne(),
      ligne(`« ${meilleur.extrait}${meilleur.extrait.length >= 160 ? "…" : ""} »`)]);
  });
  zone.addEventListener("mouseleave", () => { cacher(); actif.setAttribute("visibility", "hidden"); });
}

function graphiqueMots() {
  const mots = donnees.mots_cles.slice(0, 15);
  const conteneur = $("g-mots");
  if (!mots.length) { conteneur.replaceChildren(ligne("Pas assez de texte.", "vide")); return; }
  const pas = 22, marge = { gauche: 120, droite: 44 };
  const { svg, largeur } = toile(conteneur, mots.length * pas + 4, "Mots les plus fréquents du corpus");
  const max = mots[0].occurrences;
  const utile = largeur - marge.gauche - marge.droite;
  noeud("line", { x1: marge.gauche, x2: marge.gauche, y1: 0, y2: mots.length * pas + 4, class: "axe" }, svg);
  mots.forEach((m, i) => {
    const y = 2 + i * pas;
    texte(svg, marge.gauche - 8, y + 15, couper(m.mot, 18), { "text-anchor": "end" });
    barreH(svg, marge.gauche, y + 4, (m.occurrences / max) * utile, pas - 8, "var(--serie)");
    texte(svg, marge.gauche + (m.occurrences / max) * utile + 6, y + 16, nombre.format(m.occurrences), { class: "valeur" });
    const zone = noeud("rect", { x: 0, y, width: largeur, height: pas, fill: "transparent" }, svg);
    survol(zone, () => [ligne(m.mot, "titre"),
      ligne(`${nombre.format(m.occurrences)} occurrences dans ${nombre.format(m.documents)} document${m.documents > 1 ? "s" : ""}`)]);
  });
}

// Échelle séquentielle à une seule teinte (vert), du clair au foncé
const RAMPE = ["#e3efe5", "#b9dbc3", "#86c19b", "#4fa370", "#1f8550", "#02612f"];
function teinte(t) {
  const i = Math.max(0, Math.min(RAMPE.length - 1, Math.round(t * (RAMPE.length - 1))));
  return RAMPE[i];
}

function graphiqueSimilarites() {
  const { documents: ids, matrice } = donnees.similarites;
  const titres = Object.fromEntries(donnees.documents.map((d) => [d.doc_id, d]));
  const garder = ids.map((id, i) => [id, i]).filter(([id]) => !filtre || titres[id]?.format === filtre);
  const conteneur = $("g-similarites");
  if (garder.length < 2) {
    conteneur.replaceChildren(ligne("Il faut au moins deux documents pour comparer.", "vide"));
    $("echelle-similarites").replaceChildren();
    return;
  }
  const valeurs = [];
  for (const [, i] of garder) for (const [, j] of garder) if (i !== j) valeurs.push(matrice[i][j]);
  const min = Math.min(...valeurs), max = Math.max(...valeurs);
  const n = garder.length;
  const etiquettes = n <= 24;
  const marge = etiquettes ? 64 : 4;
  const largeurDispo = Math.max(conteneur.clientWidth, 260);
  const cote = Math.max(4, Math.min(34, Math.floor((largeurDispo - marge - 4) / n)));
  const { svg } = toile(conteneur, marge + n * cote + 4, "Matrice de similarité entre documents");
  garder.forEach(([idA, i], a) => {
    if (etiquettes) {
      texte(svg, marge - 6, marge + a * cote + cote / 2 + 4, idA.replace(/^doc_/, "doc "), { "text-anchor": "end" });
      texte(svg, 0, 0, idA.replace(/^doc_/, "doc "), {
        transform: `translate(${marge + a * cote + cote / 2 + 4}, ${marge - 6}) rotate(-90)` });
    }
    garder.forEach(([idB, j], b) => {
      const v = matrice[i][j];
      const t = i === j ? 1 : (v - min) / (max - min || 1);
      const c = noeud("rect", { x: marge + b * cote + 1, y: marge + a * cote + 1, width: cote - 2, height: cote - 2,
        rx: Math.min(3, cote / 4), fill: i === j ? "var(--grille)" : teinte(t) }, svg);
      survol(c, () => i === j
        ? [ligne(titres[idA]?.titre || idA, "titre"), ligne("le document comparé à lui-même", "discret")]
        : [ligne(`Similarité ${decimal.format(v)}`, "titre"),
          ligne(titres[idA]?.titre || idA), sautDeLigne(), ligne(titres[idB]?.titre || idB)]);
    });
  });
  const echelle = $("echelle-similarites");
  const barre = document.createElement("i");
  barre.style.background = `linear-gradient(90deg, ${RAMPE.join(", ")})`;
  echelle.replaceChildren(ligne(decimal.format(min)), barre, ligne(decimal.format(max)));
}

// ------------------------------------------------------------------ tableaux

function cellule(contenu, classe) {
  const td = document.createElement("td");
  if (classe) td.className = classe;
  if (contenu instanceof Node) td.append(contenu); else td.textContent = contenu ?? "—";
  return td;
}
function entete(colonnes) {
  const tr = document.createElement("tr");
  for (const [nom, classe] of colonnes) {
    const th = document.createElement("th");
    th.textContent = nom;
    th.scope = "col";
    if (classe) th.className = classe;
    tr.append(th);
  }
  const thead = document.createElement("thead");
  thead.append(tr);
  return thead;
}

function tableauDocuments() {
  const table = $("t-documents");
  const corps = document.createElement("tbody");
  for (const d of visibles()) {
    const tr = document.createElement("tr");
    const format = document.createElement("span");
    format.className = "format-etiquette";
    format.append(puce(d.format), infoFormat(d.format).nom);
    tr.append(cellule(d.titre), cellule(format), cellule(nombre.format(d.segments), "nombre"),
      cellule(nombre.format(d.mots || 0), "nombre"), cellule(d.pages ? nombre.format(d.pages) : "—", "nombre"),
      cellule((d.mots_cles || []).join(", "), "mots-cles"));
    corps.append(tr);
  }
  table.replaceChildren(entete([["Document"], ["Format"], ["Segments", "nombre"], ["Mots", "nombre"],
    ["Pages", "nombre"], ["Mots-clés"]]), corps);
}

function tableauEvaluation() {
  const lignes = donnees.evaluation || [];
  $("bloc-evaluation").hidden = !lignes.length;
  if (!lignes.length) return;
  const corps = document.createElement("tbody");
  for (const l of lignes) {
    const tr = document.createElement("tr");
    tr.append(cellule(String(l.modele || "").split("/").pop()), cellule(nombre.format(l.taille), "nombre"),
      cellule(nombre.format(l.nombre_segments ?? 0), "nombre"), cellule(pourcent.format(l.top1 || 0), "nombre"),
      cellule(pourcent.format(l.top5 || 0), "nombre"), cellule(decimal.format(l.mrr || 0), "nombre"),
      cellule(l.score_max_pieges == null ? "—" : decimal.format(l.score_max_pieges), "nombre"));
    corps.append(tr);
  }
  $("t-evaluation").replaceChildren(entete([["Modèle"], ["Taille", "nombre"], ["Segments", "nombre"],
    ["Bonne source en 1re position", "nombre"], ["Dans les 5 premiers", "nombre"], ["MRR", "nombre"],
    ["Score max. des pièges", "nombre"]]), corps);
}

// ------------------------------------------------------------------ chargement

function dessinerFiltres() {
  graphiqueFormats();
  graphiqueDocuments();
  graphiqueCarte();
  graphiqueSimilarites();
  tableauDocuments();
}

function dessiner() {
  cacher();
  graphiqueLongueurs();
  graphiqueMots();
  dessinerFiltres();
}

async function charger() {
  const message = $("message");
  try {
    let reponse;
    try {
      reponse = await fetch(API + "/dataviz");
    } catch {
      throw new Error("L'API ne répond pas. Lancez-la avec « uvicorn src.api:app » puis rechargez la page.");
    }
    if (!reponse.ok) {
      const d = await reponse.json().catch(() => ({}));
      throw new Error(d.detail || `Erreur ${reponse.status} de l'API.`);
    }
    donnees = await reponse.json();
  } catch (erreur) {
    message.textContent = erreur.message;
    message.dataset.type = "erreur";
    return;
  }
  if (donnees.vide) {
    message.textContent = "La base est vide : indexez d'abord le corpus (bouton « Réindexer le corpus » dans l'assistant, ou POST /index).";
    return;
  }
  message.hidden = true;
  $("contenu").hidden = false;
  chiffres();
  filtres();
  tableauEvaluation();
  dessiner();
}

let minuterie;
addEventListener("resize", () => {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => donnees && !donnees.vide && dessiner(), 150);
});

charger();
