"""Step 1 — resolve every statute reference to a canonical act.

Inputs (all CC0 / official):
  data/statute_references.parquet   OpenCaseLaw, decision -> (law_code, article, paragraph)
  data/cite-index-*.tsv.gz          OpenCaseLaw, decision -> court, canton, date
  data/sr_taxonomy.csv              Fedlex SPARQL legal taxonomy (SR tree + titles)
  ../opencaselaw/docs/data/law_codes.json, docs/api/law_aliases.json
                                    OpenCaseLaw verified alias -> SR tables

Output: build/refs.parquet  (decision_id, act_id, article, mentions, resolution)
        build/resolution_report.json  every reference accounted for

Rules (each one is disclosed on the page):
  * Language variants collapse onto one SR number (OR = CO = CO(it), BGG = LTF).
  * Former names map to the successor's SR number but keep `former=True`
    (OG -> 173.110, AuG/LEtr -> 142.20), so the timeline can show the hand-over.
  * Cantonal homonyms: some codes name a federal act AND a cantonal act
    (LPA = federal Animal Welfare Act in French, but Geneva's administrative
    procedure act in Geneva decisions). In a cantonal decision such a code is
    read as the deciding canton's act; in a federal decision it is ambiguous
    and excluded. Codes we could not identify with confidence are excluded
    everywhere they are ambiguous — never guessed.
  * Codes absent from the federal tables, cited by cantonal courts, become a
    cantonal act node keyed (canton, code). Cited only by federal courts and
    unknown: excluded as unresolved.
  * Abbreviations shared by two federal acts (32 in the table) are excluded.
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

# Identified cantonal acts sharing a federal abbreviation (read as the deciding canton's act).
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
}
# Heavily concentrated in one canton, identity not verified: excluded wherever ambiguous.
UNVERIFIED_HOMONYMS = {
    "LMC", "LPFC", "KAG", "VPRG", "LEP", "LCP", "LAP", "LPG", "STREG",
    "LTB", "LCMP", "VGV", "OPN", "LEH", "LOP", "VGS",
}


# Codes that name a repealed act (or a former edition) sharing its successor's SR number.
# Value: (sr, regime). Article numbering differs, so they get their own node.
# AuG/LEtr/LStr -> AIG is a pure rename (2019, same numbering): merged, not listed here.
FORMER_CODE_REGIME = {
    **{k: ("173.110", "1943") for k in ("OG", "OJ", "AOG", "BUNDESRECHTSPFLEGEGESETZ")},
    **{k: ("312.0", "1934") for k in ("BSTP", "PPF", "BUNDESSTRAFRECHTSPFLEGE")},
    **{k: ("142.20", "1931") for k in ("ANAG", "LSEE", "LDDS")},
    **{k: ("832.10", "1911") for k in ("KUVG", "LAMA")},
    **{k: ("235.1", "1992") for k in ("ADSG", "DSG1992", "ALPD")},
    **{k: ("101", "1874") for k in ("ABV", "BV1874", "ACST")},
    **{k: ("311.0", "a") for k in ("ASTGB", "ACP")},
    **{k: ("210", "a") for k in ("AZGB", "ACC")},
    **{k: ("220", "a") for k in ("AOR", "ACO")},
}
# A current code in a decision dated before the cut-over refers to the earlier act.
DATE_CUTOVERS = {
    "101": ("2000-01-01", "1874"),     # BV 1999 in force 1.1.2000
    "235.1": ("2023-09-01", "1992"),   # revised DSG in force 1.9.2023
    "311.0": ("2007-01-01", "a"),      # StGB general part revision in force 1.1.2007
    "832.10": ("1996-01-01", "1911"),  # KVG in force 1.1.1996
}


def main() -> None:
    lc = json.load(open(OCL / "docs/data/law_codes.json"))
    la = json.load(open(OCL / "docs/api/law_aliases.json"))
    alias, former = {}, set()
    for k, v in lc["alias_to_sr"].items():
        alias[norm(k)] = v
    for k, e in (la.get("aliases") or {}).items():
        if isinstance(e, dict) and e.get("sr_number"):
            nk = norm(k)
            alias.setdefault(nk, e["sr_number"])
            if e.get("kind") in ("former", "former_edition"):
                former.add(nk)

    rows = []
    for code, sr in alias.items():
        if isinstance(sr, list):
            rows.append((code, None, "shared_abbreviation", False))
        else:
            rows.append((code, sr, "federal", code in former))
    al = pd.DataFrame(rows, columns=["code", "sr", "kind", "former"])

    c = duckdb.connect()
    c.register("al", al)
    c.register("hom", pd.DataFrame({"code": sorted(CANTONAL_HOMONYMS)}))
    c.register("unv", pd.DataFrame({"code": sorted(UNVERIFIED_HOMONYMS)}))
    cite = glob.glob(str(ROOT / "data/cite-index-*.tsv.gz"))[0]
    c.sql(f"""create table meta as
        select column5 decision_id, any_value(column1) court, any_value(column2) canton,
               min(try_cast(column3 as date)) dt
        from read_csv('{cite}', delim='\t', header=false, skip=1, quote='', all_varchar=true)
        group by 1""")
    c.sql(f"""create table r as
        select s.decision_id, upper(s.law_code) code, s.article, coalesce(s.mention_count,1) mentions,
               m.canton, m.court
        from '{ROOT}/data/statute_references.parquet' s left join meta m using (decision_id)""")
    c.sql("""create table res as
      select r.*, al.sr, al.former,
        case
          when canton is null then 'no_decision_metadata'
          when r.code in (select code from unv) then 'excluded_unverified_homonym'
          when r.code in (select code from hom) and canton not in ('CH','CE') then 'cantonal_homonym'
          when r.code in (select code from hom) then 'excluded_ambiguous_in_federal_court'
          when al.kind = 'shared_abbreviation' then 'excluded_shared_abbreviation'
          when al.kind = 'federal' then 'federal'
          when canton not in ('CH','CE') then 'cantonal_unmapped'
          else 'excluded_unresolved'
        end resolution
      from r left join al on al.code = r.code""")
    # --- Regimes: one SR number can carry entirely different acts over time. ---
    c.register("fr_codes", pd.DataFrame(
        [(k, sr, reg) for k, (sr, reg) in FORMER_CODE_REGIME.items()], columns=["code", "sr", "regime"]))
    c.register("cut", pd.DataFrame(
        [(sr, d, reg) for sr, (d, reg) in DATE_CUTOVERS.items()], columns=["sr", "cutover", "regime"]))
    c.sql("""create table res2 as select res.*,
        m.dt,
        coalesce(f.regime, case when res.sr = cut.sr and m.dt < cast(cut.cutover as date) then cut.regime end) regime,
        (res.sr in ('272','312.0') and res.resolution = 'federal' and f.regime is null
           and m.dt < date '2011-01-01') pre2011_proc
      from res left join meta m using (decision_id)
      left join fr_codes f on f.code = res.code and res.resolution = 'federal'
      left join cut on cut.sr = res.sr and res.resolution = 'federal'""")
    c.sql("""update res2 set resolution = case when canton in ('CH','CE')
                 then 'excluded_pre2011_procedure_in_federal_court' else 'cantonal_pre2011_procedure' end
             where pre2011_proc""")
    c.sql("""create table out as select decision_id,
        case when resolution='federal' then 'SR ' || sr || coalesce('@' || regime, '')
             when resolution in ('cantonal_homonym','cantonal_unmapped','cantonal_pre2011_procedure')
               then canton || ' ' || code
        end act_id, code, article, mentions, resolution, coalesce(former,false) former
      from res2""")
    c.sql(f"copy (select * from out where act_id is not null) to '{BUILD}/refs.parquet' (compression zstd)")
    c.sql(f"copy meta to '{BUILD}/meta.parquet' (compression zstd)")

    rep = c.sql("""select resolution, count(*) refs, sum(mentions) mentions,
                    count(distinct decision_id) decisions from out group by 1 order by 2 desc""").df()
    tot = rep.refs.sum()
    rep["share"] = (rep.refs / tot).round(4)
    print(rep.to_string())
    top_excl = c.sql("""select resolution, code, count(*) n from out where act_id is null
                        group by 1,2 order by n desc limit 40""").df()
    print(top_excl.to_string())
    json.dump({"total_references": int(tot),
               "by_resolution": rep.to_dict(orient="records"),
               "top_excluded_codes": top_excl.to_dict(orient="records"),
               "cantonal_homonyms": sorted(CANTONAL_HOMONYMS),
               "unverified_homonyms": sorted(UNVERIFIED_HOMONYMS)},
              open(BUILD / "resolution_report.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
