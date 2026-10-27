"""Step 2a — validate every article reference against the official text (decision 7).

An article node exists only if the article exists in the act's Fedlex text:
  * current federal act   -> the consolidated text applicable on the run date,
                             main body only (transitional blocks restart numbering);
                             a section code (SchlT ZGB) -> that block's articles
  * earlier act (`@1943`) -> the last text in force before it was replaced
  * edition `@a` of StGB  -> the text in force on 2006-12-31; aZGB/aOR -> today's
                             numbering (Fedlex publishes no XML for older editions)
References to an article absent from that text go to the act's "not found in
the text" bucket; acts without a published text keep their references at act
level ("articles not checked"). Cantonal acts have no article layer.

Transitional cantonal procedure: a cantonal decision of 2011-2013 citing
ZPO/CPC or StPO/CPP with an article that does not exist in the federal code
cites the canton's former code, still applied to cases pending on 1.1.2011
(VD above all), and is moved to `<canton> <code>`. Later decisions keep such
references in the not-found bucket.

Inputs:  build/refs.parquet, build/meta.parquet, build/act_nodes.json,
         data/fedlex_structure.json.gz, data/fedlex_articles.json,
         data/fedlex_regime_articles.json
Outputs: build/refs_valid.parquet  decision_id, act_id, art (article key or null), status
         build/articles.parquet    every article node: act_id, art, num, ord, level, rep
         build/levels.parquet      structural units of each act (book, title, ...)
         build/validation_report.json
"""
import gzip
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

from artnum import LATIN, TOKEN, parse_eid, sort_key

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def norm_num(a: str) -> str | None:
    m = TOKEN.match(a or "")
    return (m.group(1) + re.sub(r"\s+", "", m.group(2) or "")).lower() if m else None


def main() -> None:
    nodes = json.load(open(BUILD / "act_nodes.json"))
    sp = ROOT / "data/fedlex_structure.json.gz"
    struct = json.load(gzip.open(sp, "rt"))["acts"] if sp.exists() else {}
    flat = json.load(open(ROOT / "data/fedlex_articles.json"))["acts"]
    regimes = json.load(open(ROOT / "data/fedlex_regime_articles.json"))["regimes"]

    arts, levels, valid = [], [], []   # valid: (act_id, section, num) -> art key
    for act_id, nd in nodes.items():
        sr, reg = nd["sr"], nd["regime"]
        st = struct.get(sr) or {}
        if reg == "" and st.get("articles"):
            for i, lv in enumerate(st["levels"]):
                levels.append((act_id, i, lv["id"], lv["p"], json.dumps(lv["num"], ensure_ascii=False),
                               json.dumps(lv["h"], ensure_ascii=False)))
            seen = set()
            for i, a in enumerate(st["articles"]):
                if not a["n"]:
                    continue
                nums = parse_eid(a["id"]) or [a["n"]]   # "Art. 274–274g" holds 274, 274a ... 274g
                label = nums[0] if len(nums) == 1 else f"{nums[0]}–{nums[-1]}"
                arts.append((act_id, a["id"], label, i, a["l"], a["rep"],
                             json.dumps(a["h"], ensure_ascii=False) if a["h"] else None))
                top = a["id"].split("/")[0]
                section = top if top.startswith("disp") else ""
                for n in nums:
                    if (section, n) not in seen:   # first occurrence wins
                        seen.add((section, n))
                        valid.append((act_id, section, n, a["id"]))
            continue
        if reg == "a" and nd.get("valid_until") is None and st.get("articles"):
            src = [a["n"] for a in st["articles"] if a["n"] and not a["id"].startswith("disp")]
        elif reg == "":
            src = (flat.get(sr) or {}).get("articles")
        else:
            src = (regimes.get(act_id) or {}).get("articles")
        if not src:
            continue
        src = list(dict.fromkeys(n for n in (norm_num(x) for x in src) if n))
        for i, n in enumerate(sorted(src, key=sort_key)):
            key = "art_" + n
            arts.append((act_id, key, n, i, -1, False, None))
            valid.append((act_id, "", n, key))

    A = pd.DataFrame(arts, columns=["act_id", "art", "num", "ord", "level", "rep", "h"])
    L = pd.DataFrame(levels, columns=["act_id", "idx", "eid", "parent", "num", "h"])
    V = pd.DataFrame(valid, columns=["act_id", "section", "num", "art"])
    has_text = set(A.act_id)

    c = duckdb.connect()
    c.register("valid_nums", V)
    c.register("with_text", pd.DataFrame({"act_id": sorted(has_text)}))
    c.sql(f"""create table r as select r.*, m.canton, m.dt_assign dt,
                 regexp_extract(r.article, '^(\\d+(?:[a-z]?(?:{"|".join(LATIN)})|[a-z])?)') num
              from '{BUILD}/refs.parquet' r join '{BUILD}/meta.parquet' m using (decision_id)""")
    c.sql("""create table v as select r.*, vn.art,
        case when r.act_id not like 'SR %' then 'cantonal_act_level'
             when vn.art is not null then 'valid'
             when r.act_id in (select act_id from with_text) then 'not_in_text'
             else 'no_text' end as status
        from r left join valid_nums vn on vn.act_id = r.act_id and vn.section = coalesce(r.section, '')
             and vn.num = r.num""")
    # Former cantonal procedure codes applied to pending cases after 2011.
    transitional = """status = 'not_in_text' and act_id in ('SR 272', 'SR 312.0') and canton not in ('CH', 'CE')
                      and dt between date '2011-01-01' and date '2013-12-31'"""
    c.sql(f"create table moved as select * from v where {transitional}")
    print("transitional cantonal procedure by canton/year:")
    print(c.sql("""select canton, year(dt) y, count(*) n from moved group by all order by n desc limit 15""").df().to_string())
    c.sql(f"""update v set act_id = canton || ' ' || code, art = null, status = 'cantonal_transitional_procedure'
              where {transitional}""")
    c.sql(f"""copy (select decision_id, act_id, art, status, num, code from v)
              to '{BUILD}/refs_valid.parquet' (compression zstd)""")
    A.to_parquet(BUILD / "articles.parquet", index=False)
    L.to_parquet(BUILD / "levels.parquet", index=False)

    by_status = c.sql("""select status, count(*) refs, count(distinct decision_id) decisions
                         from v group by 1 order by 2 desc""").df()
    print(by_status.to_string())
    per_act = c.sql("""select act_id, count(*) refs,
                          count(*) filter (where status='valid') valid,
                          count(*) filter (where status='not_in_text') not_in_text,
                          count(*) filter (where status='no_text') no_text
                       from v where act_id like 'SR %' group by 1 order by refs desc""").df()
    per_act["nf_share"] = (per_act.not_in_text / per_act.refs).round(3)
    print(per_act.head(25).to_string())
    print("highest not-found shares (>= 500 refs):")
    print(per_act[per_act.refs >= 500].sort_values("nf_share", ascending=False).head(25).to_string())
    top_nf = c.sql("""select act_id, num, count(*) n from v where status = 'not_in_text'
                      group by 1, 2 qualify row_number() over (partition by act_id order by n desc) <= 10
                      order by act_id, n desc""").df()
    json.dump({"unit": "distinct (decision, act, section, article)",
               "by_status": by_status.to_dict(orient="records"),
               "acts_with_text": len(has_text), "article_nodes": len(A),
               "per_act": per_act.to_dict(orient="records"),
               "top_not_found": top_nf.to_dict(orient="records")},
              open(BUILD / "validation_report.json", "w"), indent=0, default=str)


if __name__ == "__main__":
    main()
