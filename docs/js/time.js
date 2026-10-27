// The time view (decision 31): one year for the map, the network and the matrix. An act appears in the
// year it was adopted (a treaty: when it came into force for Switzerland; an earlier federal act while it
// was in force; a code not in the collection from its first citation). Only today's law is known, with
// the earlier federal acts courts cite: the past shown is today's law by age, not the law of the past.
// Decisions count from their date; the steep rise after 2000 is mostly courts publishing more.
// The bar under the view is the history itself: today's acts in force per year, stacked by level, and
// decisions per year below; drag it, step it with the keys, or play it.
import { t, lang } from "./i18n.js";
import { M, KIND, getJSON, loadHistNames } from "./data.js";
import { $, esc, num } from "./util.js";

export const TIME = { on: false, year: 2026, y0: 1848, y1: 2026 };
let D = null, YS = null, ready = null, listeners = new Set(), play = null, bar = null, cv = null, series = null, cum = new Map();
const CLS = [0, 1, 2, 3, 4, 5, 6];
const motion = () => !matchMedia("(prefers-reduced-motion: reduce)").matches;

export function load() {
  if (!ready) ready = Promise.all([getJSON("data/time.json"), getJSON("data/years.json"), loadHistNames(lang())]).then(([d, ys]) => {
    D = d; YS = ys; TIME.y0 = d.y0; TIME.y1 = d.y1;
    if (!TIME.on) TIME.year = d.y1;
    build();
  });
  return ready;
}
// after a change of language: the repealed acts' names in it
export async function relabel(lg) { if (ready) await loadHistNames(lg); }
export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
const emit = () => { for (const fn of listeners) fn(TIME); };
// an edition of an act in force (aZGB, aOR, aStGB: "@a", decision 2) is the same act: shown, not counted again
const isLaw = (i) => M.K[i] === KIND.a || (M.K[i] === KIND.o && !M.S[i].endsWith("@a"));

// does act i exist in year y? undated acts only in the last year
export function exists(i, y = TIME.year) {
  if (!TIME.on || !D) return true;
  if (M.K[i] !== KIND.a && M.K[i] !== KIND.o && M.K[i] !== KIND.x) return true;
  const b = D.born[i];
  if (!b) return y >= TIME.y1;
  const d = D.died[i];                                   // acts older than the federal state appear in 1848
  return Math.max(b, TIME.y0) <= y && !(d && y >= d);
}
// decisions referring to node i up to year y (years.json: [first year, per year])
export function decTo(i, y = TIME.year) {
  if (!TIME.on || !YS) return M.D[i];
  let c = cum.get(i);
  if (c === undefined) {
    const s = YS[i];
    if (!s) c = null;
    else { const a = new Float64Array(s[1].length); let t2 = 0; s[1].forEach((v, k) => { t2 += v; a[k] = t2; }); c = { y0: s[0], a }; }
    cum.set(i, c);
  }
  if (!c) return y >= TIME.y1 ? M.D[i] : 0;
  const k = y - c.y0;
  return k < 0 ? 0 : c.a[Math.min(k, c.a.length - 1)];
}
export const bornOf = (i) => (D ? D.born[i] : 0);
export const pairYear = (j) => (D ? D.cy[j] || TIME.y1 : 0);         // the year a co-citation pair reaches 20 shared decisions
export const decYear = (y) => { if (!D) return 0; const k = y - D.dec.y0; return k < 0 ? 0 : (D.dec.fed[k] || 0) + (D.dec.kt[k] || 0); };

// the history: acts of today's collections (and earlier federal acts) per year and level
function build() {
  const Y = TIME.y1 - TIME.y0 + 1, add = CLS.map(() => new Float64Array(Y + 1));
  for (let i = 0; i < M.n; i++) {
    if (!isLaw(i)) continue;
    const c = M.hcls[i] >= 0 ? M.hcls[i] : 6, b = D.born[i], d = D.died[i];      // earlier acts in the colour of who made them
    const from = b ? Math.max(0, b - TIME.y0) : Y - 1, to = d ? Math.min(Y, d - TIME.y0) : Y;
    if (from >= to) continue;
    add[c][from]++; add[c][to]--;
  }
  series = CLS.map((c) => { const a = new Float64Array(Y); let s = 0; for (let k = 0; k < Y; k++) { s += add[c][k]; a[k] = s; } return a; });
}
export function actsAt(y = TIME.year) { if (!series) return 0; const k = y - TIME.y0; return series.reduce((s, a) => s + a[k], 0); }
// acts existing in year y below node f, as actsAt counts them (a parent always precedes its children in the atlas)
let under = null;
export function actsUnder(f, y = TIME.year) {
  if (!under || under.y !== y) {
    const c = new Int32Array(M.n);
    for (let i = M.n - 1; i > 0; i--) { if (isLaw(i) && exists(i, y)) c[i]++; c[M.P[i]] += c[i]; }
    under = { y, c };
  }
  return under.c[f];
}

// ---------- state
export async function enter(year, autoplay = false) {
  await load();
  const was = TIME.on;
  TIME.on = true;
  TIME.year = clamp(year ?? TIME.y0);
  showBar(); emit();
  if (autoplay && motion()) start(); else if (!was) drawBar();
}
export function exit() {
  stop();
  if (!TIME.on) return;
  TIME.on = false; TIME.year = TIME.y1;
  showBar(); emit();
}
const clamp = (y) => Math.max(TIME.y0, Math.min(TIME.y1, Math.round(y)));
export function setYear(y) {
  y = clamp(y);
  if (y === TIME.year && TIME.on) return;
  TIME.year = y;
  drawBar(); emit();
}
function start() {
  if (TIME.year >= TIME.y1) TIME.year = TIME.y0;
  const rate = 13;                                         // years per second
  play = { t0: performance.now(), from: TIME.year };
  const step = (now) => {
    if (!play) return;
    const y = clamp(play.from + ((now - play.t0) / 1000) * rate);
    if (y !== TIME.year) setYear(y);
    if (y >= TIME.y1) { stop(); return; }
    play.raf = requestAnimationFrame(step);
  };
  play.raf = requestAnimationFrame(step);
  playButton();
}
function stop() { const was = !!play; if (play) { cancelAnimationFrame(play.raf); play = null; } playButton(); if (was) emit(); }
export const playing = () => !!play;

// ---------- the bar
const ICON_PLAY = `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.8v10.4L13 8z" fill="currentColor"/></svg>`;
const ICON_PAUSE = `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h3v10H4zM9 3h3v10H9z" fill="currentColor"/></svg>`;
export const ICON_CLOCK = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 4.6V8l2.4 1.6"/></svg>`;
const ICON_X = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg>`;
function makeBar() {
  bar = document.createElement("div");
  bar.className = "timebar"; bar.id = "timebar"; bar.hidden = true;
  bar.innerHTML = `<div class="trow"><button class="tplay" id="tplay"></button><div class="tyear num" id="tyear"></div>` +
    `<div class="ttrack" id="ttrack" role="slider" tabindex="0"><canvas id="tcv"></canvas></div>` +
    `<div class="tstat" id="tstat"></div><button class="tclose" id="tclose">${ICON_X}</button></div><p class="tnote" id="tnote"></p>`;
  document.body.appendChild(bar);
  cv = bar.querySelector("#tcv");
  bar.querySelector("#tplay").onclick = () => (play ? stop() : start());
  bar.querySelector("#tclose").onclick = () => exit();
  const tr = bar.querySelector("#ttrack");
  const at = (e) => { const r = tr.getBoundingClientRect(); return TIME.y0 + ((e.clientX - r.left) / r.width) * (TIME.y1 - TIME.y0); };
  let down = false;
  tr.addEventListener("pointerdown", (e) => { down = true; tr.setPointerCapture(e.pointerId); stop(); setYear(at(e)); });
  tr.addEventListener("pointermove", (e) => { if (down) setYear(at(e)); });
  tr.addEventListener("pointerup", () => { down = false; });
  tr.addEventListener("pointercancel", () => { down = false; });
  tr.addEventListener("keydown", (e) => {
    const d = { ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1, PageDown: -10, PageUp: 10 }[e.key];
    if (d) { e.preventDefault(); stop(); setYear(TIME.year + d); }
    else if (e.key === "Home") { e.preventDefault(); stop(); setYear(TIME.y0); }
    else if (e.key === "End") { e.preventDefault(); stop(); setYear(TIME.y1); }
  });
  new ResizeObserver(() => drawBar()).observe(tr);
}
function playButton() {
  const b = bar && bar.querySelector("#tplay");
  if (!b) return;
  b.innerHTML = play ? ICON_PAUSE : ICON_PLAY;
  b.setAttribute("aria-label", t(play ? "timePause" : "timePlay")); b.title = t(play ? "timePause" : "timePlay");
}
// put the bar into the view shown, above its legend
export function mount(view) {
  if (!bar) makeBar();
  const host = view && $("v-" + view), foot = host && host.querySelector(".legend, .hfoot");
  if (host && foot) host.insertBefore(bar, foot); else if (host) host.appendChild(bar);
  showBar();
  for (const b of document.querySelectorAll(".tbtn")) { b.setAttribute("aria-pressed", TIME.on); }
}
function showBar() {
  if (!bar) return;
  const host = bar.parentElement, visible = TIME.on && host && host.classList.contains("view") && !host.hidden;
  bar.hidden = !visible;
  for (const b of document.querySelectorAll(".tbtn")) b.setAttribute("aria-pressed", TIME.on);
  if (visible) { texts(); drawBar(); }
}
export function texts() {
  if (!bar) return;
  playButton();
  bar.querySelector("#tclose").setAttribute("aria-label", t("timeClose")); bar.querySelector("#tclose").title = t("timeClose");
  bar.querySelector("#ttrack").setAttribute("aria-label", t("timeYear"));
  bar.querySelector("#tnote").textContent = t("timeNote", num(D ? D.noend || 0 : 0));
  for (const b of document.querySelectorAll(".tbtn")) { b.querySelector("span").textContent = t("timeBtn"); b.title = t("timeOpen"); }
}
function drawBar() {
  if (!bar || bar.hidden || !series) return;
  const y = TIME.year, tr = bar.querySelector("#ttrack");
  bar.querySelector("#tyear").textContent = y;
  tr.setAttribute("aria-valuemin", TIME.y0); tr.setAttribute("aria-valuemax", TIME.y1); tr.setAttribute("aria-valuenow", y);
  tr.setAttribute("aria-valuetext", `${y}: ${t("timeStat", num(actsAt(y)), num(decYear(y)), y)}`);
  bar.querySelector("#tstat").textContent = t("timeStat", num(actsAt(y)), num(decYear(y)), y);
  const r = tr.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1), W = Math.max(1, Math.floor(r.width)), H = Math.max(1, Math.floor(r.height));
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const g = cv.getContext("2d"), cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const Y = TIME.y1 - TIME.y0, X = (yy) => ((yy - TIME.y0) / Y) * W;
  const top = 2, hA = Math.round((H - 18) * 0.62), gap = 4, hB = H - 18 - hA - gap, base = top + hA;
  // today's acts in force per year, stacked by level (constitution at the bottom)
  const total = new Float64Array(Y + 1);
  for (const a of series) for (let k = 0; k <= Y; k++) total[k] += a[k];
  const max = Math.max(...total);
  const order = [0, 1, 2, 3, 4, 6, 5], lo = new Float64Array(Y + 1);
  for (const c of order) {
    const a = series[c];
    g.fillStyle = c === 5 ? "#d8d8d4" : v(`--c${c}`);
    g.beginPath();
    for (let k = 0; k <= Y; k++) g.lineTo(X(TIME.y0 + k), base - ((lo[k] + a[k]) / max) * hA);
    for (let k = Y; k >= 0; k--) g.lineTo(X(TIME.y0 + k), base - (lo[k] / max) * hA);
    g.closePath(); g.fill();
    for (let k = 0; k <= Y; k++) lo[k] += a[k];
  }
  // decisions per year
  const dmax = Math.max(1, ...D.dec.fed.map((f, k) => f + D.dec.kt[k])), bw = Math.max(1, W / Y - 0.5);
  g.fillStyle = v("--ink-3");
  for (let k = 0; k < D.dec.fed.length; k++) {
    const yy = D.dec.y0 + k, n = D.dec.fed[k] + D.dec.kt[k];
    if (yy < TIME.y0 || !n) continue;
    const h = Math.max(1, (n / dmax) * hB);
    g.fillRect(X(yy) - bw / 2, base + gap + hB - h, bw, h);
  }
  // after the year: veiled
  g.fillStyle = "rgba(255,255,255,.72)"; g.fillRect(X(y) + 1, 0, W - X(y), base + gap + hB + 1);
  // row names, year ticks, the cursor
  g.font = `600 10px ${v("--sans")}`; g.textBaseline = "top"; g.fillStyle = v("--ink-2"); g.textAlign = "left";
  g.fillText(t("timeActs"), 4, top + 2);
  g.fillText(t("timeDec"), 4, base + gap + 1);
  g.font = `500 10px ${v("--mono")}`; g.fillStyle = v("--ink-3"); g.textBaseline = "alphabetic";
  for (const yy of [1850, 1900, 1950, 2000]) {
    const x = X(yy), w2 = g.measureText(String(yy)).width / 2;
    g.textAlign = x - w2 < 0 ? "left" : "center"; g.fillText(String(yy), x - w2 < 0 ? 0 : x, H - 3); g.fillRect(x, base + gap + hB + 2, 1, 3);
  }
  g.textAlign = "right"; g.fillText(String(TIME.y1), W - 1, H - 3);
  const x = X(y);
  g.fillStyle = v("--accent"); g.fillRect(Math.round(x) - 1, 0, 2, base + gap + hB + 2);
  g.beginPath(); g.arc(x, 4, 4, 0, 2 * Math.PI); g.fill();
}

// the toggle in a view's bar
export function toggle() {
  const b = document.createElement("button");
  b.className = "tbtn"; b.type = "button"; b.setAttribute("aria-pressed", TIME.on);
  b.innerHTML = `${ICON_CLOCK}<span>${esc(t("timeBtn"))}</span>`;
  b.title = t("timeOpen");
  b.onclick = () => (TIME.on ? exit() : enter(TIME.y0, true));
  return b;
}
