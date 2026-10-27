/* Swiss Law Map — zoomable map of Swiss law.
   Data: data/core.json (every circle), data/titles.<lang>.json, data/p/<n>.json (articles, loaded on zoom).
   Rendering: Canvas 2D in double precision (deep zoom), hierarchical culling, labels with collision tests. */
(() => {
  "use strict";

  // ---------- i18n ----------
  const T = {
    de: {
      name: "Karte des Schweizer Rechts", search: "Erlass, Artikel (Art. 41 OR) oder SR-Nummer",
      home: "Übersicht", period: "Zeitraum", legend: "Legende", method: "Methode", from: "Von", to: "Bis",
      CH: "Landesrecht", INT: "Völkerrecht", KT: "Kantonales Recht", root: "Schweizer Recht",
      decisions: "Entscheide", decN: (n) => `${n} Entscheide`,
      citeAct: "Entscheide, die auf diesen Erlass verweisen", citeArt: "Entscheide, die auf diesen Artikel verweisen",
      citeArea: "Entscheide, die auf mindestens einen Erlass dieses Bereichs verweisen",
      inPeriod: (a, b) => `davon ${a}–${b}`, federalShare: "davon Bundesgerichte und -behörden",
      perYear: "Entscheide pro Jahr (Entscheiddatum)", topDec: "Meistzitierte Entscheide, die auf diesen Erlass verweisen",
      topDecArt: "Meistzitierte Entscheide, die auf diesen Artikel verweisen", citedBy: (n) => `zitiert von ${n}`,
      topArts: "Meistzitierte Artikel (verweisende Entscheide)", coActs: "Häufig zusammen zitierte Erlasse",
      coArts: "Häufig zusammen zitierte Artikel", together: (n, l) => `${n} gemeinsam · ${l}× erwartet`,
      coNote: "Gemeinsam = Entscheide, die beide zitieren. «× erwartet»: so viel häufiger als bei unabhängiger Zitierung (Lift). Mindestens 20 (Erlasse) bzw. 10 (Artikel) gemeinsame Entscheide, Lift ≥ 2.",
      children: "Grösste Teile", articles: "Artikel", articlesIn: (n) => `${n} Artikel im geltenden Text`,
      notFound: "Nicht im Text gefunden", nfNote: (r, d) => `${r} Verweise aus ${d} Entscheiden nennen einen Artikel, den der massgebende Text nicht enthält (Extraktionsfehler oder andere Fassung).`,
      noText: (r) => `${r} Verweise auf Artikel konnten nicht geprüft werden: Fedlex veröffentlicht keinen Text dieses Erlasses.`,
      official: "Offizieller Text (Fedlex)", cantonal: "Kantonale Gesetzessammlung", openDec: "Entscheid auf OpenCaseLaw",
      sr: "SR", inForce: "In Kraft", earlier: "Früherer Erlass unter derselben SR-Nummer", successor: "Heute gilt",
      edition: "Frühere Fassung (aStGB, aZGB, aOR)", repealed: "Im geltenden Text aufgehoben",
      cantonalAct: "Kantonaler Erlass", cantonalNoTitle: "Abkürzung aus den Entscheiden; kein amtlicher Titel zugeordnet (keine kantonale Abkürzungstabelle).",
      bucket: "Weitere Abkürzungen", bucketNote: (c, k) => `${c} Abkürzungen, die je von weniger als 5 Entscheiden aus ${k} genannt werden, zusammengefasst.`,
      none: "Keine Treffer", loading: "Lade …", path: "Gliederung", art: "Art.", act: "Erlass", area: "Bereich",
      decisionsInCorpus: "Entscheide im Korpus", periodNote: "Gefüllte Fläche: Anteil der Entscheide im Zeitraum. Entscheide ohne verlässliches Datum zählen nur im Total.",
      noArticles: "Für diesen Erlass zeigt die Karte keine Artikel (kein Fedlex-Text).", group: "Erlass mit Ausführungserlassen",
      share: "Link", copied: "Kopiert",
    },
    fr: {
      name: "Carte du droit suisse", search: "Acte, article (art. 41 CO) ou numéro RS",
      home: "Vue d’ensemble", period: "Période", legend: "Légende", method: "Méthode", from: "De", to: "À",
      CH: "Droit interne", INT: "Droit international", KT: "Droit cantonal", root: "Droit suisse",
      decisions: "décisions", decN: (n) => `${n} décisions`,
      citeAct: "Décisions qui renvoient à cet acte", citeArt: "Décisions qui renvoient à cet article",
      citeArea: "Décisions qui renvoient à au moins un acte de ce domaine",
      inPeriod: (a, b) => `dont ${a}–${b}`, federalShare: "dont tribunaux et autorités fédéraux",
      perYear: "Décisions par année (date de la décision)", topDec: "Décisions les plus citées qui renvoient à cet acte",
      topDecArt: "Décisions les plus citées qui renvoient à cet article", citedBy: (n) => `citée par ${n}`,
      topArts: "Articles les plus cités (décisions qui y renvoient)", coActs: "Actes souvent cités ensemble",
      coArts: "Articles souvent cités ensemble", together: (n, l) => `${n} ensemble · ${l}× l’attendu`,
      coNote: "Ensemble = décisions qui citent les deux. «× l’attendu» : combien de fois plus souvent qu’une citation indépendante (lift). Au moins 20 (actes) ou 10 (articles) décisions communes, lift ≥ 2.",
      children: "Plus grandes parties", articles: "Articles", articlesIn: (n) => `${n} articles dans le texte en vigueur`,
      notFound: "Absents du texte", nfNote: (r, d) => `${r} renvois provenant de ${d} décisions citent un article absent du texte déterminant (erreur d’extraction ou autre version).`,
      noText: (r) => `${r} renvois à des articles n’ont pas pu être vérifiés : Fedlex ne publie aucun texte de cet acte.`,
      official: "Texte officiel (Fedlex)", cantonal: "Recueil cantonal", openDec: "Décision sur OpenCaseLaw",
      sr: "RS", inForce: "En vigueur", earlier: "Acte antérieur sous le même numéro RS", successor: "Aujourd’hui en vigueur",
      edition: "Version antérieure (aCP, aCC, aCO)", repealed: "Abrogé dans le texte en vigueur",
      cantonalAct: "Acte cantonal", cantonalNoTitle: "Abréviation tirée des décisions ; aucun titre officiel attribué (pas de table cantonale des abréviations).",
      bucket: "Autres abréviations", bucketNote: (c, k) => `${c} abréviations citées chacune par moins de 5 décisions de ${k}, regroupées.`,
      none: "Aucun résultat", loading: "Chargement …", path: "Structure", art: "art.", act: "Acte", area: "Domaine",
      decisionsInCorpus: "décisions dans le corpus", periodNote: "Surface pleine : part des décisions de la période. Les décisions sans date fiable ne comptent que dans le total.",
      noArticles: "La carte ne montre pas d’articles pour cet acte (pas de texte Fedlex).", group: "Acte avec actes d’exécution",
      share: "Lien", copied: "Copié",
    },
    it: {
      name: "Mappa del diritto svizzero", search: "Atto, articolo (art. 41 CO) o numero RS",
      home: "Panoramica", period: "Periodo", legend: "Legenda", method: "Metodo", from: "Da", to: "A",
      CH: "Diritto interno", INT: "Diritto internazionale", KT: "Diritto cantonale", root: "Diritto svizzero",
      decisions: "decisioni", decN: (n) => `${n} decisioni`,
      citeAct: "Decisioni che rinviano a questo atto", citeArt: "Decisioni che rinviano a questo articolo",
      citeArea: "Decisioni che rinviano ad almeno un atto di questo settore",
      inPeriod: (a, b) => `di cui ${a}–${b}`, federalShare: "di cui tribunali e autorità federali",
      perYear: "Decisioni per anno (data della decisione)", topDec: "Decisioni più citate che rinviano a questo atto",
      topDecArt: "Decisioni più citate che rinviano a questo articolo", citedBy: (n) => `citata da ${n}`,
      topArts: "Articoli più citati (decisioni che vi rinviano)", coActs: "Atti spesso citati insieme",
      coArts: "Articoli spesso citati insieme", together: (n, l) => `${n} insieme · ${l}× l’atteso`,
      coNote: "Insieme = decisioni che citano entrambi. «× l’atteso»: quante volte più spesso che con citazioni indipendenti (lift). Almeno 20 (atti) o 10 (articoli) decisioni comuni, lift ≥ 2.",
      children: "Parti più grandi", articles: "Articoli", articlesIn: (n) => `${n} articoli nel testo in vigore`,
      notFound: "Non trovati nel testo", nfNote: (r, d) => `${r} rinvii da ${d} decisioni citano un articolo assente dal testo determinante (errore di estrazione o altra versione).`,
      noText: (r) => `${r} rinvii ad articoli non hanno potuto essere verificati: Fedlex non pubblica alcun testo di questo atto.`,
      official: "Testo ufficiale (Fedlex)", cantonal: "Raccolta cantonale", openDec: "Decisione su OpenCaseLaw",
      sr: "RS", inForce: "In vigore", earlier: "Atto precedente con lo stesso numero RS", successor: "Oggi in vigore",
      edition: "Versione precedente (aCP, aCC, aCO)", repealed: "Abrogato nel testo in vigore",
      cantonalAct: "Atto cantonale", cantonalNoTitle: "Abbreviazione tratta dalle decisioni; nessun titolo ufficiale attribuito (manca una tabella cantonale delle abbreviazioni).",
      bucket: "Altre abbreviazioni", bucketNote: (c, k) => `${c} abbreviazioni citate ciascuna da meno di 5 decisioni di ${k}, raggruppate.`,
      none: "Nessun risultato", loading: "Caricamento …", path: "Struttura", art: "art.", act: "Atto", area: "Settore",
      decisionsInCorpus: "decisioni nel corpus", periodNote: "Superficie piena: quota delle decisioni nel periodo. Le decisioni senza data affidabile contano solo nel totale.",
      noArticles: "La mappa non mostra articoli per questo atto (nessun testo Fedlex).", group: "Atto con atti esecutivi",
      share: "Link", copied: "Copiato",
    },
    en: {
      name: "Map of Swiss law", search: "Act, article (Art. 41 CO) or SR number",
      home: "Overview", period: "Period", legend: "Legend", method: "Method", from: "From", to: "To",
      CH: "Domestic law", INT: "International law", KT: "Cantonal law", root: "Swiss law",
      decisions: "decisions", decN: (n) => `${n} decisions`,
      citeAct: "Decisions referring to this act", citeArt: "Decisions referring to this article",
      citeArea: "Decisions referring to at least one act in this area",
      inPeriod: (a, b) => `of which ${a}–${b}`, federalShare: "of which federal courts and authorities",
      perYear: "Decisions per year (date of decision)", topDec: "Most-cited decisions referring to this act",
      topDecArt: "Most-cited decisions referring to this article", citedBy: (n) => `cited by ${n}`,
      topArts: "Most-cited articles (referring decisions)", coActs: "Acts often cited together",
      coArts: "Articles often cited together", together: (n, l) => `${n} together · ${l}× expected`,
      coNote: "Together = decisions citing both. “× expected”: how many times more often than independent citation would predict (lift). At least 20 (acts) or 10 (articles) shared decisions, lift ≥ 2.",
      children: "Largest parts", articles: "Articles", articlesIn: (n) => `${n} articles in the current text`,
      notFound: "Not found in the text", nfNote: (r, d) => `${r} references from ${d} decisions name an article that the applicable text does not contain (extraction error or another version).`,
      noText: (r) => `${r} article references could not be checked: Fedlex publishes no text of this act.`,
      official: "Official text (Fedlex)", cantonal: "Cantonal collection", openDec: "Decision on OpenCaseLaw",
      sr: "SR", inForce: "In force", earlier: "Earlier act under the same SR number", successor: "In force today",
      edition: "Earlier edition (aStGB, aZGB, aOR)", repealed: "Repealed in the current text",
      cantonalAct: "Cantonal act", cantonalNoTitle: "Abbreviation as used in the decisions; no official title assigned (no cantonal abbreviation table exists).",
      bucket: "Other abbreviations", bucketNote: (c, k) => `${c} abbreviations, each cited by fewer than 5 decisions from ${k}, pooled.`,
      none: "No matches", loading: "Loading …", path: "Structure", art: "Art.", act: "Act", area: "Area",
      decisionsInCorpus: "decisions in the corpus", periodNote: "Filled area: share of decisions in the period. Decisions without a reliable date count only in the total.",
      noArticles: "The map shows no articles for this act (no Fedlex text).", group: "Act with implementing acts",
      share: "Link", copied: "Copied",
    },
  };
  const CANTON = {
    ZH: ["Zürich", "Zurich", "Zurigo", "Zurich"], BE: ["Bern", "Berne", "Berna", "Bern"], LU: ["Luzern", "Lucerne", "Lucerna", "Lucerne"],
    UR: ["Uri", "Uri", "Uri", "Uri"], SZ: ["Schwyz", "Schwytz", "Svitto", "Schwyz"], OW: ["Obwalden", "Obwald", "Obvaldo", "Obwalden"],
    NW: ["Nidwalden", "Nidwald", "Nidvaldo", "Nidwalden"], GL: ["Glarus", "Glaris", "Glarona", "Glarus"], ZG: ["Zug", "Zoug", "Zugo", "Zug"],
    FR: ["Freiburg", "Fribourg", "Friburgo", "Fribourg"], SO: ["Solothurn", "Soleure", "Soletta", "Solothurn"],
    BS: ["Basel-Stadt", "Bâle-Ville", "Basilea Città", "Basel-Stadt"], BL: ["Basel-Landschaft", "Bâle-Campagne", "Basilea Campagna", "Basel-Landschaft"],
    SH: ["Schaffhausen", "Schaffhouse", "Sciaffusa", "Schaffhausen"], AR: ["Appenzell Ausserrhoden", "Appenzell Rhodes-Extérieures", "Appenzello Esterno", "Appenzell Ausserrhoden"],
    AI: ["Appenzell Innerrhoden", "Appenzell Rhodes-Intérieures", "Appenzello Interno", "Appenzell Innerrhoden"],
    SG: ["St. Gallen", "Saint-Gall", "San Gallo", "St. Gallen"], GR: ["Graubünden", "Grisons", "Grigioni", "Graubünden"],
    AG: ["Aargau", "Argovie", "Argovia", "Aargau"], TG: ["Thurgau", "Thurgovie", "Turgovia", "Thurgau"], TI: ["Tessin", "Tessin", "Ticino", "Ticino"],
    VD: ["Waadt", "Vaud", "Vaud", "Vaud"], VS: ["Wallis", "Valais", "Vallese", "Valais"], NE: ["Neuenburg", "Neuchâtel", "Neuchâtel", "Neuchâtel"],
    GE: ["Genf", "Genève", "Ginevra", "Geneva"], JU: ["Jura", "Jura", "Giura", "Jura"],
  };
  const LANGS = ["de", "fr", "it", "en"];

  // ---------- state ----------
  const $ = (id) => document.getElementById(id);
  const canvas = $("map"), ctx = canvas.getContext("2d");
  let lang = pickLang(), t = T[lang], fmt = new Intl.NumberFormat(lang + "-CH");
  let core, titles = [], N = 0;
  let X, Y, R, P, D, NC, K, HUE, kids, ids, idIndex, adj, PK;
  let W = 0, H = 0, dpr = 1;
  const cam = { x: 0, y: 0, k: 1 };
  let anim = null, dirty = true;
  let sel = { i: -1, art: null }, hover = { i: -1, art: null };
  const packs = new Map(), packWait = new Map();
  let period = null;          // [y0, y1] or null
  let colors = {};
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ART_SHOW = 90;        // act screen radius (px) from which its articles are drawn

  function pickLang() {
    try { const s = localStorage.getItem("slm-lang"); if (LANGS.includes(s)) return s; } catch (e) { /* storage unavailable */ }
    const n = (navigator.language || "de").slice(0, 2);
    return LANGS.includes(n) ? n : "de";
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (n) => fmt.format(n || 0);
  const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });

  // ---------- data ----------
  async function boot() {
    const [c, tt] = await Promise.all([getJSON("data/core.json"), getJSON(`data/titles.${lang}.json`)]);
    core = c; titles = tt;
    const nodes = core.nodes;
    N = nodes.length;
    X = new Float64Array(N); Y = new Float64Array(N); R = new Float64Array(N);
    P = new Int32Array(N); D = new Int32Array(N); NC = new Float64Array(N); PK = new Int32Array(N).fill(-1);
    K = new Array(N); HUE = new Array(N); ids = new Array(N); kids = Array.from({ length: N }, () => []);
    idIndex = new Map();
    for (let i = 0; i < N; i++) {
      const o = nodes[i];
      X[i] = o.x; Y[i] = o.y; R[i] = o.r; P[i] = o.p; K[i] = o.k; NC[i] = o.n || 0; ids[i] = o.i;
      if (o.pk !== undefined) PK[i] = o.pk;
      idIndex.set(o.i, i);
      if (o.p >= 0) { kids[o.p].push(i); D[i] = D[o.p] + 1; }
      HUE[i] = hueOf(o, i);
    }
    adj = Array.from({ length: N }, () => []);
    for (const [a, b, n, l] of core.edges) { adj[a].push([b, n, l]); adj[b].push([a, n, l]); }
    for (const a of adj) a.sort((p, q) => q[1] * Math.log(q[2]) - p[1] * Math.log(p[2]));
    readColors();
    buildLegend();
    applyLang();
    resize();
    fitHome(false);
    $("loading").hidden = true;
    const h = decodeHash();
    if (h) select(h.i, h.art, true);
    requestDraw();
  }

  function hueOf(o, i) {
    if (o.k === "domain") return o.i === "KT" ? "k" : "n";
    if (o.k === "root") return "n";
    if (o.c) return "k";
    const sr = o.sr || "";
    if (sr) return sr.startsWith("0.") ? sr[2] : sr[0];
    return i > 0 && P[i] >= 0 ? HUE[P[i]] : "n";
  }

  function readColors() {
    const cs = getComputedStyle(document.documentElement);
    const g = (v) => cs.getPropertyValue(v).trim();
    colors = { bg: g("--bg"), fg: g("--fg"), muted: g("--muted"), halo: g("--halo"), line: g("--line"), hue: {} };
    for (const k of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "k", "n"]) colors.hue[k] = hexRGB(g("--d" + k));
    colors.fgRGB = hexRGB(colors.fg);
    colors.dark = luminance(hexRGB(colors.bg)) < 0.3;
    rgbaCache.clear();
  }
  function hexRGB(h) {
    h = h.replace("#", "");
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const v = parseInt(h, 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  const luminance = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const rgbaCache = new Map();
  function rgba(hue, a) {
    const key = hue + a.toFixed(3);
    let v = rgbaCache.get(key);
    if (!v) { const c = hue === "fg" ? colors.fgRGB : colors.hue[hue]; v = `rgba(${c[0]},${c[1]},${c[2]},${a.toFixed(3)})`; rgbaCache.set(key, v); }
    return v;
  }

  function label(i) {
    const o = core.nodes[i];
    if (o.k === "root") return t.root;
    if (o.k === "domain") return t[o.i];
    if (o.k === "canton") return CANTON[o.c] ? CANTON[o.c][LANGS.indexOf(lang)] : o.c;
    if (o.k === "bucket") return `${t.bucket} (${o.codes})`;
    if (o.k === "act") {
      const a = o.a ? (o.a[lang] || o.a.de || o.a.fr || o.a.it) : null;
      if (a) return o.reg && o.reg !== "a" ? `${a} ${o.reg}` : (o.reg === "a" ? `a${a}` : a);
      return o.sr ? `SR ${o.sr}${o.reg ? "@" + o.reg : ""}` : o.i;
    }
    return title(i) || o.sr || o.i;
  }
  function title(i) {
    const v = titles[i];
    return v == null ? "" : typeof v === "string" ? v : v[0];
  }
  function titleLang(i) { const v = titles[i]; return v && typeof v !== "string" ? v[1] : null; }

  // ---------- packs ----------
  function ensurePack(pk) {
    if (pk < 0 || packs.has(pk)) return packs.get(pk) ? Promise.resolve(packs.get(pk)) : null;
    if (packWait.has(pk)) return packWait.get(pk);
    const pr = getJSON(`data/p/${pk}.json`).then((d) => { packs.set(pk, d); packWait.delete(pk); requestDraw(); refreshPanel(); return d; })
      .catch(() => { packWait.delete(pk); });
    packWait.set(pk, pr);
    return pr;
  }
  function actRec(i) { const p = packs.get(PK[i]); return p ? p.acts[ids[i]] : null; }
  function decInfo(i, did) { const p = packs.get(PK[i]); return p ? p.dec[did] : null; }

  // ---------- camera ----------
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    requestDraw();
  }
  const isPhone = () => W <= 760;
  function viewRect() {
    // the part of the screen not covered by the panel
    const open = !$("panel").hidden;
    if (!open) return { x0: 0, y0: 0, x1: W, y1: H };
    if (isPhone()) return { x0: 0, y0: 70, x1: W, y1: H - Math.min(H * 0.52, 460) - 20 };
    return { x0: 0, y0: 0, x1: W - 400 - 24, y1: H };
  }
  const sx = (x) => (x - cam.x) * cam.k + W / 2;
  const sy = (y) => (y - cam.y) * cam.k + H / 2;
  const wx = (px) => (px - W / 2) / cam.k + cam.x;
  const wy = (py) => (py - H / 2) / cam.k + cam.y;

  function targetFor(i) {
    const v = viewRect();
    const vw = v.x1 - v.x0, vh = v.y1 - v.y0;
    const k = Math.min(vw, vh) * (K[i] === "act" ? 0.86 : 0.92) / (2 * R[i]);
    // centre the circle in the free part of the screen
    const cx = X[i] - ((v.x0 + v.x1) / 2 - W / 2) / k;
    const cy = Y[i] - ((v.y0 + v.y1) / 2 - H / 2) / k;
    return { x: cx, y: cy, k };
  }
  function fitHome(animate = true) {
    // frame the bounding box of the three domains, below the search bar
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const j of kids[0]) { x0 = Math.min(x0, X[j] - R[j]); x1 = Math.max(x1, X[j] + R[j]); y0 = Math.min(y0, Y[j] - R[j]); y1 = Math.max(y1, Y[j] + R[j]); }
    const v = viewRect(), top = isPhone() ? 120 : 80, bottom = isPhone() ? 70 : 20;
    const k = Math.min((v.x1 - v.x0 - 32) / (x1 - x0), (v.y1 - v.y0 - top - bottom) / (y1 - y0));
    const to = { x: (x0 + x1) / 2 - ((v.x0 + v.x1) / 2 - W / 2) / k, y: (y0 + y1) / 2 - ((v.y0 + top + v.y1 - bottom) / 2 - H / 2) / k, k };
    flyTo(to, animate);
  }
  function flyTo(to, animate = true) {
    if (!animate || reduceMotion) { Object.assign(cam, to); anim = null; requestDraw(); return; }
    const m = Math.min(W, H);
    const interp = interpolateZoom([cam.x, cam.y, m / cam.k], [to.x, to.y, m / to.k]);
    const dur = Math.max(350, Math.min(1500, interp.duration * 0.9));
    const t0 = performance.now();
    anim = (now) => {
      let u = Math.min(1, (now - t0) / dur);
      u = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      const [x, y, w] = interp(u);
      cam.x = x; cam.y = y; cam.k = m / w;
      if (u >= 1) anim = null;
    };
    requestDraw();
  }
  // van Wijk & Nuij smooth zoom (as in d3-interpolate interpolateZoom)
  function interpolateZoom(p0, p1) {
    const rho = Math.SQRT2, rho2 = 2, rho4 = 4;
    const [ux0, uy0, w0] = p0, [ux1, uy1, w1] = p1;
    const dx = ux1 - ux0, dy = uy1 - uy0, d2 = dx * dx + dy * dy;
    let i, S;
    if (d2 < 1e-12) {
      S = Math.log(w1 / w0) / rho;
      i = (u) => [ux0 + u * dx, uy0 + u * dy, w0 * Math.exp(rho * u * S)];
    } else {
      const d1 = Math.sqrt(d2);
      const b0 = (w1 * w1 - w0 * w0 + rho4 * d2) / (2 * w0 * rho2 * d1);
      const b1 = (w1 * w1 - w0 * w0 - rho4 * d2) / (2 * w1 * rho2 * d1);
      const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0), r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1);
      S = (r1 - r0) / rho;
      i = (u) => {
        const s = u * S, c0 = Math.cosh(r0);
        const uu = w0 / (rho2 * d1) * (c0 * Math.tanh(rho * s + r0) - Math.sinh(r0));
        return [ux0 + uu * dx, uy0 + uu * dy, w0 * c0 / Math.cosh(rho * s + r0)];
      };
    }
    i.duration = Math.abs(S) * 1000;
    return i;
  }
  function zoomAt(px, py, f) {
    const x = wx(px), y = wy(py);
    cam.k = Math.max(0.05, Math.min(cam.k * f, 5e7));
    cam.x = x - (px - W / 2) / cam.k;
    cam.y = y - (py - H / 2) / cam.k;
    anim = null;
    requestDraw();
  }

  // ---------- drawing ----------
  function requestDraw() { if (!dirty) { dirty = true; requestAnimationFrame(frame); } }
  dirty = false;
  function frame(now) {
    dirty = false;
    if (anim) { anim(now); dirty = true; requestAnimationFrame(frame); }
    if (!core) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, W, H);
    const vis = collect();
    drawCircles(vis);
    for (const i of vis.expanded) drawArticles(i);
    drawEdges();
    drawLabels(vis);
    drawRings();
    window.__slmFrame = performance.now() - now;
  }

  function share(o, rec) {
    // share of decisions inside the period, from the per-year counts
    if (!period) return 1;
    const ys = rec ? rec.ys : o.ys, y0 = rec ? rec.y0 : o.y0, n = rec ? rec.n : o.n;
    if (!ys || !n) return 0;
    let s = 0;
    for (let y = Math.max(period[0], y0); y <= Math.min(period[1], y0 + ys.length - 1); y++) s += ys[y - y0];
    return Math.min(1, s / n);
  }

  function collect() {
    const byDepth = [], expanded = [], stack = [0];
    const k = cam.k;
    while (stack.length) {
      const i = stack.pop();
      const r = R[i] * k, x = sx(X[i]), y = sy(Y[i]);
      if (x + r < 0 || x - r > W || y + r < 0 || y - r > H || r < 0.35) continue;
      (byDepth[D[i]] || (byDepth[D[i]] = [])).push(i);
      if (K[i] === "act") {
        if (PK[i] >= 0 && r > ART_SHOW * 0.7) { ensurePack(PK[i]); if (r > ART_SHOW && actRec(i) && actRec(i).arts) expanded.push(i); }
        continue;
      }
      if (r > 2.5) for (const c of kids[i]) stack.push(c);
    }
    return { byDepth, expanded };
  }

  function drawCircles(vis) {
    const k = cam.k, dark = colors.dark;
    for (const list of vis.byDepth) {
      if (!list) continue;
      const groups = new Map();
      for (const i of list) {
        const kind = K[i];
        if (kind === "root") continue;
        const key = kind + HUE[i];
        let g = groups.get(key);
        if (!g) groups.set(key, (g = { kind, hue: HUE[i], items: [] }));
        g.items.push(i);
      }
      for (const g of groups.values()) {
        const { kind, hue } = g;
        if (kind === "act" || kind === "bucket") {
          for (const i of g.items) drawAct(i, hue);
          continue;
        }
        const fillA = kind === "domain" ? (dark ? 0.035 : 0.03) : kind === "canton" ? 0.07 : (dark ? 0.085 : 0.075);
        ctx.beginPath();
        for (const i of g.items) { const r = R[i] * k; ctx.moveTo(sx(X[i]) + r, sy(Y[i])); ctx.arc(sx(X[i]), sy(Y[i]), r, 0, 6.2832); }
        ctx.fillStyle = rgba(hue, fillA);
        ctx.fill();
        ctx.lineWidth = kind === "domain" ? 1.2 : 0.8;
        ctx.strokeStyle = rgba(hue, kind === "domain" ? 0.35 : (dark ? 0.32 : 0.28));
        ctx.stroke();
      }
    }
  }

  function drawAct(i, hue) {
    const r = R[i] * cam.k, x = sx(X[i]), y = sy(Y[i]);
    const o = core.nodes[i];
    // fade the disc as the articles take over
    const fade = PK[i] >= 0 && actRec(i) && actRec(i).arts ? Math.max(0, Math.min(1, (r - ART_SHOW) / 120)) : 0;
    const base = (colors.dark ? 0.62 : 0.58) * (1 - 0.82 * fade);
    const sh = period ? share(o) : 1;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832);
    ctx.fillStyle = rgba(hue, period ? base * 0.28 : base);
    ctx.fill();
    if (period && sh > 0 && fade < 1) {
      ctx.beginPath(); ctx.arc(x, y, r * Math.sqrt(sh), 0, 6.2832);
      ctx.fillStyle = rgba(hue, base); ctx.fill();
    }
    if (r > 3) { ctx.lineWidth = r > 40 ? 1.2 : 0.8; ctx.strokeStyle = rgba(hue, 0.9); ctx.stroke(); }
    if (o.reg && r > 6) { // earlier act or edition: dashed rim
      ctx.setLineDash([3, 3]); ctx.lineWidth = 1; ctx.strokeStyle = rgba("fg", 0.45); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  function drawArticles(i) {
    const rec = actRec(i);
    const k = cam.k, hue = HUE[i];
    const fadeIn = Math.max(0, Math.min(1, (R[i] * k - ART_SHOW) / 60));
    const cited = new Path2D(), uncited = new Path2D(), rep = new Path2D(), inner = new Path2D();
    let nc = 0, nu = 0, nr = 0;
    for (const a of rec.arts) {
      const x = sx(a[2]), y = sy(a[3]), r = Math.max(a[4] * k, 0.6);
      if (x + r < 0 || x - r > W || y + r < 0 || y - r > H) continue;
      const ex = a[6];
      if (ex && ex.rep) { rep.moveTo(x + r, y); rep.arc(x, y, r, 0, 6.2832); nr++; continue; }
      const path = a[5] ? cited : uncited;
      path.moveTo(x + r, y); path.arc(x, y, r, 0, 6.2832);
      if (a[5]) nc++; else nu++;
      if (period && a[5]) {
        const s = share(null, { ys: ex && ex.ys, y0: ex && ex.y0, n: a[5] });
        if (s > 0) { const rr = r * Math.sqrt(s); inner.moveTo(x + rr, y); inner.arc(x, y, rr, 0, 6.2832); }
      }
    }
    if (nu) { ctx.fillStyle = rgba(hue, 0.28 * fadeIn); ctx.fill(uncited); }
    if (nc) { ctx.fillStyle = rgba(hue, (period ? 0.3 : 0.9) * fadeIn); ctx.fill(cited); }
    if (period) { ctx.fillStyle = rgba(hue, 0.9 * fadeIn); ctx.fill(inner); }
    if (nr) { ctx.lineWidth = 0.8; ctx.strokeStyle = rgba(hue, 0.5 * fadeIn); ctx.stroke(rep); }
  }

  function artPos(i, key) {
    const rec = actRec(i);
    if (!rec || !rec.arts) return null;
    return rec.arts.find((a) => a[0] === key) || null;
  }

  function curve(x0, y0, x1, y1) {
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2, dx = x1 - x0, dy = y1 - y0;
    ctx.moveTo(x0, y0);
    ctx.quadraticCurveTo(mx - dy * 0.22, my + dx * 0.22, x1, y1);
  }
  function drawEdges() {
    if (sel.i < 0) return;
    const i = sel.i;
    ctx.lineCap = "round";
    if (sel.art) {
      const a = artPos(i, sel.art);
      if (!a || !a[6] || !a[6].e) return;
      const x0 = sx(a[2]), y0 = sy(a[3]);
      a[6].e.forEach((e, j) => {
        ctx.beginPath(); curve(x0, y0, sx(e[2]), sy(e[3]));
        ctx.lineWidth = 0.6 + Math.log10(e[4] + 1) * 0.6;
        ctx.strokeStyle = rgba("fg", 0.42 - j * 0.025);
        ctx.stroke();
        ctx.beginPath(); ctx.arc(sx(e[2]), sy(e[3]), 2.5, 0, 6.2832); ctx.fillStyle = rgba("fg", 0.7); ctx.fill();
      });
      return;
    }
    if (K[i] !== "act" || (R[i] * cam.k > ART_SHOW && actRec(i) && actRec(i).arts)) return;
    const x0 = sx(X[i]), y0 = sy(Y[i]);
    adj[i].slice(0, 16).forEach(([j, n], r) => {
      ctx.beginPath(); curve(x0, y0, sx(X[j]), sy(Y[j]));
      ctx.lineWidth = 0.7 + Math.log10(n + 1) * 0.7;
      ctx.strokeStyle = rgba("fg", Math.max(0.12, 0.5 - r * 0.025));
      ctx.stroke();
    });
  }

  function drawRings() {
    const ring = (i, art, a, w) => {
      if (i < 0) return;
      let x, y, r;
      if (art) { const p = artPos(i, art); if (!p) return; x = sx(p[2]); y = sy(p[3]); r = Math.max(p[4] * cam.k, 3) + 2.5; }
      else { x = sx(X[i]); y = sy(Y[i]); r = R[i] * cam.k + 1.5; }
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.lineWidth = w; ctx.strokeStyle = rgba("fg", a); ctx.stroke();
    };
    if (hover.i >= 0 && (hover.i !== sel.i || hover.art !== sel.art)) ring(hover.i, hover.art, 0.45, 1.5);
    ring(sel.i, sel.art, 0.95, 2);
  }

  // labels
  const measureCache = new Map();
  function measure(font, s) {
    const key = font + "|" + s;
    let w = measureCache.get(key);
    if (w === undefined) { ctx.font = font; w = ctx.measureText(s).width; if (measureCache.size > 20000) measureCache.clear(); measureCache.set(key, w); }
    return w;
  }
  function fit(font, s, maxW) {
    if (measure(font, s) <= maxW) return s;
    let lo = 0, hi = s.length;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (measure(font, s.slice(0, m) + "…") <= maxW) lo = m; else hi = m - 1; }
    return lo > 2 ? s.slice(0, lo).trimEnd() + "…" : "";
  }
  function wrap(font, s, maxW, maxLines) {
    const words = s.split(/\s+/), lines = [];
    let cur = "";
    for (const w of words) {
      const next = cur ? cur + " " + w : w;
      if (measure(font, next) <= maxW || !cur) cur = next;
      else { lines.push(cur); cur = w; if (lines.length === maxLines) break; }
    }
    if (lines.length < maxLines && cur) lines.push(cur);
    else if (cur && lines.length === maxLines) lines[maxLines - 1] = fit(font, lines[maxLines - 1] + " " + cur, maxW);
    return lines.map((l) => fit(font, l, maxW)).filter(Boolean);
  }
  const DISPLAY = '"Schibsted Grotesk", system-ui, sans-serif', BODY = '"IBM Plex Sans", system-ui, sans-serif', DATA = '"IBM Plex Mono", ui-monospace, monospace';

  function drawLabels(vis) {
    const boxes = [];
    const free = (b) => {
      for (const o of boxes) if (b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]) return false;
      boxes.push(b); return true;
    };
    const text = (s, x, y, font, color, align = "center") => {
      ctx.font = font; ctx.textAlign = align; ctx.textBaseline = "middle";
      ctx.lineJoin = "round"; ctx.lineWidth = 3.2; ctx.strokeStyle = colors.halo; ctx.strokeText(s, x, y);
      ctx.fillStyle = color; ctx.fillText(s, x, y);
    };
    const k = cam.k;
    const cand = [];
    for (const list of vis.byDepth) if (list) for (const i of list) {
      const r = R[i] * k;
      if (K[i] === "root") continue;
      if (K[i] === "act" || K[i] === "bucket") { if (r > 11) cand.push(i); }
      else if (r > 34) cand.push(i);
    }
    cand.sort((a, b) => R[b] - R[a]);
    let placed = 0;
    for (const i of cand) {
      if (placed > 420) break;
      const r = R[i] * k, x = sx(X[i]), y = sy(Y[i]), kind = K[i];
      const expanded = kind === "act" && r > ART_SHOW && actRec(i) && actRec(i).arts;
      if (kind === "act" || kind === "bucket") {
        if (expanded) {
          // act heading at the top of its circle
          const f = Math.max(12, Math.min(26, r / 16));
          const font = `700 ${f}px ${DISPLAY}`;
          // keep the heading readable below the search bar while the circle runs off the top
          const ty = Math.min(Math.max(y - r * 0.86, isPhone() ? 150 : 96), y + r * 0.5);
          const chord = 2 * Math.sqrt(Math.max(r * r - (ty - y) ** 2, 0)) * 0.9;
          const s = fit(font, label(i), chord);
          if (s && ty > -20 && ty < H + 20 && free([x - chord / 2, ty - f, x + chord / 2, ty + f])) {
            text(s, x, ty, font, colors.fg);
            const tt = title(i);
            if (tt && r > 220) {
              const f2 = Math.max(11, Math.min(15, r / 30));
              const font2 = `400 ${f2}px ${BODY}`;
              const ty2 = ty + f * 0.95;
              const chord2 = 2 * Math.sqrt(Math.max(r * r - (ty2 - y) ** 2, 0)) * 0.85;
              const s2 = fit(font2, tt, chord2);
              if (s2) text(s2, x, ty2, font2, colors.muted);
            }
            placed++;
          }
          continue;
        }
        const f = Math.max(10, Math.min(30, r / 2.4));
        const font = `600 ${f}px ${DISPLAY}`;
        const s = fit(font, label(i), r * 1.85);
        if (!s) continue;
        const w = measure(font, s);
        const tt = r > 70 ? title(i) : "";
        let lines = [], f2 = 0, font2 = "";
        if (tt) {
          f2 = Math.max(10.5, Math.min(14, r / 8));
          font2 = `400 ${f2}px ${BODY}`;
          lines = wrap(font2, tt, r * 1.45, r > 140 ? 4 : 2);
        }
        const hTot = f + lines.length * f2 * 1.25;
        const top = y - hTot / 2;
        if (!free([x - Math.max(w, r * 0.7) / 2, top, x + Math.max(w, r * 0.7) / 2, top + hTot])) continue;
        text(s, x, top + f / 2, font, colors.fg);
        lines.forEach((l, j) => text(l, x, top + f + f2 * 1.25 * (j + 0.5), font2, colors.muted));
        placed++;
        continue;
      }
      // areas: label inside the top of the circle
      const f = Math.max(11, Math.min(kind === "domain" ? 24 : 19, r / 13));
      const font = `${kind === "domain" ? 700 : 600} ${f}px ${DISPLAY}`;
      const ty = y - r + f * 1.35;
      const chord = 2 * Math.sqrt(Math.max(r * r - (ty - y) ** 2, 0)) * 0.86;
      const o = core.nodes[i];
      let s = label(i);
      if (o.sr && kind === "area") s = o.sr + "  " + s;
      s = fit(font, s, chord);
      if (!s || ty < -f || ty > H + f) continue;
      const w = measure(font, s);
      if (!free([x - w / 2 - 4, ty - f * 0.7, x + w / 2 + 4, ty + f * 0.7])) continue;
      text(s, x, ty, font, kind === "domain" ? colors.fg : rgba(HUE[i] === "n" ? "fg" : HUE[i], 1));
      placed++;
    }
    for (const i of vis.expanded) articleLabels(i, free, text);
  }

  function articleLabels(i, free, text) {
    const rec = actRec(i), k = cam.k;
    const cell = rec.p * k;
    const r = R[i] * k, cx = sx(X[i]), cy = sy(Y[i]);
    if (rec.heads && cell * 0.55 >= 8.5) {
      const f = Math.min(cell * 0.5, 15);
      const font = `600 ${f}px ${BODY}`;
      for (const [nm, h, hx, hy] of rec.heads) {
        const x = sx(hx), y = sy(hy);
        if (y < -f || y > H + f) continue;
        const s0 = [(nm && (nm[lang] || nm.de)) || "", (h && (h[lang] || h.de || h.fr || h.it)) || ""].join(" ").trim();
        if (!s0) continue;
        const half = Math.sqrt(Math.max(r * r * 0.81 - (y - cy) ** 2, 0));
        const maxW = cx + half - x;
        const s = fit(font, s0, maxW);
        if (s) { ctx.font = font; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillStyle = colors.muted; ctx.fillText(s, x, y); }
      }
    }
    if (cell < 22) return;
    const f = Math.min(cell * 0.27, 13);
    const font = `500 ${f}px ${DATA}`;
    for (const a of rec.arts) {
      const x = sx(a[2]), y = sy(a[3]);
      if (x < -cell || x > W + cell || y < -cell || y > H + cell) continue;
      const full = `${t.art} ${a[1]}`;
      const s = cell > 96 && measure(font, full) < cell * 0.9 ? full : (measure(font, a[1]) < cell * 0.92 ? a[1] : "");
      if (s) text(s, x, y, font, colors.fg);
    }
  }

  // ---------- hit testing ----------
  function hit(px, py) {
    if (!core) return { i: -1, art: null };
    const x = wx(px), y = wy(py), k = cam.k;
    let i = 0, best = -1;
    for (;;) {
      let next = -1;
      if (K[i] === "act") break;
      if (R[i] * k <= 2.5) break;
      for (const c of kids[i]) {
        const dx = x - X[c], dy = y - Y[c];
        if (dx * dx + dy * dy <= R[c] * R[c] && R[c] * k > 1.2) { next = c; break; }
      }
      if (next < 0) break;
      i = next; best = i;
    }
    if (best >= 0 && K[best] === "act" && R[best] * k > ART_SHOW) {
      const rec = actRec(best);
      if (rec && rec.arts) {
        const lim = (rec.p / 2) ** 2;
        let bd = Infinity, ba = null;
        for (const a of rec.arts) {
          const d = (x - a[2]) ** 2 + (y - a[3]) ** 2;
          if (d < bd) { bd = d; ba = a; }
        }
        if (ba && bd <= Math.max(lim, (ba[4]) ** 2)) return { i: best, art: ba[0] };
      }
    }
    return { i: best, art: null };
  }

  // ---------- selection & panel ----------
  function select(i, art = null, animate = true) {
    if (i < 0) { sel = { i: -1, art: null }; $("panel").hidden = true; $("tools").classList.remove("raised"); writeHash(); crumbs(); requestDraw(); return; }
    sel = { i, art };
    $("panel").hidden = false;
    $("tools").classList.toggle("raised", isPhone());
    if (PK[i] >= 0) ensurePack(PK[i]);
    if (art) {
      const go = () => {
        const a = artPos(i, art);
        const base = targetFor(i);
        if (a) {
          const rec = actRec(i);
          const v = viewRect();
          const k = Math.max(base.k, 64 / rec.p);
          flyTo({ x: a[2] - ((v.x0 + v.x1) / 2 - W / 2) / k, y: a[3] - ((v.y0 + v.y1) / 2 - H / 2) / k, k }, animate);
        } else flyTo(base, animate);
        refreshPanel();
      };
      if (actRec(i)) go(); else { refreshPanel(); const pr = ensurePack(PK[i]); if (pr) pr.then(go); }
    } else {
      flyTo(targetFor(i), animate);
      refreshPanel();
    }
    writeHash(); crumbs(); requestDraw();
  }

  function crumbs() {
    const el = $("crumbs");
    el.innerHTML = "";
    let i = sel.i;
    if (i < 0) return;
    const path = [];
    while (i >= 0) { path.unshift(i); i = P[i]; }
    path.forEach((j, n) => {
      if (n) el.append(Object.assign(document.createElement("span"), { textContent: "›" }));
      const b = document.createElement("button");
      const o = core.nodes[j];
      b.textContent = o.k === "area" || o.k === "group" ? o.sr : label(j);
      b.title = label(j);
      b.onclick = () => (j === 0 ? goHome() : select(j));
      el.append(b);
    });
    if (sel.art) {
      el.append(Object.assign(document.createElement("span"), { textContent: "›" }));
      const a = artPos(sel.i, sel.art);
      const b = document.createElement("button");
      b.textContent = `${t.art} ${a ? a[1] : ""}`;
      el.append(b);
    }
  }

  function goHome() { select(-1); fitHome(); }

  function spark(o, y0, ys, hue) {
    if (!ys || !ys.length) return "";
    const max = Math.max(...ys), n = ys.length, w = 360, h = 64, pad = 14;
    const bw = (w) / Math.max(n, 1);
    let bars = "";
    ys.forEach((v, j) => {
      if (!v) return;
      const bh = (h - pad - 4) * v / max;
      const inP = !period || (y0 + j >= period[0] && y0 + j <= period[1]);
      bars += `<rect x="${(j * bw).toFixed(2)}" y="${(h - pad - bh).toFixed(2)}" width="${Math.max(bw - 0.6, 0.6).toFixed(2)}" height="${bh.toFixed(2)}" fill="var(--d${hue})" fill-opacity="${inP ? 0.85 : 0.25}"/>`;
    });
    const last = y0 + n - 1;
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${esc(t.perYear)}">
      <line x1="0" x2="${w}" y1="${h - pad}" y2="${h - pad}" stroke="var(--line)" stroke-width="1"/>${bars}
      <text x="0" y="${h - 2}" font-size="10" fill="var(--muted)" font-family="IBM Plex Mono, monospace">${y0}</text>
      <text x="${w}" y="${h - 2}" font-size="10" fill="var(--muted)" text-anchor="end" font-family="IBM Plex Mono, monospace">${last} · max ${num(max)}</text></svg>`;
  }
  const decUrl = (did) => "https://mcp.opencaselaw.ch/entscheid/" + encodeURIComponent(did);

  function decList(i, list) {
    const items = list.map((did) => {
      const d = decInfo(i, did);
      if (!d) return "";
      const [lab, date, cb] = d;
      return `<li><a class="k link" href="${decUrl(did)}" target="_blank" rel="noopener" title="${esc(t.openDec)}">${esc(lab)}</a><span class="v">${esc(t.citedBy(num(cb)))}</span><span class="d">${date ? esc(date) : ""}</span></li>`;
    }).join("");
    return `<ul class="list">${items}</ul>`;
  }

  function countBlock(n, what, o, rec) {
    let s = `<section><div class="big"><b>${num(n)}</b><span>${esc(what)}</span></div>`;
    if (period && (o || rec)) s += `<p class="note">${esc(t.inPeriod(period[0], period[1]))}: <span class="mono">${num(Math.round(share(o, rec) * n))}</span></p>`;
    if (o && o.f != null && n) s += `<p class="note">${esc(t.federalShare)}: <span class="mono">${num(o.f)}</span> (${Math.round(100 * o.f / n)} %)</p>`;
    return s + "</section>";
  }

  function refreshPanel() {
    if (sel.i < 0 || $("panel").hidden) return;
    const i = sel.i, o = core.nodes[i], hue = HUE[i];
    const head = $("phead"), body = $("pbody");
    let eyebrow = "", h2 = "", sub = "", html = "";
    const tt = title(i), tl = titleLang(i);
    const rec = actRec(i);
    if (sel.art) {
      const a = artPos(i, sel.art);
      const actName = label(i);
      eyebrow = `${o.sr ? (t.sr + " " + o.sr) : actName}`;
      if (!a) { head.innerHTML = `<p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(t.loading)}</h2>`; body.innerHTML = ""; return; }
      const ex = a[6] || {};
      h2 = `${t.art} ${a[1]} ${actName}`;
      const own = ex.h ? (ex.h[lang] || ex.h.de || ex.h.fr || ex.h.it) : "";
      // structure path
      const levels = rec.levels || [];
      const chain = [];
      let li = ex.l;
      while (li !== undefined && li >= 0 && levels[li]) { chain.unshift(levels[li]); li = levels[li][1]; }
      const path = chain.map((lv) => [lv[2][lang] || lv[2].de || "", lv[3][lang] || lv[3].de || lv[3].fr || ""].join(" ").trim()).filter(Boolean);
      sub = own;
      html += countBlock(a[5], t.citeArt, null, { ys: ex.ys, y0: ex.y0, n: a[5] });
      if (ex.rep) html += `<p class="note"><span class="pill">${esc(t.repealed)}</span></p>`;
      if (path.length) html += `<section><h3>${esc(t.path)}</h3><ul class="list">${path.map((p) => `<li><span class="k">${esc(p)}</span></li>`).join("")}</ul></section>`;
      if (ex.ys) html += `<section><h3>${esc(t.perYear)}</h3>${spark(o, ex.y0, ex.ys, hue)}</section>`;
      if (ex.top && ex.top.length) html += `<section><h3>${esc(t.topDecArt)}</h3>${decList(i, ex.top)}</section>`;
      if (ex.e && ex.e.length) {
        html += `<section><h3>${esc(t.coArts)}</h3><ul class="list">${ex.e.map((e) => {
          const j = idIndex.get(e[0]);
          const lab = j !== undefined ? label(j) : e[0];
          const an = e[1].replace(/^.*art_/, "").replace(/_/g, "");
          return `<li><button class="k link" data-sel="${j}" data-art="${esc(e[1])}">${esc(t.art)} ${esc(an)} ${esc(lab)}</button><span class="v">${esc(t.together(num(e[4]), e[5]))}</span></li>`;
        }).join("")}</ul><p class="note">${esc(t.coNote)}</p></section>`;
      }
      if (o.e) {
        const anchor = /^(art_|disp_)/.test(sel.art) && !o.reg ? `/${lang === "en" ? "en" : lang}#${sel.art.replace(/\//g, "_")}` : "";
        html += `<section><a class="link" href="${esc(o.e + anchor)}" target="_blank" rel="noopener">${esc(t.official)} ↗</a></section>`;
      }
    } else if (o.k === "act") {
      eyebrow = o.c ? `${t.cantonalAct} · ${CANTON[o.c] ? CANTON[o.c][LANGS.indexOf(lang)] : o.c}` : `${t.sr} ${o.sr}${o.reg ? (o.reg === "a" ? " · " + t.edition : " · " + t.earlier) : ""}`;
      h2 = label(i);
      sub = tt + (tl ? ` [${tl.toUpperCase()}]` : "");
      html += countBlock(o.n, t.citeAct, o, null);
      if (o.c && !tt) html += `<p class="note">${esc(t.cantonalNoTitle)}</p>`;
      if (o.from || o.to) html += `<dl class="facts"><dt>${esc(t.inForce)}</dt><dd class="mono">${esc(o.from || "")} – ${esc(o.to || "")}</dd></dl>`;
      if (o.reg && o.reg !== "a") {
        const j = idIndex.get("SR " + o.sr);
        if (j !== undefined) html += `<p class="note">${esc(t.successor)}: <button class="link" data-sel="${j}">${esc(label(j))}</button></p>`;
      }
      if (o.ys) html += `<section><h3>${esc(t.perYear)}</h3>${spark(o, o.y0, o.ys, hue)}</section>`;
      if (rec && rec.arts) {
        const top = rec.arts.filter((a) => a[5]).sort((a, b) => b[5] - a[5]).slice(0, 10);
        const max = top.length ? top[0][5] : 1;
        html += `<section><h3>${esc(t.topArts)}</h3><p class="note">${esc(t.articlesIn(num(rec.arts.length)))}</p><ul class="list">${top.map((a) => {
          const h = a[6] && a[6].h ? (a[6].h[lang] || a[6].h.de || "") : "";
          return `<li style="--hue: var(--d${hue})"><button class="k link" data-sel="${i}" data-art="${esc(a[0])}">${esc(t.art)} ${esc(a[1])}${h ? " · " + esc(h) : ""}</button><span class="v">${num(a[5])}</span><span class="bar"><i style="width:${(100 * a[5] / max).toFixed(1)}%"></i></span></li>`;
        }).join("")}</ul></section>`;
      } else if (PK[i] >= 0 && !rec) html += `<p class="note">${esc(t.loading)}</p>`;
      else if (!o.c) html += `<p class="note">${esc(t.noArticles)}</p>`;
      if (adj[i].length) {
        html += `<section><h3>${esc(t.coActs)}</h3><ul class="list">${adj[i].slice(0, 12).map(([j, n, l]) =>
          `<li><button class="k link" data-sel="${j}">${esc(label(j))}</button><span class="v">${esc(t.together(num(n), l.toFixed(1)))}</span><span class="d">${esc(title(j))}</span></li>`).join("")}</ul><p class="note">${esc(t.coNote)}</p></section>`;
      }
      if (rec && rec.top && rec.top.length) html += `<section><h3>${esc(t.topDec)}</h3>${decList(i, rec.top)}</section>`;
      if (o.nf) {
        html += `<section><h3>${esc(t.notFound)}</h3><p class="note">${esc(t.nfNote(num(o.nf), num(o.nfd)))}</p>`;
        if (rec && rec.nf && rec.nf.length) html += `<p class="note mono">${rec.nf.slice(0, 20).map(([a, n]) => `${esc(t.art)} ${esc(a)} (${num(n)})`).join(" · ")}</p>`;
        html += "</section>";
      }
      if (o.nt) html += `<p class="note">${esc(t.noText(num(o.nt)))}</p>`;
      if (o.e) html += `<section><a class="link" href="${esc(o.e + (o.c ? "" : "/" + (lang === "en" ? "en" : lang)))}" target="_blank" rel="noopener">${esc(o.c ? t.cantonal : t.official)} ↗</a></section>`;
    } else if (o.k === "bucket") {
      const p = core.nodes[P[i]];
      eyebrow = t.cantonalAct;
      h2 = t.bucket;
      html += countBlock(o.n, t.citeAct, null, null);
      html += `<p class="note">${esc(t.bucketNote(num(o.codes), CANTON[p.c] ? CANTON[p.c][LANGS.indexOf(lang)] : p.c))}</p>`;
    } else {
      eyebrow = o.k === "area" ? `${t.sr} ${o.sr}` : o.k === "group" ? `${t.sr} ${o.sr} · ${t.group}` : o.k === "canton" ? t.KT : o.k === "domain" ? t.root : "";
      h2 = label(i);
      sub = o.k === "domain" || o.k === "root" ? "" : (tl ? `[${tl.toUpperCase()}]` : "");
      html += countBlock(o.n, o.k === "root" ? t.decisionsInCorpus : t.citeArea, null, null);
      const ch = kids[i].slice().sort((a, b) => NC[b] - NC[a]).slice(0, 14);
      const max = ch.length ? Math.max(NC[ch[0]], 1) : 1;
      html += `<section><h3>${esc(t.children)}</h3><ul class="list">${ch.map((j) => {
        const oj = core.nodes[j];
        const name = oj.k === "act" ? `${label(j)}${title(j) ? " · " + title(j) : ""}` : (oj.sr ? oj.sr + " " : "") + label(j);
        return `<li style="--hue: var(--d${HUE[j]})"><button class="k link" data-sel="${j}">${esc(name)}</button><span class="v">${num(NC[j])}</span><span class="bar"><i style="width:${(100 * NC[j] / max).toFixed(1)}%"></i></span></li>`;
      }).join("")}</ul></section>`;
    }
    head.innerHTML = `<p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(h2)}</h2>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}`;
    body.innerHTML = html;
    body.scrollTop = 0;
    crumbs();
  }

  $("pbody").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sel]");
    if (!b) return;
    const j = +b.dataset.sel;
    if (Number.isFinite(j) && j >= 0) select(j, b.dataset.art || null);
  });
  $("close").onclick = () => { select(-1); requestDraw(); };

  // ---------- hash ----------
  function writeHash() {
    let h = "";
    if (sel.i >= 0) {
      h = ids[sel.i].replace(/ /g, "_").replace(/@/g, "~").replace(/\*/g, "x");
      if (sel.art) h += "--" + sel.art.replace(/\//g, "~");
    }
    try { history.replaceState(null, "", h ? "#" + h : location.pathname + location.search); } catch (e) { /* sandboxed */ }
  }
  function decodeHash() {
    const h = decodeURIComponent((location.hash || "").slice(1));
    if (!h) return null;
    const [node, art] = h.split("--");
    const id = node.replace(/_/g, " ").replace(/~/g, "@").replace(/ x$/, " *");
    const i = idIndex.get(id);
    return i === undefined ? null : { i, art: art ? art.replace(/~/g, "/") : null };
  }

  // ---------- search ----------
  const DIACRITICS = new RegExp("[" + String.fromCharCode(0x300) + "-" + String.fromCharCode(0x36f) + "]", "g");   // combining marks after NFD
  const norm = (s) => s.normalize("NFD").replace(DIACRITICS, "").replace(/[.\s\-_/]+/g, "").toUpperCase();
  const fold = (s) => s.normalize("NFD").replace(DIACRITICS, "").toLowerCase();
  let results = [], cursor = 0;
  // Topic index: headings of the acts' own structure ("Die Miete", "La vente"), loaded at the first search.
  let topics = null, topicsLang = null, topicsLoading = null;
  function ensureTopics() {
    if ((topics && topicsLang === lang) || topicsLoading) return;
    const l = lang;
    topicsLoading = getJSON(`data/topics.${l}.json`).then((d) => {
      topics = d.map(([i, art, text, n, parent]) => [i, art, text, n, fold(text).split(/[^a-z0-9]+/).filter(Boolean), parent]);
      topicsLang = l; topicsLoading = null;
      if ($("search").value.trim()) showResults();
    }).catch(() => { topicsLoading = null; });
  }
  function topicMatches(q) {
    if (!topics || topicsLang !== lang) return [];
    const words = fold(q).split(/[^a-z0-9]+/).filter((w) => w.length >= 3);
    if (!words.length) return [];
    const hasWord = (tp, w) => tp[4].some((tok) => tok.startsWith(w));
    const run = (ws) => {
      const out = [];
      for (const tp of topics) {
        let own = 0, ok = true;
        for (const w of ws) {
          if (hasWord(tp, w)) { own++; continue; }
          let p = tp[5], found = false;          // a word may sit in a parent heading
          while (p >= 0 && !found) { found = hasWord(topics[p], w); p = topics[p][5]; }
          if (!found) { ok = false; break; }
        }
        if (ok && own) out.push({ i: tp[0], art: tp[1], topic: tp[2], n: tp[3], score: 120 + own * 30 + Math.log10(tp[3] + 1) * 25 });
      }
      return out;
    };
    let out = run(words);
    if (!out.length) out = run(words.map((w) => (w.length > 5 ? w.slice(0, 4) : w)));   // "Mietrecht" -> "miet"
    out.sort((a, b) => b.score - a.score);
    return out.slice(0, 8);
  }
  function search(q) {
    q = q.trim();
    const out = [];
    if (!q) return out;
    // "Art. 41 OR", "art 8 CEDH", "OR 41", "41 OR"
    const m = q.match(/^(?:art(?:\.|icle|ikel|icolo)?\s*)?(\d+\s*[a-z]{0,9})\s+(?:al\.?\s*\d+\s*|abs\.?\s*\d+\s*|cpv\.?\s*\d+\s*)?([\p{L}][\p{L}\d.\s/-]*)$/iu)
      || q.match(/^([\p{L}][\p{L}\d.\/-]*)\s+(?:art\.?\s*)?(\d+\s*[a-z]{0,9})$/iu);
    if (m) {
      let artNum = m[1], code = m[2];
      if (/^\d/.test(m[2])) { artNum = m[2]; code = m[1]; }
      const j = core.alias[norm(code)];
      if (j !== undefined) out.push({ i: j, artNum: artNum.replace(/\s+/g, "").toLowerCase(), score: 1000 });
    }
    const nq = norm(q), lq = q.toLowerCase();
    const words = lq.split(/\s+/).filter((w) => w.length > 1);
    const ali = core.alias[nq];
    if (ali !== undefined) out.push({ i: ali, score: 900 });
    for (let i = 1; i < N; i++) {
      const o = core.nodes[i];
      if (o.k === "bucket") continue;
      let s = 0;
      if (o.sr && (o.sr === q || (q.length >= 2 && /^[\d.]+$/.test(q) && o.sr.startsWith(q)))) s = o.sr === q ? 800 : 300 - o.sr.length;
      if (o.a) for (const v of Object.values(o.a)) { const nv = norm(v); if (nv === nq) s = Math.max(s, 850); else if (nq.length >= 2 && nv.startsWith(nq)) s = Math.max(s, 400); }
      if (!s && words.length) {
        const tt = (title(i) || "").toLowerCase();
        if (tt && words.every((w) => tt.includes(w))) s = 200 - Math.min(tt.length / 4, 60);
        else if (o.k === "canton" && label(i).toLowerCase().startsWith(lq)) s = 600;
      }
      if (s) out.push({ i, score: s + Math.log10(NC[i] + 1) * 12 });
    }
    ensureTopics();
    if (!m) out.push(...topicMatches(q));   // "Art. 41 OR" is an article, not a topic
    out.sort((a, b) => b.score - a.score);
    const seen = new Set();
    return out.filter((r) => { const key = r.i + "|" + (r.artNum || r.art || ""); if (seen.has(key)) return false; seen.add(key); return true; }).slice(0, 12);
  }
  function showResults() {
    const box = $("results");
    const q = $("search").value;
    results = search(q);
    cursor = 0;
    if (!q.trim()) { box.hidden = true; return; }
    box.hidden = false;
    if (!results.length) { box.innerHTML = `<div class="empty">${esc(t.none)}</div>`; return; }
    box.innerHTML = results.map((r, n) => {
      const o = core.nodes[r.i];
      const head = r.topic || (r.artNum ? `${t.art} ${r.artNum} ${label(r.i)}` : (o.k === "area" ? `${o.sr} ${label(r.i)}` : label(r.i)));
      const subl = r.topic ? `${label(r.i)} · ${title(r.i)}`
        : o.k === "act" ? [o.sr ? `${t.sr} ${o.sr}` : (o.c || ""), title(r.i)].filter(Boolean).join(" · ") : (o.k === "area" || o.k === "group" ? t.area : "");
      return `<button role="option" aria-selected="${n === 0}" data-n="${n}"><span class="t">${esc(head)}</span><span class="s">${esc(subl)}</span><span class="n">${r.artNum ? "" : num(r.topic ? r.n : NC[r.i])}</span></button>`;
    }).join("");
  }
  function choose(n) {
    const r = results[n];
    if (!r) return;
    $("results").hidden = true;
    $("search").blur();
    if (r.art) { select(r.i, r.art); return; }
    if (r.artNum && PK[r.i] >= 0) {
      const go = () => {
        const rec = actRec(r.i);
        const a = rec && rec.arts && (rec.arts.find((x) => x[1] === r.artNum) || rec.arts.find((x) => x[1].split("–")[0] === r.artNum)
          || rec.arts.find((x) => x[0] === "art_" + r.artNum));
        select(r.i, a ? a[0] : null);
      };
      const pr = ensurePack(PK[r.i]);
      if (pr && pr.then) pr.then(go); else go();
    } else select(r.i);
  }
  $("search").addEventListener("input", showResults);
  $("search").addEventListener("keydown", (e) => {
    const opts = [...$("results").querySelectorAll("button")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!opts.length) return;
      cursor = (cursor + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
      opts.forEach((b, n) => b.setAttribute("aria-selected", n === cursor));
      opts[cursor].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") { e.preventDefault(); choose(cursor); }
    else if (e.key === "Escape") { $("results").hidden = true; $("search").blur(); }
  });
  $("results").addEventListener("click", (e) => { const b = e.target.closest("button[data-n]"); if (b) choose(+b.dataset.n); });

  // ---------- input ----------
  const pointers = new Map();
  let drag = null, pinch = null, lastTap = 0;
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    $("results").hidden = true;
    if (pointers.size === 1) drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y, moved: false };
    else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: cam.k, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, wx: wx((a.x + b.x) / 2), wy: wy((a.y + b.y) / 2) };
      drag = null;
    }
    anim = null;
  });
  canvas.addEventListener("pointermove", (e) => {
    if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      cam.k = Math.max(0.05, Math.min(pinch.k * d / pinch.d, 5e7));
      cam.x = pinch.wx - (mx - W / 2) / cam.k;
      cam.y = pinch.wy - (my - H / 2) / cam.k;
      requestDraw();
      return;
    }
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > 4) { drag.moved = true; canvas.classList.add("dragging"); $("tip").hidden = true; }
      if (drag.moved) { cam.x = drag.cx - dx / cam.k; cam.y = drag.cy - dy / cam.k; requestDraw(); }
      return;
    }
    if (e.pointerType === "mouse") hoverAt(e.clientX, e.clientY);
  });
  const end = (e) => {
    pointers.delete(e.pointerId);
    if (pinch && pointers.size < 2) { pinch = null; drag = null; return; }
    if (drag && !drag.moved && pointers.size === 0) {
      const now = performance.now();
      const h = hit(e.clientX, e.clientY);
      if (e.pointerType !== "mouse" && now - lastTap < 300) { zoomAt(e.clientX, e.clientY, 2); lastTap = 0; }
      else {
        lastTap = now;
        if (h.i >= 0) select(h.i, h.art);
        else if (sel.i >= 0) { const p = P[sel.i]; if (p > 0) select(p); else goHome(); }
      }
    }
    drag = null;
    canvas.classList.remove("dragging");
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("pointerleave", () => { if (hover.i >= 0) { hover = { i: -1, art: null }; $("tip").hidden = true; requestDraw(); } });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (!core) return;
    const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    zoomAt(e.clientX, e.clientY, Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0018)));
    $("tip").hidden = true;
  }, { passive: false });
  canvas.addEventListener("dblclick", (e) => { e.preventDefault(); zoomAt(e.clientX, e.clientY, 2.2); });

  function hoverAt(px, py) {
    const h = hit(px, py);
    const tip = $("tip");
    if (h.i !== hover.i || h.art !== hover.art) { hover = h; requestDraw(); }
    canvas.classList.toggle("pointing", h.i >= 0);
    if (h.i < 0 || K[h.i] === "root") { tip.hidden = true; return; }
    let head, line;
    if (h.art) {
      const a = artPos(h.i, h.art);
      if (!a) { tip.hidden = true; return; }
      const hh = a[6] && a[6].h ? (a[6].h[lang] || a[6].h.de || "") : "";
      head = `${t.art} ${a[1]} ${label(h.i)}${hh ? " · " + hh : ""}`;
      line = t.decN(num(a[5]));
    } else {
      const o = core.nodes[h.i];
      head = o.k === "area" ? `${o.sr} ${label(h.i)}` : label(h.i);
      if (o.k === "act" && title(h.i)) head += " · " + title(h.i);
      line = t.decN(num(NC[h.i]));
    }
    tip.innerHTML = `<b>${esc(head.length > 140 ? head.slice(0, 139) + "…" : head)}</b><span>${esc(line)}</span>`;
    tip.hidden = false;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(px + 14, W - tw - 8) + "px";
    tip.style.top = Math.min(py + 16, H - th - 8) + "px";
  }

  window.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key === "/") { e.preventDefault(); $("search").focus(); }
    else if (e.key === "Escape") { if (!$("method").hidden) closeMethod(); else if (sel.i >= 0) { const p = P[sel.i]; sel.art ? select(sel.i) : (p > 0 ? select(p) : goHome()); } }
    else if (e.key === "+" || e.key === "=") zoomAt(W / 2, H / 2, 1.5);
    else if (e.key === "-") zoomAt(W / 2, H / 2, 1 / 1.5);
  });
  window.addEventListener("resize", () => { resize(); });
  $("zin").onclick = () => zoomAt(W / 2, H / 2, 1.8);
  $("zout").onclick = () => zoomAt(W / 2, H / 2, 1 / 1.8);
  $("home").onclick = goHome;
  $("legendbtn").onclick = () => { const on = $("legend").classList.toggle("open"); $("legendbtn").setAttribute("aria-pressed", on); if (!isPhone()) $("legend").hidden = !on; };
  $("periodbtn").onclick = () => {
    const box = $("period"), on = box.hidden;
    box.hidden = !on;
    $("periodbtn").setAttribute("aria-pressed", on);
    if (on) setPeriod(); else { period = null; requestDraw(); refreshPanel(); }
  };
  for (const id of ["y0", "y1"]) $(id).addEventListener("input", setPeriod);
  function setPeriod() {
    let a = +$("y0").value, b = +$("y1").value;
    if (a > b) [a, b] = [b, a];
    $("o0").value = a; $("o1").value = b;
    period = [a, b];
    requestDraw(); refreshPanel();
  }
  const mq = matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", () => { readColors(); requestDraw(); });
  new MutationObserver(() => { readColors(); requestDraw(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (document.fonts) document.fonts.ready.then(() => { measureCache.clear(); requestDraw(); });

  // ---------- language & legend ----------
  $("lang").addEventListener("change", async (e) => {
    lang = e.target.value; t = T[lang]; fmt = new Intl.NumberFormat(lang + "-CH");
    try { localStorage.setItem("slm-lang", lang); } catch (err) { /* storage unavailable */ }
    titles = await getJSON(`data/titles.${lang}.json`);
    topics = null;
    measureCache.clear();
    applyLang(); buildLegend(); refreshPanel(); crumbs(); requestDraw();
    if ($("search").value) showResults();
  });
  function applyLang() {
    document.documentElement.lang = lang;
    $("lang").value = lang;
    $("brandname").textContent = t.name;
    $("search").placeholder = t.search;
    $("home").textContent = t.home; $("periodbtn").textContent = t.period; $("legendbtn").textContent = t.legend; $("methodbtn").textContent = t.method;
    $("l-from").textContent = t.from; $("l-to").textContent = t.to; $("periodnote").textContent = t.periodNote;
  }
  function buildLegend() {
    const el = $("legend");
    const items = [];
    const ch = idIndex.get("CH");
    for (const j of kids[ch]) items.push([j, HUE[j], label(j)]);
    const kt = idIndex.get("KT");
    items.push([kt, "k", t.KT]);
    el.innerHTML = items.map(([j, h, l]) => `<button data-sel="${j}" title="${esc(l)}"><i style="background: var(--d${h})"></i><span>${esc(core.nodes[j].sr ? core.nodes[j].sr + " " : "")}${esc(l)}</span></button>`).join("")
      + `<p class="note">${esc({ de: "Völkerrecht (SR 0.1–0.9) in der Farbe des entsprechenden Landesrechts. Gestrichelt: früherer Erlass oder frühere Fassung.", fr: "Droit international (RS 0.1–0.9) dans la couleur du domaine interne correspondant. Tirets : acte ou version antérieurs.", it: "Diritto internazionale (RS 0.1–0.9) nel colore del settore interno corrispondente. Tratteggio: atto o versione precedenti.", en: "International law (SR 0.1–0.9) takes the colour of the matching domestic area. Dashed rim: earlier act or edition." }[lang])}</p>`;
    el.onclick = (e) => { const b = e.target.closest("[data-sel]"); if (b) select(+b.dataset.sel); };
    if (!isPhone()) { el.hidden = false; el.classList.add("open"); $("legendbtn").setAttribute("aria-pressed", true); }
  }

  // ---------- method ----------
  function methodHTML() {
    const m = core.method;
    const L = { de: 0, fr: 1, it: 2, en: 3 }[lang];
    const tr = (de, fr, it, en) => [de, fr, it, en][L];
    const RES = {
      federal: tr("Bundeserlass", "Acte fédéral", "Atto federale", "Federal act"),
      cantonal_unmapped: tr("Kantonaler Erlass (Abkürzung ohne Bundeszuordnung, kantonaler Entscheid)", "Acte cantonal (abréviation sans correspondance fédérale, décision cantonale)", "Atto cantonale (abbreviazione senza corrispondenza federale, decisione cantonale)", "Cantonal act (abbreviation with no federal match, cantonal decision)"),
      cantonal_homonym: tr("Kantonaler Erlass gleicher Abkürzung wie ein Bundeserlass (z. B. StG, LPA)", "Acte cantonal de même abréviation qu’un acte fédéral (p. ex. LPA)", "Atto cantonale con la stessa abbreviazione di un atto federale (p. es. LT)", "Cantonal act sharing a federal abbreviation (e.g. StG, LPA)"),
      cantonal_pre2011_procedure: tr("Kantonale Prozessordnung vor 2011 (ZPO/StPO in kantonalem Entscheid)", "Code de procédure cantonal avant 2011", "Codice di procedura cantonale prima del 2011", "Cantonal procedure code before 2011"),
      excluded_unresolved: tr("Ausgeschlossen: Abkürzung nicht identifiziert", "Exclu : abréviation non identifiée", "Escluso: abbreviazione non identificata", "Excluded: abbreviation not identified"),
      excluded_not_a_cantonal_act: tr("Ausgeschlossen: kein kantonaler Erlass (fehlender Bundesalias, Tippfehler, Gattungswort)", "Exclu : pas un acte cantonal", "Escluso: non è un atto cantonale", "Excluded: not a cantonal act (missing federal alias, typo, generic word)"),
      excluded_unverified_homonym: tr("Ausgeschlossen: Bedeutung nicht gesichert (z. B. aZG/AZG)", "Exclu : signification non vérifiée", "Escluso: significato non verificato", "Excluded: meaning not verified (e.g. aZG read as AZG)"),
      excluded_ambiguous_in_federal_court: tr("Ausgeschlossen: Homonym in Bundesentscheid mehrdeutig", "Exclu : homonyme ambigu dans une décision fédérale", "Escluso: omonimo ambiguo in decisione federale", "Excluded: homonym ambiguous in a federal decision"),
      excluded_pre2011_procedure_in_federal_court: tr("Ausgeschlossen: ZPO/StPO vor 2011 in Bundesentscheid", "Exclu : CPC/CPP avant 2011 dans une décision fédérale", "Escluso: CPC/CPP prima del 2011 in decisione federale", "Excluded: ZPO/StPO before 2011 in a federal decision"),
      excluded_shared_abbreviation: tr("Ausgeschlossen: Abkürzung zweier Bundeserlasse", "Exclu : abréviation de deux actes fédéraux", "Escluso: abbreviazione di due atti federali", "Excluded: abbreviation of two federal acts"),
      no_decision_metadata: tr("Ausgeschlossen: Entscheid ohne Metadaten", "Exclu : décision sans métadonnées", "Escluso: decisione senza metadati", "Excluded: decision without metadata"),
    };
    const VAL = {
      valid: tr("Artikel im massgebenden Text gefunden", "Article trouvé dans le texte déterminant", "Articolo trovato nel testo determinante", "Article found in the applicable text"),
      cantonal_act_level: tr("Kantonaler Erlass (keine Artikelebene)", "Acte cantonal (sans niveau article)", "Atto cantonale (senza livello articolo)", "Cantonal act (no article layer)"),
      not_in_text: tr("Artikel nicht im Text (Behälter je Erlass)", "Article absent du texte (compté par acte)", "Articolo assente dal testo (contato per atto)", "Article not in the text (bucket per act)"),
      no_text: tr("Kein Fedlex-Text: Artikel nicht prüfbar", "Pas de texte Fedlex : article non vérifiable", "Nessun testo Fedlex: articolo non verificabile", "No Fedlex text: article not checkable"),
      cantonal_transitional_procedure: tr("Frühere kantonale Prozessordnung 2011–2013 (v. a. VD)", "Ancien code de procédure cantonal 2011–2013 (surtout VD)", "Vecchio codice di procedura cantonale 2011–2013", "Former cantonal procedure code 2011–2013 (mostly VD)"),
    };
    const pct = (a, b) => (100 * a / b).toFixed(2) + " %";
    const tot = m.total_references;
    const rows = m.resolution.map((r) => `<tr><td>${esc(RES[r.resolution] || r.resolution)}</td><td class="r">${num(r.refs)}</td><td class="r">${pct(r.refs, tot)}</td><td class="r">${num(r.decisions)}</td></tr>`).join("");
    const vtot = m.validation.reduce((s, r) => s + r.refs, 0);
    const vrows = m.validation.map((r) => `<tr><td>${esc(VAL[r.status] || r.status)}</td><td class="r">${num(r.refs)}</td><td class="r">${pct(r.refs, vtot)}</td><td class="r">${num(r.decisions)}</td></tr>`).join("");
    const c = m.citations, dup = Object.fromEntries(m.duplicates.map((d) => [d.rule, d.n]));
    const H = (s) => `<h3>${esc(s)}</h3>`;
    return `<button class="chip x" id="mclose">×</button>
      <h2 id="mtitle">${esc(t.method)}</h2>
      <p>${esc(tr("Jede Zahl auf dieser Karte ist aus offenen Daten berechnet, nicht geschätzt. Hier steht, wie, und was weggelassen wurde.", "Chaque chiffre de cette carte est calculé à partir de données ouvertes, non estimé. Voici comment, et ce qui a été écarté.", "Ogni numero di questa mappa è calcolato da dati aperti, non stimato. Ecco come, e che cosa è stato escluso.", "Every number on this map is computed from open data, not estimated. This is how, and what was left out."))}</p>
      ${H(tr("Quellen", "Sources", "Fonti", "Sources"))}
      <ul><li>${esc(tr("OpenCaseLaw (CC0): Entscheide, Zitierungen zwischen Entscheiden, Gesetzesverweise. Stand", "OpenCaseLaw (CC0) : décisions, citations entre décisions, renvois aux lois. État au", "OpenCaseLaw (CC0): decisioni, citazioni tra decisioni, rinvii alle leggi. Stato al", "OpenCaseLaw (CC0): decisions, citations between decisions, statute references. Snapshot"))} ${esc(m.snapshot)}.</li>
      <li>${esc(tr("Fedlex: Systematische Rechtssammlung, Titel, Abkürzungen, Inkrafttreten, konsolidierte Texte (DE/FR/IT).", "Fedlex : Recueil systématique, titres, abréviations, entrée en vigueur, textes consolidés.", "Fedlex: Raccolta sistematica, titoli, abbreviazioni, entrata in vigore, testi consolidati.", "Fedlex: Classified Compilation (SR), titles, abbreviations, entry into force, consolidated texts (DE/FR/IT)."))}</li></ul>
      ${H(tr("Was gemessen wird", "Ce qui est mesuré", "Che cosa si misura", "What is measured"))}
      <ul><li>${esc(tr("Grösse eines Erlasses oder Artikels = Zahl der Entscheide, die darauf verweisen. Ein Entscheid zählt einmal.", "Taille d’un acte ou d’un article = nombre de décisions qui y renvoient. Une décision compte une fois.", "Dimensione di un atto o articolo = numero di decisioni che vi rinviano. Una decisione conta una volta.", "Size of an act or article = number of decisions referring to it. A decision counts once."))}</li>
      <li>${esc(tr("«Meistzitierte Entscheide, die auf diesen Artikel verweisen»: verweisende Entscheide, geordnet nach der Zahl der Entscheide, die sie zitieren. Keine Aussage über Leitentscheide.", "«Décisions les plus citées qui renvoient à cet article» : décisions qui y renvoient, classées selon le nombre de décisions qui les citent. Ce n’est pas un jugement sur les arrêts de principe.", "«Decisioni più citate che rinviano a questo articolo»: decisioni che vi rinviano, ordinate per numero di decisioni che le citano. Non è un giudizio sulle sentenze di principio.", "“Most-cited decisions referring to this article”: referring decisions ranked by how many decisions cite them. No claim about leading cases."))}</li>
      <li>${esc(tr("Position = Platz in der SR. Artikel stehen in der Reihenfolge des amtlichen Textes.", "Position = place dans le RS. Les articles suivent l’ordre du texte officiel.", "Posizione = posto nella RS. Gli articoli seguono l’ordine del testo ufficiale.", "Position = place in the SR. Articles follow the order of the official text."))}</li></ul>
      ${H(tr("Zuordnung der Gesetzesverweise", "Attribution des renvois", "Attribuzione dei rinvii", "Resolving statute references"))}
      <p class="note">${esc(tr("Einheit: Zeile der Verweistabelle (Entscheid × Abkürzung × Artikel × Absatz).", "Unité : ligne de la table des renvois (décision × abréviation × article × alinéa).", "Unità: riga della tabella dei rinvii (decisione × abbreviazione × articolo × capoverso).", "Unit: row of the reference table (decision × abbreviation × article × paragraph)."))}</p>
      <div class="tw"><table><tr><th></th><th class="r">${esc(tr("Verweise", "Renvois", "Rinvii", "References"))}</th><th class="r">%</th><th class="r">${esc(t.decisions)}</th></tr>${rows}
      <tr><td><b>Total</b></td><td class="r"><b>${num(tot)}</b></td><td class="r"></td><td class="r"></td></tr></table></div>
      ${H(tr("Prüfung der Artikel", "Vérification des articles", "Verifica degli articoli", "Article validation"))}
      <p class="note">${esc(tr("Einheit: Paar Entscheid × Artikel. Ein Artikel erscheint nur, wenn er im massgebenden Fedlex-Text existiert: geltender Text; bei früheren Erlassen der letzte und der erste veröffentlichte Text.", "Unité : paire décision × article. Un article n’apparaît que s’il existe dans le texte Fedlex déterminant.", "Unità: coppia decisione × articolo. Un articolo compare solo se esiste nel testo Fedlex determinante.", "Unit: decision × article pair. An article appears only if it exists in the applicable Fedlex text: the current text; for earlier acts, their last and first published text."))} ${num(m.article_nodes)} ${esc(tr("Artikelpunkte.", "points d’article.", "punti articolo.", "article dots."))}</p>
      <div class="tw"><table><tr><th></th><th class="r">${esc(tr("Verweise", "Renvois", "Rinvii", "References"))}</th><th class="r">%</th><th class="r">${esc(t.decisions)}</th></tr>${vrows}</table></div>
      ${H(tr("Entscheide und Zitierungen", "Décisions et citations", "Decisioni e citazioni", "Decisions and citations"))}
      <div class="tw"><table>
      <tr><td>${esc(tr("Entscheide im Korpus (nach Zusammenführung)", "Décisions dans le corpus (après fusion)", "Decisioni nel corpus (dopo fusione)", "Decisions in the corpus (after merging)"))}</td><td class="r">${num(c.decisions_in_corpus)}</td></tr>
      <tr><td>${esc(tr("Doppelt erfasste Urteile zusammengeführt: BGE + BGer-Dossier", "Arrêts enregistrés deux fois fusionnés : ATF + dossier TF", "Sentenze registrate due volte unite: DTF + incarto TF", "Judgments held twice, merged: BGE + BGer docket"))}</td><td class="r">${num(dup.bge_bger_docket)}</td></tr>
      <tr><td>${esc(tr("… gleiche Bezeichnung, gleiches Datum, gleicher Kanton", "… même référence, même date, même canton", "… stesso riferimento, data e cantone", "… same label, date and canton"))}</td><td class="r">${num(dup.same_label_date_canton)}</td></tr>
      <tr><td>${esc(tr("Datum unmöglich (vor dem Jahr der eigenen Dossiernummer): als unbekannt behandelt", "Date impossible (avant l’année du propre numéro de dossier) : traitée comme inconnue", "Data impossibile (prima dell’anno del proprio numero d’incarto): trattata come ignota", "Impossible date (before the year of its own docket number): treated as unknown"))}</td><td class="r">${num(m.dates.implausible_date)}</td></tr>
      <tr><td>${esc(tr("Ohne Datum", "Sans date", "Senza data", "No date"))}</td><td class="r">${num(m.dates.no_date)}</td></tr>
      <tr><td>${esc(tr("Zitierungen (roh)", "Citations (brutes)", "Citazioni (grezze)", "Citations (raw)"))}</td><td class="r">${num(c.raw_edges)}</td></tr>
      <tr><td>${esc(tr("… entfernt: Konfidenz < 0,5 (vom Resolver erkannte Konflikte)", "… retirées : confiance < 0,5", "… rimosse: confidenza < 0,5", "… removed: score < 0.5 (resolver-detected conflicts)"))}</td><td class="r">${num(c.dropped_score_below_0_5)}</td></tr>
      <tr><td>${esc(tr("… entfernt: doppelte Paare", "… retirées : paires en double", "… rimosse: coppie doppie", "… removed: duplicate pairs"))}</td><td class="r">${num(c.duplicate_pairs_removed)}</td></tr>
      <tr><td>${esc(tr("… entfernt: Selbstzitierung nach Zusammenführung", "… retirées : autocitation après fusion", "… rimosse: autocitazione dopo fusione", "… removed: self-citation after merging"))}</td><td class="r">${num(c.self_citations_after_merge)}</td></tr>
      <tr><td>${esc(tr("… entfernt: Ziel nicht im Korpus", "… retirées : cible hors corpus", "… rimosse: destinazione fuori corpus", "… removed: target not in the corpus"))}</td><td class="r">${num(c.target_not_in_corpus)}</td></tr>
      <tr><td><b>${esc(tr("Zitierungen verwendet", "Citations utilisées", "Citazioni usate", "Citations used"))}</b></td><td class="r"><b>${num(c.edges)}</b></td></tr>
      <tr><td>${esc(tr("… davon nur aus BGE-Fundstelle erschlossen", "… dont déduites uniquement d’un renvoi de page ATF", "… di cui dedotte solo da un rinvio di pagina DTF", "… of which inferred from a BGE pinpoint only"))}</td><td class="r">${num(c.edges_inferred_bge_pincite_only)}</td></tr>
      </table></div>
      ${H(tr("Entscheide über die Daten", "Choix sur les données", "Scelte sui dati", "Decisions about the data"))}
      <ul>
      <li>${esc(tr("Sprachvarianten fallen auf eine SR-Nummer zusammen (OR = CO, BGG = LTF, EMRK = CEDH).", "Les variantes linguistiques sont réunies sous un numéro RS (CO = OR, LTF = BGG).", "Le varianti linguistiche sono riunite sotto un numero RS (CO = OR, LTF = BGG).", "Language variants collapse onto one SR number (OR = CO, BGG = LTF, EMRK = CEDH)."))}</li>
      <li>${esc(tr(`Eine SR-Nummer kann nacheinander verschiedene Erlasse tragen (412 der 830 zitierten). Frühere Erlasse erhalten einen eigenen Kreis (gestrichelt), z. B. OG 1943 unter 173.110. Eine Abkürzung, die nur der frühere Erlass trug, meint diesen; eine gemeinsame Abkürzung (ELG, AsylG) den am Entscheiddatum geltenden. ${m.regimes} frühere Erlasse erhalten Verweise.`, `Un numéro RS peut porter successivement plusieurs actes (412 des 830 cités). Les actes antérieurs ont leur propre cercle (tirets). Une abréviation commune (LPC, LAsi) désigne l’acte en vigueur à la date de la décision. ${m.regimes} actes antérieurs reçoivent des renvois.`, `Un numero RS può designare successivamente atti diversi (412 dei 830 citati). Gli atti precedenti hanno un proprio cerchio (tratteggio). Un’abbreviazione comune designa l’atto in vigore alla data della decisione. ${m.regimes} atti precedenti ricevono rinvii.`, `One SR number can carry different acts over time (412 of the 830 cited). Earlier acts get their own circle (dashed), e.g. OG 1943 under 173.110. A code only the earlier act bore means it; a shared code (ELG, AsylG) means the act in force on the decision date. ${m.regimes} earlier acts receive references.`))}</li>
      <li>${esc(tr(`Kantonale Homonyme (${m.cantonal_homonyms.join(", ")}): im kantonalen Entscheid der Erlass des Kantons, im Bundesentscheid ausgeschlossen.`, `Homonymes cantonaux (${m.cantonal_homonyms.join(", ")}) : acte du canton dans une décision cantonale, exclus dans une décision fédérale.`, `Omonimi cantonali (${m.cantonal_homonyms.join(", ")}): atto del cantone in una decisione cantonale, esclusi in una decisione federale.`, `Cantonal homonyms (${m.cantonal_homonyms.join(", ")}): the canton's act in a cantonal decision, excluded in a federal one.`))}</li>
      <li>${esc(tr(`Nicht gesicherte Bedeutungen werden nie erraten, sondern ausgeschlossen: ${m.unverified_homonyms.join(", ")}.`, `Les significations non vérifiées ne sont jamais devinées mais exclues : ${m.unverified_homonyms.join(", ")}.`, `I significati non verificati non vengono mai indovinati ma esclusi: ${m.unverified_homonyms.join(", ")}.`, `Meanings not verified are never guessed, they are excluded: ${m.unverified_homonyms.join(", ")}.`))}</li>
      <li>${esc(tr(`Unbekannte Abkürzungen in kantonalen Entscheiden werden zum kantonalen Erlass «Kanton Abkürzung», ausser bei Abkürzungen, die nachweislich keinen kantonalen Erlass bezeichnen: ${m.not_cantonal.join(", ")}. Ebenso ${m.glued_codes} Abkürzungen mit angehängter Artikelnummer (BV8, ZGB8). Abkürzungen mit weniger als 5 Entscheiden sind je Kanton zusammengefasst.`, `Les abréviations inconnues dans les décisions cantonales deviennent l’acte cantonal «canton abréviation», sauf celles qui ne désignent manifestement pas un acte cantonal : ${m.not_cantonal.join(", ")}. De même ${m.glued_codes} abréviations suivies d’un numéro d’article (BV8, ZGB8). Celles de moins de 5 décisions sont regroupées par canton.`, `Le abbreviazioni sconosciute nelle decisioni cantonali diventano l’atto cantonale «cantone abbreviazione», salvo quelle che chiaramente non designano un atto cantonale: ${m.not_cantonal.join(", ")}. Così pure ${m.glued_codes} abbreviazioni seguite da un numero d’articolo (BV8, ZGB8). Quelle con meno di 5 decisioni sono raggruppate per cantone.`, `Unknown codes in cantonal decisions become the cantonal act “canton code”, except codes shown not to name a cantonal act: ${m.not_cantonal.join(", ")}. The same holds for ${m.glued_codes} codes with an article number glued on (BV8, ZGB8). Codes cited by fewer than 5 decisions are pooled per canton.`))}</li>
      <li>${esc(tr(`Korrigierte Zuordnungen: ${Object.entries(m.alias_overrides).map(([k, v]) => k + " → SR " + v).join(", ")}; ${m.aliases_added_from_fedlex} Kurztitel früherer Erlasse aus Fedlex ergänzt.`, `Attributions corrigées : ${Object.entries(m.alias_overrides).map(([k, v]) => k + " → RS " + v).join(", ")} ; ${m.aliases_added_from_fedlex} titres courts d’actes antérieurs ajoutés depuis Fedlex.`, `Attribuzioni corrette: ${Object.entries(m.alias_overrides).map(([k, v]) => k + " → RS " + v).join(", ")}; ${m.aliases_added_from_fedlex} titoli brevi di atti precedenti aggiunti da Fedlex.`, `Corrected mappings: ${Object.entries(m.alias_overrides).map(([k, v]) => k + " → SR " + v).join(", ")}; ${m.aliases_added_from_fedlex} short titles of earlier acts added from Fedlex.`))}</li>
      <li>${esc(tr("ZPO/CPC/StPO/CPP vor 2011: kantonale Prozessordnungen (kantonaler Entscheid) bzw. ausgeschlossen (Bundesentscheid).", "CPC/CPP avant 2011 : codes cantonaux (décision cantonale) ou exclus (décision fédérale).", "CPC/CPP prima del 2011: codici cantonali (decisione cantonale) o esclusi (decisione federale).", "ZPO/CPC/StPO/CPP before 2011: cantonal procedure codes (cantonal decision) or excluded (federal decision)."))}</li>
      <li>${esc(tr(`Gemeinsam zitiert: mindestens ${m.co_citation.min_decisions_acts} (Erlasse) bzw. ${m.co_citation.min_decisions_articles} (Artikel) gemeinsame Entscheide, Lift ≥ ${m.co_citation.min_lift}, je Knoten die ${m.co_citation.top_k} stärksten Verbindungen. Ohne diesen Filter wären BGG und ZPO mit allem verbunden.`, `Cités ensemble : au moins ${m.co_citation.min_decisions_acts} (actes) ou ${m.co_citation.min_decisions_articles} (articles) décisions communes, lift ≥ ${m.co_citation.min_lift}, les ${m.co_citation.top_k} liens les plus forts par nœud.`, `Citati insieme: almeno ${m.co_citation.min_decisions_acts} (atti) o ${m.co_citation.min_decisions_articles} (articoli) decisioni comuni, lift ≥ ${m.co_citation.min_lift}, i ${m.co_citation.top_k} legami più forti per nodo.`, `Cited together: at least ${m.co_citation.min_decisions_acts} (acts) or ${m.co_citation.min_decisions_articles} (articles) shared decisions, lift ≥ ${m.co_citation.min_lift}, each node keeps its ${m.co_citation.top_k} strongest links. Without this filter BGG and ZPO would connect to everything.`))}</li>
      <li>${esc(tr("Der Konfidenzwert der Zitierungen ist keine Wahrscheinlichkeit (er bevorzugt gleiches Gericht und neuere Entscheide); nur Werte unter 0,5 (Konflikte) werden entfernt.", "Le score de confiance des citations n’est pas une probabilité ; seuls les scores inférieurs à 0,5 (conflits) sont retirés.", "Il punteggio di confidenza non è una probabilità; solo i valori inferiori a 0,5 (conflitti) sono rimossi.", "The citation confidence score is not a probability (it favours same court and recency); only scores below 0.5 (conflicts) are removed."))}</li>
      </ul>
      ${H(tr("Grenzen", "Limites", "Limiti", "Limits"))}
      <ul>
      <li>${esc(tr("Die Verweise stammen aus automatischer Extraktion. Zahlen zeigen, was die Entscheide nennen, nicht wie sie das Recht anwenden.", "Les renvois proviennent d’une extraction automatique. Les chiffres montrent ce que les décisions citent, non comment elles appliquent le droit.", "I rinvii provengono da un’estrazione automatica. I numeri mostrano che cosa citano le decisioni, non come applicano il diritto.", "References come from automatic extraction. Numbers show what decisions cite, not how they apply the law."))}</li>
      <li>${esc(tr("Kantonale Erlasse tragen nur dort einen amtlichen Titel, wo der Titel die Abkürzung selbst enthält (vor allem GE und TI).", "Les actes cantonaux n’ont un titre officiel que lorsque ce titre contient l’abréviation (surtout GE et TI).", "Gli atti cantonali hanno un titolo ufficiale solo se questo contiene l’abbreviazione (soprattutto GE e TI).", "Cantonal acts carry an official title only where that title contains the abbreviation itself (mostly GE and TI)."))}</li>
      <li>${esc(tr("aZGB und aOR werden gegen die heutige Nummerierung geprüft; Fedlex veröffentlicht ältere Fassungen nicht als XML.", "aCC et aCO sont vérifiés selon la numérotation actuelle ; Fedlex ne publie pas les anciennes versions en XML.", "aCC e aCO sono verificati secondo la numerazione attuale; Fedlex non pubblica le versioni precedenti in XML.", "aZGB and aOR are checked against today’s numbering; Fedlex publishes no XML of older editions."))}</li>
      </ul>`;
  }
  function openMethod() {
    $("mbox").innerHTML = methodHTML();
    $("method").hidden = false;
    $("mclose").onclick = closeMethod;
    $("mclose").focus();
  }
  function closeMethod() { $("method").hidden = true; $("methodbtn").focus(); }
  $("methodbtn").onclick = openMethod;
  $("method").addEventListener("click", (e) => { if (e.target.id === "method") closeMethod(); });

  boot().catch((e) => { $("loading").textContent = "Error: " + e.message; console.error(e); });
})();
