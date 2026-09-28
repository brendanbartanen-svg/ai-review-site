#!/usr/bin/env python3
"""Export quote-free public data files for the Mistakes audit and Overreach census pages.

Reads two local, read-only research files (it never writes to them) and the
site's own build/manifest.csv, and writes three CSVs to data/:

    data/mistakes_ledger.csv    one row per reconciliation item (141)
    data/overreach_claims.csv   one row per census row (1,340; 1,140 assessable)
    data/paper_summary.csv      one row per paper (33)

Only code columns are exported. Every column in the sources that holds verbatim
paper text or internal notes is dropped:

    ledger: side_a, side_b, notes, evidence, worker_notes, prior_verification, in_draft
    claims: concession_quote, evidence, ruling (base_id is dropped as redundant)

Leak guard: the script fails if any exported cell is longer than 40 characters
or contains a quotation mark, unless the column is metadata taken from
build/manifest.csv (cite, journal, doi). Code columns are additionally checked
against their controlled vocabularies. The vocabulary values are all short and
quote-free, so they pass the length/quote guard as well.

Sources (defaults under /Users/yvp3tf/Documents/CC Sandbox/; override with
environment variables):

    AI_REVIEW_POST   root of the essay project   (Substack/ai-review-post)
    LEDGER_CSV       $AI_REVIEW_POST/RECONCILIATION_LEDGER.csv
    CLAIMS_CSV       $AI_REVIEW_POST/claims/claims_final.csv

Phase 4 (blind second pass) note, checked 2026-09-28: RECONCILIATION_LEDGER.csv
(written 2026-09-26 11:32, after the blind adjudication was ingested into
reconciliation/verdicts.csv) already carries all 11 verdict changes listed in
reconciliation/blind/ADJUDICATION.md and RECONCILIATION_SUMMARY.md section 11,
and the Umansky error-stage recode. verdicts.csv and the ledger agree on every
verdict field for all 141 items. So this script applies NO adjustment. Instead it
asserts the 11 post-Phase-4 codes (PHASE4_EXPECTED) and the section 11 totals
(LEDGER_EXPECTED), and fails if a future ledger drifts from them. If the ledger
is deliberately revised, update those constants and the Methods text together.

Run:  python3 build/export_data.py
"""

import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
SANDBOX = Path("/Users/yvp3tf/Documents/CC Sandbox")

AI_REVIEW_POST = Path(os.environ.get("AI_REVIEW_POST", SANDBOX / "Substack/ai-review-post"))
LEDGER_CSV = Path(os.environ.get("LEDGER_CSV", AI_REVIEW_POST / "RECONCILIATION_LEDGER.csv"))
CLAIMS_CSV = Path(os.environ.get("CLAIMS_CSV", AI_REVIEW_POST / "claims/claims_final.csv"))
MANIFEST = SITE / "build/manifest.csv"
OUT = SITE / "data"

MAX_LEN = 40
QUOTE_CHARS = set("\"'`‘’‚‛“”„‟«»‹›′″")
# Metadata columns copied from build/manifest.csv; exempt from the length/quote guard.
METADATA_COLS = {"cite", "journal", "doi"}

# ---------------------------------------------------------------- vocabularies
LEDGER_VOCAB = {
    "round": {"1", "2"},
    "tier": {"1", "2", "3"},
    "bucket": {"A", "B", "F", "J1", "J2"},
    "resolution": {"R0", "R1", "R2", "R3", "R4"},
    "consequence": {"C0", "C1", "C2", "C3", "n.a."},
    "source": {"article", "supplement", "earlier version", "code", "UAS documentation", "none"},
    "error_stage": {"present in earlier version", "introduced after earlier version",
                    "no earlier version found", "earlier version silent",
                    "different version not comparable", "n.a."},
    "overseer_check": {"CONFIRMED", "CORRECTED"},
    "withdrawn": {"true", "false"},
}

VERDICTS = ["S", "SH", "T1", "T2", "T3a", "T3b", "T4", "LIT", "NC", "NA"]
ASSESSABLE = {"S", "SH", "T1", "T2", "T3a", "T3b", "T4"}
OVERREACH = {"T1", "T2", "T3a", "T3b"}          # T4 is contested, not counted as overreach
HEDGE_TOKENS = {"H0", "HM", "HF", "HMF", "HS", "HC", "HL"}
DESIGN_TOKENS = {"DESC", "CORR", "WITHIN", "QE", "RCT", "OTHER", "NONE"}
SECONDARY_TOKENS = set(VERDICTS)
CLAIMS_VOCAB = {
    "location": {"title", "abstract", "conclusion"},
    "type": {"DES", "ASC", "CAU", "MEC", "SCO", "NUL", "POL", "NC"},
    "scope": {"IN", "BEYOND"},
    "verdict": set(VERDICTS),
    "final_code_source": {"agree", "fable", "codex", "adjudicator", "overruled"},
    "assessable": {"true", "false"},
    "f1": {"true", "false"},
    "overreach": {"true", "false"},
}
# Multi-valued (semicolon-joined) code columns; empty allowed.
CLAIMS_MULTI = {"hedge": HEDGE_TOKENS, "design": DESIGN_TOKENS, "secondary": SECONDARY_TOKENS}

# ---------------------------------------------------------------- expected totals
# RECONCILIATION_SUMMARY.md section 11 (final, after the Phase 4 blind pass).
LEDGER_EXPECTED = {
    "items": 141, "papers": 33, "withdrawn": 17, "surviving": 124,
    "R": {"R1": 83, "R2": 13, "R3": 19, "R4": 9},
    "C": {"C0": 65, "C1": 44, "C2": 13, "C3": 2},
    "papers_with_C2": 12,
}
# The 11 verdicts the overseer changed after the blind pass (ADJUDICATION.md).
PHASE4_EXPECTED = {
    "P05-2": ("R1", "C2"), "P06-3": ("R3", "C1"), "P06-5": ("R2", "C0"),
    "P08-5": ("R3", "C0"), "P12-5": ("R0", "n.a."), "P13-4": ("R3", "C0"),
    "P14-3": ("R4", "C0"), "P20-1": ("R1", "C1"), "P21-1": ("R1", "C1"),
    "P22-1": ("R2", "C0"), "P30-1": ("R0", "n.a."),
}
# Items that RECONCILIATION_SUMMARY.md section 10 moved to R2 on the ICPSR
# deposits (code or its README); the ledger's `source` column still carries the
# first-pass value for these four, so it is updated here.
SOURCE_OVERRIDES = {"P03-1": "code", "P03-4": "code", "P06-5": "code", "P07-4": "code"}
# claims/CLAIMS_RESULTS.md headline.
CLAIMS_EXPECTED = {"rows": 1340, "assessable": 1140, "overreach": 354,
                   "papers_with_overreach": 32, "papers_with_title_abstract_overreach": 21}


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def read_csv(path):
    if not path.is_file():
        die(f"source file not found: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def flag(b):
    return "true" if b else "false"


def read_manifest():
    """Map both the Codex-style id (P01_AERAOpen_shand) and the site pid (P01) to manifest rows."""
    rows = read_csv(MANIFEST)
    by_codex = {r["codex_id"]: r for r in rows}
    by_pid = {r["pid"]: r for r in rows}
    if len(by_pid) != 33:
        die(f"manifest has {len(by_pid)} papers, expected 33")
    return by_codex, by_pid


def paper_meta(m):
    return {"pid": m["pid"], "cite": m["authors"], "journal": m["journal"], "doi": m["doi"]}


# ---------------------------------------------------------------- ledger
def build_ledger(by_codex):
    src = read_csv(LEDGER_CSV)
    out = []
    for r in src:
        m = by_codex.get(r["paper_id"])
        if m is None:
            die(f"ledger item {r['item_id']}: paper_id {r['paper_id']} not in manifest")
        if not r["item_id"].startswith(m["pid"] + "-"):
            die(f"ledger item {r['item_id']} does not match pid {m['pid']}")
        if r["journal"] != m["journal"]:
            die(f"ledger item {r['item_id']}: journal {r['journal']} != manifest {m['journal']}")
        if r["round"] != m["round"]:
            die(f"ledger item {r['item_id']}: round {r['round']} != manifest {m['round']}")
        if not re.fullmatch(r"\d{1,3}", r["minutes"]):
            die(f"ledger item {r['item_id']}: minutes '{r['minutes']}' is not an integer")
        row = {"item_id": r["item_id"], **paper_meta(m)}
        row.update({k: r[k] for k in ("round", "tier", "bucket", "resolution", "consequence",
                                      "source", "error_stage", "minutes", "overseer_check")})
        row["source"] = SOURCE_OVERRIDES.get(r["item_id"], row["source"])
        row["withdrawn"] = flag(r["resolution"] == "R0")
        if (row["resolution"] == "R0") != (row["consequence"] == "n.a."):
            die(f"ledger item {r['item_id']}: R0 must pair with consequence n.a. and vice versa")
        out.append(row)
    return out


def check_ledger(rows):
    ids = [r["item_id"] for r in rows]
    if len(set(ids)) != len(ids):
        die("duplicate item_id in ledger")
    surv = [r for r in rows if r["withdrawn"] == "false"]
    got = {
        "items": len(rows), "papers": len({r["pid"] for r in rows}),
        "withdrawn": len(rows) - len(surv), "surviving": len(surv),
        "R": {k: sum(r["resolution"] == k for r in surv) for k in LEDGER_EXPECTED["R"]},
        "C": {k: sum(r["consequence"] == k for r in surv) for k in LEDGER_EXPECTED["C"]},
        "papers_with_C2": len({r["pid"] for r in surv if r["consequence"] == "C2"}),
    }
    bad = [f"{k}: got {got[k]}, expected {v}" for k, v in LEDGER_EXPECTED.items() if got[k] != v]
    by_id = {r["item_id"]: r for r in rows}
    for iid, (res, con) in PHASE4_EXPECTED.items():
        r = by_id.get(iid)
        if r is None or (r["resolution"], r["consequence"]) != (res, con):
            have = None if r is None else (r["resolution"], r["consequence"])
            bad.append(f"Phase 4 item {iid}: got {have}, expected {(res, con)}")
    if bad:
        die("ledger does not match RECONCILIATION_SUMMARY.md section 11:\n  " + "\n  ".join(bad))
    return got


# ---------------------------------------------------------------- claims
def build_claims(by_codex):
    src = read_csv(CLAIMS_CSV)
    out = []
    for r in src:
        m = by_codex.get(r["pid"])
        if m is None:
            die(f"claim {r['claim_id']}: pid {r['pid']} not in manifest")
        if not re.fullmatch(re.escape(m["pid"]) + r"-[CX]\d{2}[a-z]?", r["claim_id"]):
            die(f"claim {r['claim_id']}: unexpected claim_id format for {m['pid']}")
        if r["journal"] != m["journal"]:
            die(f"claim {r['claim_id']}: journal {r['journal']} != manifest {m['journal']}")
        if not re.fullmatch(r"[0-9A-Za-z .;,()\-–]*", r["concession_page"]):
            die(f"claim {r['claim_id']}: concession_page '{r['concession_page']}' is not a page reference")
        for b in ("f1", "overreach"):
            if r[b] not in ("True", "False"):
                die(f"claim {r['claim_id']}: {b} '{r[b]}' is not True/False")
        v = r["verdict"]
        if (v in OVERREACH) != (r["overreach"] == "True"):
            die(f"claim {r['claim_id']}: overreach flag disagrees with verdict {v}")
        row = {**paper_meta(m), "claim_id": r["claim_id"]}
        row.update({k: r[k] for k in ("location", "type", "scope", "hedge", "design", "verdict",
                                      "secondary", "concession_page")})
        row["final_code_source"] = r["source"]
        row["assessable"] = flag(v in ASSESSABLE)
        row["f1"] = flag(r["f1"] == "True")
        row["overreach"] = flag(r["overreach"] == "True")
        out.append(row)
    return out


def claims_totals(rows):
    ta_pids = {r["pid"] for r in rows if r["overreach"] == "true" and r["location"] in ("title", "abstract")}
    return {
        "rows": len(rows),
        "assessable": sum(r["assessable"] == "true" for r in rows),
        "overreach": sum(r["overreach"] == "true" for r in rows),
        "papers_with_overreach": len({r["pid"] for r in rows if r["overreach"] == "true"}),
        "papers_with_title_abstract_overreach": len(ta_pids),
    }


# ---------------------------------------------------------------- summary
def build_summary(by_pid, ledger, claims):
    out = []
    for pid in sorted(by_pid):
        m = by_pid[pid]
        L = [r for r in ledger if r["pid"] == pid]
        S = [r for r in L if r["withdrawn"] == "false"]
        K = [r for r in claims if r["pid"] == pid]
        row = paper_meta(m)
        row.update({
            "ledger_items": len(L),
            "withdrawn": len(L) - len(S),
            "surviving": len(S),
            **{k: sum(r["resolution"] == k for r in S) for k in ("R1", "R2", "R3", "R4")},
            **{k: sum(r["consequence"] == k for r in S) for k in ("C0", "C1", "C2", "C3")},
            "has_C2": flag(any(r["consequence"] == "C2" for r in S)),
            "claims_total": len(K),
            "claims_assessable": sum(r["assessable"] == "true" for r in K),
            "overreach_claims": sum(r["overreach"] == "true" for r in K),
            **{f"verdict_{v}": sum(r["verdict"] == v for r in K) for v in VERDICTS},
            "overreach_title_abstract": flag(any(r["overreach"] == "true" and r["location"] in ("title", "abstract")
                                                 for r in K)),
        })
        out.append(row)
    return out


# ---------------------------------------------------------------- guard + write
def guard(name, rows, vocab, multi=None):
    multi = multi or {}
    errs = []
    for i, r in enumerate(rows, start=2):  # line 2 = first data row
        for col, val in r.items():
            val = str(val)
            if col in vocab and val not in vocab[col]:
                errs.append(f"{name} line {i} {col}: '{val}' not in vocabulary")
            if col in multi and val and not set(val.split(";")) <= multi[col]:
                errs.append(f"{name} line {i} {col}: '{val}' has a token outside the vocabulary")
            if col in METADATA_COLS:
                continue
            if len(val) > MAX_LEN:
                errs.append(f"{name} line {i} {col}: {len(val)} characters (limit {MAX_LEN})")
            if QUOTE_CHARS & set(val):
                errs.append(f"{name} line {i} {col}: contains a quotation mark")
    if errs:
        die(f"leak guard tripped in {name} ({len(errs)} cells):\n  " + "\n  ".join(errs[:30]))


def write(name, rows):
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(SITE)}: {len(rows)} rows, {len(rows[0])} columns")


def main():
    by_codex, by_pid = read_manifest()

    ledger = build_ledger(by_codex)
    lt = check_ledger(ledger)
    guard("mistakes_ledger.csv", ledger, LEDGER_VOCAB)

    claims = build_claims(by_codex)
    ct = claims_totals(claims)
    guard("overreach_claims.csv", claims, CLAIMS_VOCAB, CLAIMS_MULTI)
    bad = [f"{k}: got {ct[k]}, expected {v}" for k, v in CLAIMS_EXPECTED.items() if ct[k] != v]
    if bad:
        die("claims census does not match claims/CLAIMS_RESULTS.md:\n  " + "\n  ".join(bad))

    summary = build_summary(by_pid, ledger, claims)
    guard("paper_summary.csv", summary, {"has_C2": {"true", "false"},
                                        "overreach_title_abstract": {"true", "false"}})
    if sum(r["ledger_items"] for r in summary) != lt["items"] or sum(r["claims_total"] for r in summary) != ct["rows"]:
        die("paper_summary totals do not add up to the row-level files")

    print("Exporting quote-free data files:")
    write("mistakes_ledger.csv", ledger)
    write("overreach_claims.csv", claims)
    write("paper_summary.csv", summary)

    print("Mistakes audit (matches RECONCILIATION_SUMMARY.md section 11):")
    print(f"  {lt['items']} items in {lt['papers']} papers; {lt['withdrawn']} withdrawn; {lt['surviving']} survive")
    print("  " + " / ".join(f"{k} {v}" for k, v in lt["R"].items())
          + ";  " + " / ".join(f"{k} {v}" for k, v in lt["C"].items()))
    print(f"  papers with at least one C2: {lt['papers_with_C2']}")
    print("Overreach census (matches claims/CLAIMS_RESULTS.md):")
    print(f"  {ct['rows']} rows; {ct['assessable']} assessable; {ct['overreach']} overreach "
          f"({ct['overreach'] / ct['assessable']:.0%})")
    print(f"  papers with overreach: {ct['papers_with_overreach']}; "
          f"with overreach in title or abstract: {ct['papers_with_title_abstract_overreach']}")
    vc = Counter(r["verdict"] for r in claims)
    print("  verdicts: " + ", ".join(f"{v} {vc[v]}" for v in VERDICTS if vc[v]))


if __name__ == "__main__":
    main()
