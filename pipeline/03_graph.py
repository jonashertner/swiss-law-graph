"""Step 2b — graph layers: acts, articles, decisions, citations, co-citation.

Counting unit: a decision referring to an act or article counts once, however
many paragraphs or mentions it cites (statute_references holds one row per
paragraph; `mention_count` is 1 on every row and carries no information).

Citation edges (decision 6): all match types kept; edges scoring < 0.5 dropped
(resolver-detected conflicts); duplicate decisions merged (step 1), then
(source, target) pairs deduplicated and self-citations removed; an edge whose
only evidence is a `bge_pincite` match is flagged inferred. Authority of a
decision = number of distinct decisions citing it.

Co-citation (decision 9): two acts (or two articles) are linked when they are
cited together by at least MIN_ACT (MIN_ART) decisions and the pair is
over-represented: lift = n_xy * N / (n_x * n_y) >= MIN_LIFT. Each node keeps
its TOP_K strongest links by lift; an edge survives if either end keeps it.

Outputs (build/graph/): acts.parquet, act_years.parquet, articles.parquet,
art_years.parquet, act_edges.parquet, art_edges.parquet, top_decisions.parquet,
decisions.parquet (decisions referenced by any top list), citations_report.json
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
OUT = BUILD / "graph"
OUT.mkdir(exist_ok=True)
MIN_ACT, MIN_ART, MIN_LIFT, TOP_K = 20, 10, 2.0, 8
TOP_DECISIONS = 25


def main() -> None:
    c = duckdb.connect()
    c.sql("set preserve_insertion_order = false")
    c.sql(f"create table meta as select * from '{BUILD}/meta.parquet'")
    c.sql(f"create table rv as select * from '{BUILD}/refs_valid.parquet'")
    c.sql(f"create table alias as select * from '{BUILD}/decision_alias.parquet'")

    # --- Citations between decisions. ---
    c.sql(f"""create table raw as select source_decision_id s0, target_decision_id t0, match_type, confidence_score
              from '{ROOT}/data/citations.parquet'""")
    rep = {"raw_edges": c.sql("select count(*) from raw").fetchall()[0][0],
           "dropped_score_below_0_5": c.sql("select count(*) from raw where confidence_score < 0.5").fetchall()[0][0]}
    c.sql("""create table e as select coalesce(a.canonical_id, s0) s, coalesce(b.canonical_id, t0) t, match_type
             from raw left join alias a on a.alias_id = s0 left join alias b on b.alias_id = t0
             where confidence_score >= 0.5""")
    c.sql("""create table cit as select s, t, bool_and(match_type = 'bge_pincite') inferred, count(*) raw_n
             from e where s <> t group by 1, 2""")
    rep["self_citations_after_merge"] = c.sql("select count(*) from e where s = t").fetchall()[0][0]
    rep["duplicate_pairs_removed"] = c.sql("select sum(raw_n - 1) from cit").fetchall()[0][0]
    rep["target_not_in_corpus"] = c.sql("select count(*) from cit where t not in (select decision_id from meta)").fetchall()[0][0]
    c.sql("delete from cit where t not in (select decision_id from meta) or s not in (select decision_id from meta)")
    rep["edges"] = c.sql("select count(*) from cit").fetchall()[0][0]
    rep["edges_inferred_bge_pincite_only"] = c.sql("select count(*) from cit where inferred").fetchall()[0][0]
    c.sql("""create table indeg as select t decision_id, count(*) cited_by,
             count(*) filter (where not inferred) cited_by_direct from cit group by 1""")
    c.sql("create table outdeg as select s decision_id, count(*) cites from cit group by 1")
    print(json.dumps(rep, indent=1, default=str))

    # --- Acts. ---
    c.sql("""create table ad as select distinct act_id, decision_id from rv""")
    c.sql("""create table acts as select rv.act_id,
               count(distinct rv.decision_id) decisions,
               count(distinct rv.decision_id) filter (where m.canton in ('CH','CE')) decisions_federal,
               count(distinct rv.decision_id) filter (where rv.status = 'valid') decisions_valid_article,
               count(*) filter (where rv.status = 'valid') refs_valid,
               count(*) filter (where rv.status = 'not_in_text') refs_not_in_text,
               count(distinct rv.decision_id) filter (where rv.status = 'not_in_text') decisions_not_in_text,
               count(*) filter (where rv.status = 'no_text') refs_no_text,
               count(*) filter (where rv.status in ('cantonal_act_level','cantonal_transitional_procedure')) refs_act_level,
               min(year(m.dt)) first_year, max(year(m.dt)) last_year
             from rv join meta m using (decision_id) group by 1""")
    c.sql("""create table act_years as select act_id, year(m.dt) y, count(*) n
             from ad join meta m using (decision_id) where m.dt is not null group by 1, 2""")
    c.sql("""create table act_nf as select act_id, num, count(distinct decision_id) n from rv
             where status = 'not_in_text' group by 1, 2""")

    # --- Articles. ---
    c.sql("""create table artd as select distinct act_id, art, decision_id from rv where status = 'valid'""")
    c.sql("""create table articles as select act_id, art, count(*) decisions,
               count(*) filter (where m.canton in ('CH','CE')) decisions_federal,
               min(year(m.dt)) first_year, max(year(m.dt)) last_year
             from artd join meta m using (decision_id) group by 1, 2""")
    c.sql("""create table art_years as select act_id, art, year(m.dt) y, count(*) n
             from artd join meta m using (decision_id) where m.dt is not null group by 1, 2, 3""")

    # --- Most-cited decisions referring to each act / article. ---
    c.sql(f"""create table top_art as select act_id, art, decision_id, cited_by, rk from (
                select a.act_id, a.art, a.decision_id, coalesce(i.cited_by, 0) cited_by,
                       row_number() over (partition by a.act_id, a.art
                                          order by coalesce(i.cited_by, 0) desc, m.dt desc, a.decision_id) rk
                from artd a left join indeg i using (decision_id) join meta m using (decision_id))
              where rk <= {TOP_DECISIONS}""")
    c.sql(f"""create table top_act as select act_id, decision_id, cited_by, rk from (
                select a.act_id, a.decision_id, coalesce(i.cited_by, 0) cited_by,
                       row_number() over (partition by a.act_id
                                          order by coalesce(i.cited_by, 0) desc, m.dt desc, a.decision_id) rk
                from ad a left join indeg i using (decision_id) join meta m using (decision_id))
              where rk <= {TOP_DECISIONS}""")
    c.sql("""create table top_decisions as
             select act_id, null art, decision_id, cited_by, rk from top_act
             union all select act_id, art, decision_id, cited_by, rk from top_art""")
    c.sql("""create table decisions as select m.*, coalesce(i.cited_by, 0) cited_by,
                coalesce(i.cited_by_direct, 0) cited_by_direct, coalesce(o.cites, 0) cites
             from meta m left join indeg i using (decision_id) left join outdeg o using (decision_id)
             where decision_id in (select decision_id from top_decisions)""")

    # --- Co-citation, significance-filtered. ---
    def cocite(table: str, key: str, min_n: int, name: str) -> None:
        n_total = c.sql(f"select count(distinct decision_id) from {table}").fetchall()[0][0]
        c.sql(f"create table nx as select {key} k, count(*) n from {table} group by 1")
        c.sql(f"""create table px as select a.{key} x, b.{key} y, count(*) n
                  from {table} a join {table} b on a.decision_id = b.decision_id and a.{key} < b.{key}
                  group by 1, 2 having count(*) >= {min_n}""")
        c.sql(f"""create table sx as select px.*, px.n * {n_total}::double / (nx1.n * nx2.n) lift
                  from px join nx nx1 on nx1.k = px.x join nx nx2 on nx2.k = px.y
                  where px.n * {n_total}::double / (nx1.n * nx2.n) >= {MIN_LIFT}""")
        c.sql(f"""create table {name} as with both_ as (
                    select x, y, n, lift, row_number() over (partition by x order by lift desc, n desc) rx,
                           row_number() over (partition by y order by lift desc, n desc) ry from sx)
                  select x, y, n, lift from both_ where rx <= {TOP_K} or ry <= {TOP_K}""")
        print(name, c.sql(f"select count(*) from px").fetchall()[0][0], "pairs >= min;",
              c.sql(f"select count(*) from sx").fetchall()[0][0], "with lift >=", MIN_LIFT, ";",
              c.sql(f"select count(*) from {name}").fetchall()[0][0], "kept")
        c.sql("drop table nx; drop table px; drop table sx")

    cocite("ad", "act_id", MIN_ACT, "act_edges")
    c.sql("create table artk as select act_id || '|' || art k, decision_id from artd")
    cocite("artk", "k", MIN_ART, "art_edges")

    for t in ("acts", "act_years", "act_nf", "articles", "art_years", "top_decisions", "decisions",
              "act_edges", "art_edges"):
        c.sql(f"copy {t} to '{OUT}/{t}.parquet' (compression zstd)")
    rep["decisions_in_corpus"] = c.sql("select count(*) from meta").fetchall()[0][0]
    rep["decisions_citing_a_resolved_act"] = c.sql("select count(distinct decision_id) from ad").fetchall()[0][0]
    rep["co_citation"] = {"min_decisions_acts": MIN_ACT, "min_decisions_articles": MIN_ART,
                          "min_lift": MIN_LIFT, "top_k": TOP_K}
    json.dump(rep, open(OUT / "citations_report.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
