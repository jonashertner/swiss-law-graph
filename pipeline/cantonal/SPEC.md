# Cantonal act adapters — output contract

Each adapter `pipeline/cantonal/<ct>.py` (lower-case canton code) is a standalone script:
`python3 pipeline/cantonal/<ct>.py` writes `build/cantonal/<CT>.json` (a JSON list, one record per
act IN FORCE in the canton's official systematic collection: laws, decrees, ordinances/règlements/
arrêtés, intercantonal agreements the canton lists — everything the collection carries, not a sample).
Raw responses are cached under `build/cantonal/raw/<CT>/` so a rerun is resumable and offline.

Record:
{
  "ct": "VD",
  "sr": "173.36",            # the canton's systematic number exactly as the portal writes it
  "title": "...",            # official title, verbatim (no abbreviation appended by us)
  "abbr": "LPA-VD" | null,   # ONLY if the portal states it (own field, or "(...)" in the official
                             # title/header). Never derive or guess one.
  "url": "https://...",      # official, stable page of the act on the portal (what a reader opens)
  "in_force": true,
  "adopted": "2008-10-28" | null,   # adoption date ("du 28 octobre 2008", "vom 30. Januar 1997")
  "issuer": "Le Grand Conseil du Canton de Vaud",   # verbatim, text before the first basis keyword
  "ingress": "...",          # verbatim preamble from the issuer to the enacting word
                             # ("décrète", "arrête", "beschliesst", "verordnet", "decreta") inclusive,
                             # plain text, whitespace normalised, footnote markers kept as "[n]"
                             # where the source has them. "" if the act has no preamble.
  "notes": {"1": "RS 101"},  # footnotes referenced inside the ingress, verbatim plain text
  "links": [{"text": "...", "href": "..."}],   # hyperlinks inside the ingress, in order
  "lang": "fr",
  "src": "portal" | "lexfind"
}

Rules: public official sources only (the cantonal portal; LexFind only where the portal cannot be
reached). Never use the private HF dataset voilaj/swiss-legislation or jonashertner/opencaselaw-data.
Polite crawling: descriptive User-Agent "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)",
at most 3 concurrent requests per host, retry 5xx/timeouts with backoff.
