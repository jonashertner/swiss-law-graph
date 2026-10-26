"""Step 1 — resolve every statute reference to a canonical act.

Inputs (all CC0 / official):
  data/statute_references.parquet   OpenCaseLaw, decision -> (law_code, article, paragraph)
  data/cite-index-*.tsv.gz          OpenCaseLaw, decision -> label, court, canton, date
  data/fedlex_acts.json             Fedlex, every act that ever carried a cited SR number
  ../opencaselaw/docs/data/law_codes.json, docs/api/law_aliases.json
                                    OpenCaseLaw verified alias -> SR tables

Output: build/refs.parquet  one row per (decision, act, section, article):
            decision_id (canonical), act_id, section, article, code, resolution
        build/meta.parquet  canonical decisions: decision_id, court, canton, dt, label
        build/decision_alias.parquet  duplicate decision id -> canonical id
        build/resolution_report.json  every reference accounted for

Rules (each one is disclosed on the page):
  * Language variants collapse onto one SR number (OR = CO = CO(it), BGG = LTF).
  * One SR number can carry different acts over time (412 of the 830 cited SR
    numbers have). Each earlier act gets its own node `SR <n>@<year of the act>`.
    A code that only an earlier act bore (OG, ANAG, BStP) means that act; a code
    shared by old and new act (ELG, AsylG, BV) means the act in force on the
    decision date; a code only the current act bears (BGG, AIG) means the
    current act whatever the date. Dates and abbreviations come from Fedlex.
  * 'a'-prefixed editions of acts still in force (aStGB, aZGB, aOR) get
    `SR <n>@a`; StGB references in decisions before 2007-01-01 also go to
    311.0@a (the general part was renumbered on that date).
  * ZPO/CPC/StPO/CPP in decisions before 2011-01-01 name cantonal procedure
    codes: cantonal decision -> `<canton> <code>`, federal decision -> excluded.
  * Cantonal homonyms: some codes name a federal act AND a cantonal act
    (LPA = federal Animal Welfare Act in French, but Geneva's administrative
    procedure act in Geneva decisions; StG = Stamp Duty Act, but every canton's
    tax act). In a cantonal decision such a code is read as the deciding
    canton's act; in a federal decision it is ambiguous and excluded. Codes we
    could not identify with confidence are excluded everywhere — never guessed.
  * Codes absent from the federal tables, cited by cantonal courts, become a
    cantonal act node keyed (canton, code). Cited only by federal courts and
    unknown: excluded as unresolved.
  * Abbreviations shared by two federal acts (32 in the table) are excluded.
  * A judgment held twice in the corpus (published BGE + the BGer docket
    version; a few cantonal duplicates with the same label and date) counts once.
  * Source dates that cannot be right (more than a year before the decision's
    own docket year, or after the snapshot) are treated as unknown: no year is
    shown for them, and act assignment uses 1 January of the docket year.
"""
import glob
import json
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OCL = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "jonashertner/opencaselaw")
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

norm = lambda s: re.sub(r"[.\s\-_/]+", "", s or "").upper()

# Alias corrections, each verified against the Fedlex article lists: the share of
# references whose article does not exist in the act drops from 69 % to 0.4 %.
ALIAS_OVERRIDES = {
    "OPC": "831.301",   # OPC-AVS/AI (ELV), not SR 281.41
}
# Identified cantonal acts sharing a federal abbreviation (read as the deciding canton's act).
# The 2026-10-26 additions were found by the share of references whose article does
# not exist in the federal act (StG in BE 82 %, SG 70 %, NW 78 %; PBG in SG 81 %; ...).
CANTONAL_HOMONYMS = {
    "LPA",   # GE/VD loi sur la procédure administrative  vs SR 455 (LPA = Animal Welfare Act, fr)
    "VRP",   # SG Gesetz über die Verwaltungsrechtspflege vs SR 901.021
    "LT",    # TI legge tributaria                        vs SR 641.10 (LT = Stamp Duty Act, fr/it)
    "LATC",  # VD loi sur l'aménagement du territoire et les constructions
    "KRG",   # GR Raumplanungsgesetz
    "LOC",   # TI legge organica comunale
    "LOG",   # TI legge sull'organizzazione giudiziaria
    "LI",    # VD loi sur les impôts directs cantonaux
    "LIC",   # VD loi sur les impôts communaux
    "LIP",   # GE loi sur l'instruction publique
    "LPCC",  # GE loi sur les prestations complémentaires cantonales
    "VSG",   # SG Volksschulgesetz
    "STG",   # cantonal Steuergesetz (BE, SG, NW, AR, OW, GR, ZH) vs SR 641.10 Stamp Duty Act
    "PBG",   # cantonal Planungs- und Baugesetz (SG, ZH, LU, NW) vs SR 745.1
    "LAF",   # TI/GE assegni/allocations familiales, VD améliorations foncières vs SR 836.1
    "LC",    # VD/BE/VS loi sur les communes vs SR 823.11
    "LPERS", # FR/VD loi sur le personnel vs SR 172.220.1
    "PG",    # BE Personalgesetz vs SR 783.0 Postgesetz
    "LAS",   # TI legge sull'assistenza sociale vs SR 851.1
}
# Identity not verified, or an upper-cased 'a'-prefix that collides with another
# act (aZG 1925 Customs Act read as AZG Arbeitszeitgesetz): excluded wherever ambiguous.
UNVERIFIED_HOMONYMS = {
    "LMC", "LPFC", "KAG", "VPRG", "LEP", "LCP", "LAP", "LPG", "STREG",
    "LTB", "LCMP", "VGV", "OPN", "LEH", "LOP", "VGS",
    "AZG", "AWG", "ASTG", "ASTV",
}
# Codes that cantonal courts use but that name no cantonal act: federal acts missing
# from the alias table, former editions, typos, generic words, private standards.
# Found because each appears in 6-24 cantons and often in federal decisions too.
# Without this list each would become a bogus cantonal act in every canton.
NOT_CANTONAL = {
    "GEBV",    # GebV SchKG (SR 281.35); ZH also has a GebV des Obergerichts -> ambiguous
    "BVV", "OPP",          # BVV 2 / OPP 2 (SR 831.441.1), number dropped by the extractor
    "VOSTRA", "SIS", "DNA",  # federal: VOSTRA-Verordnung, N-SIS-Verordnung, DNA-Profil-Gesetz
    "ALAI", "ALAVS",       # former editions aLAI, aLAVS
    "ALPC",                # typo for ALCP
    "TIT",                 # fragment of "tit. fin. CC"
    "CLAH",                # Hague conventions (international)
    "BG", "VO", "EG", "REG", "LF", "CF", "PP", "AI",  # generic words or unidentified
    "SIA", "CCT", "CGA",   # SIA norms, collective labour agreements, insurance terms
}
# Fedlex short titles of earlier acts NOT added as aliases: the corpus uses them for
# something else (each checked against the cited article numbers).
REJECTED_FEDLEX = {
    "LAG", "LAJ",   # TI / VD-VS-NE cantonal legal-aid acts, not the 1989 youth act
    "OASI",         # Italian AsylV (OAsi 1), not the 1989 military ordinance
    "TVA",          # French for VAT, not the 1990 waste ordinance
    "ALV",          # unemployment insurance, not the 1953 agriculture ordinance
    "OOA", "OGF", "OAJ", "BCO",  # cited articles and courts do not fit the Fedlex act
}
# Former codes not in the opencaselaw alias table: code -> (sr, last day it applied).
EXTRA_FORMER = {"AMWSTG": ("641.20", "2009-12-31"), "AMWSTV": ("641.201", "2009-12-31"),
                "ALTVA": ("641.20", "2009-12-31"), "ALIVA": ("641.20", "2009-12-31")}
# A shared abbreviation that only one act bore before a date: code -> (sr, first day it is ambiguous).
# KLV = Krankenpflege-Leistungsverordnung (since 1996); KlV = Klimaschutzverordnung (since 2025).
DATED_ALIASES = {"KLV": ("832.112.31", "2025-01-01")}
# Same act, earlier edition with different numbering: references dated before the
# cut-over go to `SR <n>@a`.
EDITION_CUTOVERS = {"311.0": "2007-01-01"}   # StGB general part revision in force 1.1.2007
SNAPSHOT = "2026-10-26"


def strip_year(a: str) -> str:
    return re.sub(r"\d{4}$", "", norm(a))


def regime_labels(hist: list[dict]) -> tuple[dict, dict]:
    """Label each act of one SR number: '' for the current act, '@<year>' for earlier ones."""
    cur = max((a for a in hist if not a.get("repealed")), default=hist[-1],
              key=lambda a: a.get("in_force") or "")
    regime = {a["eli"]: "" if a is cur else "@" + (a.get("date") or a.get("in_force") or "0000")[:4]
              for a in hist}
    if len(set(regime.values())) < len(regime):  # two earlier acts of the same year
        for a in hist:
            if a is not cur:
                regime[a["eli"]] = "@" + (a.get("date") or a.get("in_force") or "0000")[:7]
    return regime, cur


def act_intervals(code_sr: pd.DataFrame, acts: dict, alias_sets: dict, former: dict) -> pd.DataFrame:
    """For each (code, sr): which act a reference means, as date intervals."""
    rows = []
    for code, sr in code_sr.itertuples(index=False):
        hist = acts.get(sr) or []
        if len(hist) <= 1:
            rows.append((code, sr, "", "0001-01-01", "9999-12-31"))
            continue
        regime, cur = regime_labels(hist)

        def in_force_on(day: str) -> dict:
            started = [a for a in hist if (a.get("in_force") or "0000") <= day]
            return max(started, key=lambda a: a.get("in_force") or "") if started else hist[0]

        if code in former:
            a = in_force_on(former[code])
            rows.append((code, sr, regime[a["eli"]], "0001-01-01", "9999-12-31"))
            continue
        match = [a for a in hist if code in {strip_year(x) for x in a["abbr"].values()}
                 or (a is cur and code in alias_sets.get(sr, ()))]
        cand = match or hist
        if len(cand) == 1:
            rows.append((code, sr, regime[cand[0]["eli"]], "0001-01-01", "9999-12-31"))
            continue
        cand = sorted(cand, key=lambda a: a.get("in_force") or "")
        for i, a in enumerate(cand):
            start = "0001-01-01" if i == 0 else (a.get("in_force") or "0001-01-01")
            end = (cand[i + 1].get("in_force") or "9999-12-31") if i + 1 < len(cand) else "9999-12-31"
            rows.append((code, sr, regime[a["eli"]], start, end))
    return pd.DataFrame(rows, columns=["code", "sr", "regime", "start", "end"])


def main() -> None:
    lc = json.load(open(OCL / "docs/data/law_codes.json"))
    la = json.load(open(OCL / "docs/api/law_aliases.json"))
    acts = json.load(open(ROOT / "data/fedlex_acts.json"))["acts"]
    alias, kind = {}, {}
    for k, v in lc["alias_to_sr"].items():
        alias[norm(k)] = v
    former, editions, current = dict(), set(), set()
    for k, e in (la.get("aliases") or {}).items():
        if isinstance(e, dict) and e.get("sr_number"):
            nk = norm(k)
            alias.setdefault(nk, e["sr_number"])
            kind[nk] = e.get("kind")
            if e.get("kind") == "former" and e.get("as_of_hint"):
                former[nk] = e["as_of_hint"]
            elif e.get("kind") == "former_edition":
                editions.add(nk)
            elif e.get("kind") == "current":
                current.add(nk)
    for k, (sr, day) in EXTRA_FORMER.items():
        alias[k], former[k] = sr, day
    alias.update(ALIAS_OVERRIDES)
    # Fedlex's own short titles of earlier acts that carried a cited SR number (SGG
    # under 173.71, BEHG under 954.1): added when the code names exactly one SR number
    # and no act in force bears it. Current acts are covered by the opencaselaw tables.
    fed_abbr: dict[str, set] = {}
    current_abbr = set()
    for sr, hist in acts.items():
        for a in hist:
            keys = {k for x in a["abbr"].values() for k in (norm(x), strip_year(x))}
            if not a.get("repealed"):
                current_abbr |= keys
                continue
            for k in keys:
                fed_abbr.setdefault(k, set()).add(sr)
    added_from_fedlex = {k: next(iter(v)) for k, v in fed_abbr.items()
                         if len(v) == 1 and k not in alias and k not in current_abbr and len(k) >= 3
                         and k not in CANTONAL_HOMONYMS | UNVERIFIED_HOMONYMS | NOT_CANTONAL | REJECTED_FEDLEX}
    alias.update(added_from_fedlex)
    for k, (sr, _) in DATED_ALIASES.items():
        alias[k] = sr
    sections = {norm(k): e["section"] for k, e in la["aliases"].items() if e.get("kind") == "section"}
    alias_sets: dict[str, set] = {}
    for e in lc["federal"]:
        alias_sets.setdefault(e["sr_number"], set()).update(
            norm(x) for x in (e.get("aliases") or []) + [e.get("abbr_de"), e.get("abbr_fr"), e.get("abbr_it")] if x)
    for k in current:
        alias_sets.setdefault(alias[k], set()).add(k)

    rows = []
    for code, sr in alias.items():
        if isinstance(sr, list):
            rows.append((code, None, "shared_abbreviation"))
        else:
            rows.append((code, sr, "federal"))
    al = pd.DataFrame(rows, columns=["code", "sr", "kind"])

    c = duckdb.connect()
    c.register("al", al)
    c.register("hom", pd.DataFrame({"code": sorted(CANTONAL_HOMONYMS)}))
    c.register("unv", pd.DataFrame({"code": sorted(UNVERIFIED_HOMONYMS)}))
    # Extraction artifacts: a federal code with the article number glued on ("BV8", "ZGB8",
    # "LPGA1"). Unknown to the alias tables, they would become cantonal acts.
    codes = [x for (x,) in c.sql(f"select distinct upper(law_code) from '{ROOT}/data/statute_references.parquet'").fetchall()]
    glued = {k for k in codes if k not in alias and (m := re.fullmatch(r"([A-Z]+?)(\d+[A-Z]?)", k or ""))
             and len(m.group(1)) >= 2 and m.group(1) in alias}
    c.register("notk", pd.DataFrame({"code": sorted(NOT_CANTONAL | glued)}))
    c.register("dated", pd.DataFrame([(k, d) for k, (_, d) in DATED_ALIASES.items()], columns=["code", "until"]))
    c.register("sec", pd.DataFrame(list(sections.items()), columns=["code", "section"]))
    c.register("edi", pd.DataFrame({"code": sorted(editions)}))
    cite = glob.glob(str(ROOT / "data/cite-index-*.tsv.gz"))[0]
    c.sql(f"""create table ci as select column0 label, column1 court, column2 canton,
                  try_cast(column3 as date) dt, column5 decision_id
              from read_csv('{cite}', delim='\t', header=false, skip=1, quote='', all_varchar=true)""")

    # --- One judgment, one node. ---
    c.sql("""create table dup as
        select g.decision_id alias_id, min(b.decision_id) canonical_id, 'bge_bger_docket' rule
          from ci b join ci g on g.label = b.label and b.court = 'bge' and g.court = 'bger'
         group by 1
        union all
        select b.decision_id, min(a.decision_id), 'same_label_date_canton'
          from ci a join ci b on a.label = b.label and a.dt = b.dt and a.canton = b.canton
               and a.decision_id < b.decision_id
         where not (a.court in ('bge','bger') and b.court in ('bge','bger'))
         group by 1""")
    c.sql("""create table alias_map as select alias_id, canonical_id, rule from dup
             where alias_id not in (select canonical_id from dup)""")
    c.sql(f"""create table meta0 as
        select decision_id, min(court) court, min(canton) canton, min(dt) dt_src,
               arg_min(label, lpad(length(label)::varchar, 4, '0') || label) label
        from ci where decision_id not in (select alias_id from alias_map) group by 1""")
    # Docket year: the last run of exactly four digits between 1850 and 2029.
    year_of = lambda col: (f"try_cast(list_last(list_filter(regexp_extract_all({col}, '[0-9]+'), "
                           f"lambda x: length(x) = 4 and x between '1850' and '2029')) as int)")
    c.sql(f"""create table meta1 as select *, coalesce({year_of('label')}, {year_of('decision_id')}) docket_year
              from meta0""")
    c.sql(f"""create table meta as select decision_id, court, canton, label, docket_year, dt_src,
                 (dt_src is not null and dt_src <= date '{SNAPSHOT}'
                  and (docket_year is null or year(dt_src) >= docket_year - 1)) dt_ok,
                 case when dt_src <= date '{SNAPSHOT}' and (docket_year is null or year(dt_src) >= docket_year - 1)
                      then dt_src end dt,
                 case when dt_src <= date '{SNAPSHOT}' and (docket_year is null or year(dt_src) >= docket_year - 1)
                      then dt_src when docket_year is not null then make_date(docket_year, 1, 1) end dt_assign
              from meta1""")
    c.sql("""create table r as
        select coalesce(am.canonical_id, s.decision_id) decision_id, upper(s.law_code) code, s.article,
               m.canton, m.court, m.dt_assign dt
        from 'data/statute_references.parquet' s
        left join alias_map am on am.alias_id = s.decision_id
        left join meta m on m.decision_id = coalesce(am.canonical_id, s.decision_id)""")
    c.sql("""create table res as
      select r.*, al.sr, sec.section,
        case
          when canton is null then 'no_decision_metadata'
          when r.code in (select code from unv) then 'excluded_unverified_homonym'
          when r.code in (select code from notk) then 'excluded_not_a_cantonal_act'
          when exists (select 1 from dated where dated.code = r.code and (r.dt is null or r.dt >= cast(dated.until as date)))
            then 'excluded_shared_abbreviation'
          when r.code in (select code from hom) and canton not in ('CH','CE') then 'cantonal_homonym'
          when r.code in (select code from hom) then 'excluded_ambiguous_in_federal_court'
          when al.kind = 'shared_abbreviation' then 'excluded_shared_abbreviation'
          when al.kind = 'federal' then 'federal'
          when canton not in ('CH','CE') then 'cantonal_unmapped'
          else 'excluded_unresolved'
        end resolution
      from r left join al on al.code = r.code left join sec on sec.code = r.code""")

    # --- Regimes: which of the acts carried by an SR number a code means. ---
    code_sr = c.sql("select distinct code, sr from res where resolution = 'federal'").df()
    iv = act_intervals(code_sr[~code_sr.code.isin(editions)], acts, alias_sets, former)
    c.register("iv", iv)
    c.register("cut", pd.DataFrame(list(EDITION_CUTOVERS.items()), columns=["sr", "cutover"]))
    c.sql("""create table res2 as select res.*,
        case when res.code in (select code from edi) then '@a'
             when cut.sr is not null and res.dt < cast(cut.cutover as date) and coalesce(iv.regime, '') = '' then '@a'
             else coalesce(iv.regime, '') end regime
      from res
      left join iv on res.resolution = 'federal' and iv.code = res.code and iv.sr = res.sr
           and coalesce(res.dt, date '9999-12-30') >= cast(iv.start as date)
           and coalesce(res.dt, date '9999-12-30') < cast(iv."end" as date)
      left join cut on cut.sr = res.sr and res.resolution = 'federal'""")
    c.sql("""update res2 set resolution = case when canton in ('CH','CE')
                 then 'excluded_pre2011_procedure_in_federal_court' else 'cantonal_pre2011_procedure' end
             where resolution = 'federal' and sr in ('272','312.0') and regime = '' and dt < date '2011-01-01'""")
    c.sql("""create table out as select decision_id, dt,
        case when resolution='federal' then 'SR ' || sr || regime
             when resolution in ('cantonal_homonym','cantonal_unmapped','cantonal_pre2011_procedure')
               then canton || ' ' || code
        end act_id, section, code, article, resolution
      from res2""")
    c.sql(f"""copy (select decision_id, act_id, section, article, min(code) code, min(resolution) resolution
                    from out where act_id is not null group by 1,2,3,4)
              to '{BUILD}/refs.parquet' (compression zstd)""")
    c.sql(f"copy meta to '{BUILD}/meta.parquet' (compression zstd)")
    # Every federal act node with its Fedlex act; `valid_until` is the last day an
    # earlier act applied (its articles are validated against that text).
    nodes = {}
    for (act_id,) in c.sql("select distinct act_id from out where act_id like 'SR %'").fetchall():
        sr, _, reg = act_id[3:].partition("@")
        hist = acts.get(sr) or []
        if reg == "a" or not hist:
            base = max(hist, key=lambda a: a.get("in_force") or "") if hist else {}
            nodes[act_id] = {"sr": sr, "regime": reg, **base,
                             "valid_until": {"311.0": "2006-12-31"}.get(sr) if reg == "a" else None}
            continue
        labels, cur = regime_labels(hist)
        a = next(x for x in hist if labels[x["eli"]] == ("@" + reg if reg else ""))
        later = [x["in_force"] for x in hist if (x.get("in_force") or "") > (a.get("in_force") or "")]
        until = a.get("repealed") or (min(later) if later else None)
        nodes[act_id] = {"sr": sr, "regime": reg, **a,
                         "valid_until": str(pd.Timestamp(until) - pd.Timedelta(days=1))[:10] if reg and until else None}
    json.dump(nodes, open(BUILD / "act_nodes.json", "w"), ensure_ascii=False, indent=0)
    c.sql(f"copy alias_map to '{BUILD}/decision_alias.parquet' (compression zstd)")

    rep = c.sql("""select resolution, count(*) refs, count(distinct decision_id) decisions
                   from out group by 1 order by 2 desc""").df()
    tot = rep.refs.sum()
    rep["share"] = (rep.refs / tot).round(4)
    print(rep.to_string())
    top_excl = c.sql("""select resolution, code, count(*) n from out where act_id is null
                        group by 1,2 order by n desc limit 40""").df()
    regimes = c.sql("""select act_id, count(*) refs, count(distinct decision_id) decisions from out
                       where act_id like 'SR %@%' group by 1 order by 2 desc""").df()
    print(regimes.head(30).to_string())
    dups = c.sql("select rule, count(*) n from alias_map group by 1").df()
    dates = c.sql("""select count(*) decisions, count(*) filter (where dt_src is null) no_date,
                        count(*) filter (where dt_src is not null and not dt_ok) implausible_date,
                        count(*) filter (where dt_src > date '2026-10-26') future_date from meta""").df()
    print(dates.to_string())
    print(dups.to_string())
    json.dump({"total_references": int(tot),
               "unit": "one row of statute_references.parquet (decision, code, article, paragraph)",
               "by_resolution": rep.to_dict(orient="records"),
               "top_excluded_codes": top_excl.to_dict(orient="records"),
               "regimes": regimes.to_dict(orient="records"),
               "duplicate_decisions": dups.to_dict(orient="records"),
               "decision_dates": dates.to_dict(orient="records")[0],
               "alias_overrides": ALIAS_OVERRIDES,
               "aliases_added_from_fedlex": added_from_fedlex,
               "not_cantonal": sorted(NOT_CANTONAL),
               "glued_codes": len(glued),
               "cantonal_homonyms": sorted(CANTONAL_HOMONYMS),
               "unverified_homonyms": sorted(UNVERIFIED_HOMONYMS)},
              open(BUILD / "resolution_report.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
