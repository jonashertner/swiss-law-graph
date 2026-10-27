// Small helpers shared by the views.
import { lang, LOCALE } from "./i18n.js";

export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const nf = {};
export function num(n, d = 0) {
  const k = lang() + d;
  if (!nf[k]) nf[k] = new Intl.NumberFormat(LOCALE[lang()], { maximumFractionDigits: d, minimumFractionDigits: d });
  return nf[k].format(n || 0);
}
const df = {};
export function date(s) {
  if (!s) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return s;
  const k = lang();
  if (!df[k]) df[k] = new Intl.DateTimeFormat(LOCALE[k], { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  return df[k].format(new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])));
}
export const sw = (c) => `<i class="sw c${c}" aria-hidden="true"></i>`;
// links inside the page: #<lang>/<target>
export const href = (target) => `#${lang()}/${target || ""}`;
export const decUrl = (did) => "https://mcp.opencaselaw.ch/entscheid/" + encodeURIComponent(did);
export const ICON = {
  ext: `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M4.5 2.5h-2v7h7v-2M7 2.5h2.5V5M9.5 2.5 5.5 6.5"/></svg>`,
  x: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg>`,
  up: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/></svg>`,
  link: `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6.5 9.5l3-3M7 4.5l1.2-1.2a2.8 2.8 0 0 1 4 4L11 8.5M9 11.5l-1.2 1.2a2.8 2.8 0 0 1-4-4L5 7.5"/></svg>`,
  zoom: `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="2.5" y="2.5" width="11" height="11"/><path d="M2.5 8h11M8 2.5v11"/></svg>`,
};
export function store(k, v) {
  try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { /* storage blocked */ }
  return null;
}
