#!/usr/bin/env python3
"""Generate the per-paper pages, the Corrections page and build/manifest.csv.

Reads the two read-only review archives (Claude pipeline and Codex pipeline),
the paper manifest, the Claude ratings tables and build/corrections.yml, and
writes:

    papers/<PID>/index.qmd    paper page: ratings, both syntheses in tabs
    papers/<PID>/claude.qmd   full Claude review
    papers/<PID>/codex.qmd    full Codex review
    corrections.qmd           corrections log
    _includes/prompts.qmd     the six prompts, included by methods.qmd
    _includes/comparison_table.qmd   ratings comparison, included by comparison.qmd
    prompts/*.md              copies of the six prompt files
    build/manifest.csv        one row per paper

index.qmd, methods.qmd and comparison.qmd are hand-edited and never touched.

Nothing is ever written to the source archives. Paper PDFs, extracted paper
text and images are never copied.

Usage:  python3 build/build_site.py
Needs:  Python 3.8+, PyYAML. Source locations can be overridden with the
        environment variables CLAUDE_REVIEWS, CODEX_ROOT, CLAUDE_PROMPTS.
"""

import csv
import json
import os
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("ERROR: PyYAML is required (pip install pyyaml).")

# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------

SITE = Path(__file__).resolve().parent.parent
SANDBOX = Path("/Users/yvp3tf/Documents/CC Sandbox")

CLAUDE_REVIEWS = Path(os.environ.get("CLAUDE_REVIEWS", SANDBOX / "ai_paper_reviewer/reviews"))
CODEX_ROOT = Path(os.environ.get("CODEX_ROOT", SANDBOX / "second-reader"))
CLAUDE_PROMPTS = Path(os.environ.get("CLAUDE_PROMPTS", SANDBOX / "ai_paper_reviewer/prompts/reader"))

CODEX_REVIEWS = CODEX_ROOT / "reviews"
MANIFEST_MD = CODEX_ROOT / "papers/MANIFEST.md"
COMPARISON_MD = CODEX_ROOT / "COMPARISON_ratings.md"
LANDSCAPE = CLAUDE_REVIEWS / "landscape_aera_quant_202609"
RESULTS_R1 = LANDSCAPE / "RESULTS.md"
RESULTS_R2 = LANDSCAPE / "RESULTS_round2.md"

CORRECTIONS_YML = SITE / "build/corrections.yml"
MANIFEST_CSV = SITE / "build/manifest.csv"

# Codex ID -> Claude review folder. Fixed on purpose: the archive holds stale
# duplicate folders with other date prefixes, which must be ignored.
MAPPING = OrderedDict([
    ("P01_AERAOpen_shand", "20260902_curriculum_implementation_and_change_management_a_new_framew"),
    ("P02_AERAOpen_lee", "20260902_understanding_the_landscape_of_rural_racial_achievement_gaps"),
    ("P03_AERAOpen_holzman", "20260902_race_nativity_and_the_labor_market_returns_to_college_major"),
    ("P04_AERAOpen_boles", "20260902_geographic_disparities_in_availability_of_secondary_advanced_stem"),
    ("P05_AERAOpen_britton", "20260902_student_teacher_ethnoracial_matching_and_postsecondary_access"),
    ("P06_AERAOpen_holtz", "20260925_dual_language_for_whom_a_critical_race_spatial_analysis_of"),
    ("P07_AERAOpen_odle", "20260925_high_performing_pell_institutions_identifying_and_exploring"),
    ("P08_AERAOpen_gao", "20260925_a_longitudinal_analysis_of_school_mobility_for_students_in_foster_care"),
    ("P09_AERJ_johnson", "20260902_the_politics_of_platform_allocation_commencement_speaker"),
    ("P10_AERJ_chin", "20260902_impacts_of_school_choice_expansion_on_public_school_finance"),
    ("P11_AERJ_gilmour", "20260902_composition_distribution_and_stability_of_the_special_education"),
    ("P12_AERJ_umansky", "20260902_uses_characteristics_and_effects_of_extra_instructional_time"),
    ("P13_AERJ_little", "20260902_school_district_superintendents_leadership_of_early_childhood"),
    ("P14_EEPA_truwit", "20260902_the_model_itself_or_something_else_whether_and_how_the"),
    ("P15_EEPA_xu", "20260902_bulwark_or_barrier_the_effect_of_academic_criteria_based"),
    ("P16_EEPA_delgado", "20260902_classroom_composition_affects_teacher_performance_ratings"),
    ("P17_EEPA_broton", "20260902_promoting_academic_success_through_university_microgrants"),
    ("P18_EEPA_choi", "20260902_examining_the_impact_of_performance_based_funding_policy"),
    ("P19_EEPA_munoz", "20260925_beyond_school_police_officers_racialethnic_disparities_in_expo"),
    ("P20_EEPA_camp", "20260925_the_effects_of_the_four_day_school_week_on_teacher_recruitment"),
    ("P21_EEPA_ganimian", "20260925_the_reliability_of_classroom_observations_and_student_surveys"),
    ("P22_EEPA_cleveland", "20260925_the_lingering_legacy_of_redlining_on_school_funding_diversity"),
    ("P23_EEPA_acris", "20260925_does_civic_education_impact_primary_school_students_civic_ou"),
    ("P24_ER_gicheva", "20260902_postsecondary_gaps_in_recovery_from_the_covid19_pandemic"),
    ("P25_ER_perry", "20260902_necessary_but_not_sufficient_school_administrator_support"),
    ("P26_ER_whitfield", "20260902_how_better_fafsa_changed_federal_aid_applications"),
    ("P27_ER_yoon", "20260902_fifteen_years_of_change_in_high_quality_cte_participation"),
    ("P28_ER_heller", "20260902_the_decline_of_adult_education_supply_demand_and_public_support"),
    ("P29_ER_polikoff", "20260925_what_explains_support_for_race_related_topics_in_the_curriculum"),
    ("P30_ER_ambali", "20260925_unequal_foundations_racial_disparities_in_school_building"),
    ("P31_ER_cristancho", "20260925_the_effects_of_homicides_on_childcare_classroom_quality_and_child"),
    ("P32_ER_burdickwill", "20260925_sidewalks_for_students_google_street_view_measures_of_walkability"),
    ("P33_ER_lyon", "20260925_racial_status_threat_and_antidei_efforts_in_local_school"),
])

ROUND_BY_PREFIX = {"20260902": 1, "20260925": 2}
CLAUDE_REVIEW_DATE = {1: "2026-09-02", 2: "2026-09-25"}
CODEX_REVIEW_DATE = "2026-09-25"

JOURNAL_SHORT = {
    "AERA Open": "AERA Open",
    "American Educational Research Journal": "AERJ",
    "Educational Evaluation and Policy Analysis": "EEPA",
    "Educational Researcher": "ER",
}

PROMPTS = [  # (file stem, section title)
    ("methods", "Methods sub-review"),
    ("literature", "Literature sub-review"),
    ("writing", "Writing sub-review"),
    ("contribution", "Contribution sub-review"),
    ("reproducibility", "Reproducibility sub-review"),
    ("synthesis", "Synthesis"),
]

DIMENSIONS = [  # (label, RESULTS column, Codex JSON stem, letter code)
    ("Methods", "Methods", "review_1_methods", "M"),
    ("Literature", "Lit", "review_2_literature", "L"),
    ("Writing", "Writing", "review_3_writing", "W"),
    ("Contribution", "Contrib", "review_4_contribution", "C"),
    ("Reproducibility", "Repro", "review_5_reproducibility", "R"),
]

OVERALL_CATEGORIES = ["Landmark", "Solid Contribution", "Useful with Caveats", "Treat with Caution"]
SEVERITY = {"Landmark": 4, "Solid Contribution": 3, "Useful with Caveats": 2, "Treat with Caution": 1}
CODEX_OVERALL = {
    "landmark_contribution": "Landmark",
    "solid_contribution": "Solid Contribution",
    "useful_with_caveats": "Useful with Caveats",
    "treat_with_caution": "Treat with Caution",
}
CONF_LABEL = {"mod": "moderate", "high": "high", "low": "low"}

# --------------------------------------------------------------------------
# Site text (fixed wording; edit here)
# --------------------------------------------------------------------------

BANNER_CLAUDE_R1 = (
    "Claude pipeline, round one (reviewed 2026-09-02). Five sub-reviews were written by "
    "separate Claude Opus sessions, one per dimension; the synthesis was written by Claude "
    "Fable 5.1, which read the paper and checked the sub-reviews against the extracted text "
    "but did not render PDF pages. Not page-verified. Sub-reviews are first-layer outputs "
    "and may contain claims the synthesis did not adopt."
)
BANNER_CLAUDE_R1_EXTRA = {
    "P28": "In this run, sub-reviews were relayed through a coordinating session rather than "
           "written into the folder directly.",
    "P04": "In this run, sub-reviews were relayed through a coordinating session rather than "
           "written into the folder directly.",
    "P12": "In this run, sub-reviews were reused from an earlier attempt that hit a rate limit.",
}
BANNER_CLAUDE_R2 = (
    "Claude pipeline, round two (reviewed 2026-09-25). Five sub-reviews were written by "
    "separate Claude Opus 5.5 sessions, one per dimension; the synthesis was written by a "
    "Claude Fable 5.1 overseer that rendered PDF pages and checked sub-review claims against "
    "them. Page-verified: see the Verification notes at the end of the synthesis, which tag "
    "each checked claim CONFIRMED, CORRECTED or COULD NOT CHECK. Sub-reviews are first-layer "
    "outputs and may contain claims the overseer corrected."
)
BANNER_CODEX = (
    "Codex pipeline (reviewed 2026-09-25). Independent second reader: OpenAI GPT-6 (astra, "
    "high reasoning) run through the Codex CLI with the same six prompts, given the paper and "
    "no other information; it had no access to the Claude reviews or to the project's aims. "
    "Five sub-reviews were written by separate sessions, one per dimension; the synthesis by a "
    "sixth session that read them. Each Codex synthesis ends with its own Verification notes."
)

RESPONSES_TEXT = (
    "Authors of the reviewed paper, and readers who find an error in a review, can respond in "
    "the discussion thread below once it is enabled, or open an issue in the site's GitHub "
    "repository. Corrections are logged on the Corrections page with dates."
)

GISCUS_PLACEHOLDER = """<!--
Giscus discussion thread placeholder.
To enable, uncomment the `comments: giscus:` block in _quarto.yml (it needs the
GitHub repository to be public, Discussions turned on, the giscus app installed,
and the repo-id / category-id values from https://giscus.app). Quarto then adds
the thread at the bottom of every page, directly below this section.
-->"""

CORRECTIONS_INTRO = (
    "This page lists every known error in the published reviews, with the date it was found "
    "and what was changed. Corrections are inserted into the affected review as dated notes; "
    "the original sentence is left in place so readers can see what was wrong. The round-two "
    "Claude syntheses also carry a Verification notes section in which the overseer model "
    "tagged each checked sub-review claim as CONFIRMED, CORRECTED or COULD NOT CHECK; across "
    "the 13 round-two papers, 14 of 264 checked claims were corrected at that stage. Those "
    "in-pipeline corrections are visible in each synthesis and are not repeated here."
)
CORRECTIONS_OUTRO = (
    "To report an error, open an issue in the site's GitHub repository or use the discussion "
    "thread on the paper's page."
)

GENERATED_NOTICE = "<!-- GENERATED by build/build_site.py from the review archives. Do not edit by hand; edit the generator or build/corrections.yml and rebuild. -->"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


class BuildError(Exception):
    pass


def fail(msg):
    raise BuildError(msg)


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def yq(value):
    """Scalar for YAML front matter (a JSON string is a valid YAML double-quoted scalar)."""
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def front_matter(fields):
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {yq(v)}" if not isinstance(v, bool) else f"{k}: {'true' if v else 'false'}")
    lines.append("---")
    return "\n".join(lines)


def parse_md_tables(text):
    """Return a list of tables; each is (header_cells, [row_cells...])."""
    tables, cur = [], None
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s[1:-1].split("|")]
            if cur is None:
                cur = (cells, [])
            elif all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
                continue
            else:
                cur[1].append(cells)
        else:
            if cur is not None:
                tables.append(cur)
                cur = None
    if cur is not None:
        tables.append(cur)
    return tables


def short_pid(codex_id):
    num, _journal, name = codex_id.split("_", 2)
    return f"{num}_{name}"


def normalize_overall(s):
    s = s.replace("**", "").strip()
    base = s.split(" (")[0].strip()
    for cat in OVERALL_CATEGORIES:
        if base.lower() == cat.lower():
            return cat, s
    fail(f"Unrecognized overall rating: {s!r}")


def claude_dim_display(cell):
    m = re.fullmatch(r"\s*(Strong|Adequate|Weak|Insufficient)\s*\((mod|high|low)\)\s*", cell.replace("**", ""))
    if not m:
        fail(f"Unrecognized Claude dimension cell: {cell!r}")
    return m.group(1), f"{m.group(1)} ({CONF_LABEL[m.group(2)]})"


def conf_bucket(c):
    # Same buckets the Codex pipeline's own renderer uses (second-reader/render.py).
    return "high" if c >= 0.85 else "moderate" if c >= 0.70 else "low" if c >= 0.50 else "very low"


# ---- markdown transforms ---------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})(\s+\S.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])(\s+)")
META_RE = re.compile(r"^\*\*(Authors|Venue|Review Date|Model|Review Mode):\*\*")


def split_h1(text):
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].startswith("# "):
        fail("expected an H1 title on the first line")
    return lines[0][2:].strip(), lines[1:]


def strip_metadata(lines):
    """Drop the leading Authors/Venue/Review Date/Model/Review Mode block and its --- rule."""
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s == "---" or META_RE.match(s):
            i += 1
            continue
        break
    return lines[i:]


def demote(lines):
    out, in_fence = [], False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            if len(m.group(1)) >= 6:
                fail(f"cannot demote heading below level 6: {line[:60]!r}")
            line = "#" + line
        out.append(line)
    return out


BLOCK_SPACING_STATS = Counter()


def ensure_block_spacing(lines):
    """Insert the blank line Pandoc needs before a list, heading, table or blockquote that
    directly follows a line of other text. The review files were written for renderers
    that do not need it (e.g. "**Strengths:**" followed at once by "- item"); without the
    blank line Pandoc runs the list into the paragraph. Nested/continued list lines and
    consecutive table or quote lines are left alone."""
    out, in_fence = [], False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        prev = out[-1] if out else ""
        kind = None
        if not in_fence and prev.strip():
            if LIST_ITEM_RE.match(line):
                if not LIST_ITEM_RE.match(prev) and not prev.startswith((" ", "\t")):
                    kind = "list"
            elif HEADING_RE.match(line):
                kind = "heading"
            elif line.lstrip().startswith("|") and not prev.lstrip().startswith("|"):
                kind = "table"
            elif line.lstrip().startswith(">") and not prev.lstrip().startswith(">"):
                kind = "blockquote"
        if kind:
            out.append("")
            BLOCK_SPACING_STATS[kind] += 1
        out.append(line)
    return out


def guard_rules(lines):
    """Make sure every '---' rule has blank lines around it, so Pandoc never reads it
    as a YAML metadata delimiter or a setext heading underline."""
    out = []
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if out and out[-1].strip():
                out.append("")
            out.append(line)
            if i + 1 < len(lines) and lines[i + 1].strip():
                out.append("")
        else:
            out.append(line)
    return out


def escape_dollars(lines):
    """Escape $ outside inline code so currency is never read as TeX math."""
    out, in_fence = [], False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
        if in_fence or "$" not in line:
            out.append(line)
            continue
        parts = re.split(r"(`+[^`]*`+)", line)
        out.append("".join(p if p.startswith("`") else re.sub(r"(?<!\\)\$", r"\\$", p) for p in parts))
    return out


def block_bounds(lines, idx):
    """(indent, last_line_index) for the paragraph / list item / table containing lines[idx]."""
    if lines[idx].lstrip().startswith("|"):
        k = idx
        while k + 1 < len(lines) and lines[k + 1].lstrip().startswith("|"):
            k += 1
        return len(lines[idx]) - len(lines[idx].lstrip()), k
    # walk back to the start of the block
    j = idx
    while j > 0 and not LIST_ITEM_RE.match(lines[j]) and lines[j - 1].strip() and not HEADING_RE.match(lines[j - 1]):
        j -= 1
    m = LIST_ITEM_RE.match(lines[j])
    indent = len(m.group(0)) if m else len(lines[j]) - len(lines[j].lstrip())
    # walk forward to the end of the block
    k = idx
    while (k + 1 < len(lines) and lines[k + 1].strip()
           and not LIST_ITEM_RE.match(lines[k + 1]) and not HEADING_RE.match(lines[k + 1])):
        k += 1
    return indent, k


def apply_insertions(lines, specs, label):
    """specs: list of dicts {anchor, block (list of str), allow_multiple, tag}.
    All anchors are located in the ORIGINAL lines first (so inserted notes can never be
    matched), then inserted. Returns (new_lines, {tag: count})."""
    inserts = {}  # last-line index -> list of block-lines
    counts = Counter()
    for spec in specs:
        hits = [i for i, line in enumerate(lines) if spec["anchor"] in line]
        if not hits:
            fail(f"[{label}] anchor NOT FOUND ({spec['tag']}): {spec['anchor']!r}")
        if len(hits) > 1 and not spec.get("allow_multiple"):
            fail(f"[{label}] anchor matched {len(hits)} times, expected 1 ({spec['tag']}): {spec['anchor']!r} "
                 f"at lines {[h + 1 for h in hits]}")
        for h in hits:
            indent, last = block_bounds(lines, h)
            pad = " " * indent
            inserts.setdefault(last, []).append([""] + [pad + b if b else "" for b in spec["block"]])
            counts[spec["tag"]] += 1
    out = []
    for i, line in enumerate(lines):
        out.append(line)
        for block in inserts.get(i, []):
            out.extend(block)
        if i in inserts and i + 1 < len(lines) and lines[i + 1].strip():
            out.append("")
    return out, counts


# --------------------------------------------------------------------------
# Load inputs
# --------------------------------------------------------------------------


def load_manifest():
    tables = parse_md_tables(read(MANIFEST_MD))
    hdr, rows = next(t for t in tables if t[0][:2] == ["ID", "Journal"])
    out = {}
    for r in rows:
        d = dict(zip(hdr, r))
        out[d["ID"]] = {
            "journal_full": d["Journal"],
            "journal": JOURNAL_SHORT[d["Journal"]],
            "authors": d["Authors"],
            "title": d["Title"],
            "doi": d["DOI"],
            "online": d["Online"],
        }
    return out


def load_claude_results():
    out = {}
    for path, rnd in ((RESULTS_R1, 1), (RESULTS_R2, 2)):
        tables = parse_md_tables(read(path))
        hdr, rows = next(t for t in tables if "Overall" in t[0] and "Review folder" in t[0])
        for r in rows:
            d = dict(zip(hdr, r))
            folder = d["Review folder"].split("/")[-1]
            overall, overall_full = normalize_overall(d["Overall"])
            dims = {}
            for label, col, _stem, _code in DIMENSIONS:
                dims[label] = claude_dim_display(d[col])
            out[folder] = {"overall": overall, "overall_full": overall_full, "dims": dims,
                           "results_round": rnd, "paper": d["Paper"]}
    return out


def load_codex(codex_id):
    folder = CODEX_REVIEWS / codex_id
    syn = json.loads(read(folder / "synthesis.json"))
    raw = syn.get("overall_rating")
    if raw not in CODEX_OVERALL:
        fail(f"{codex_id}: unknown Codex overall_rating {raw!r}")
    dims = {}
    for label, _col, stem, _code in DIMENSIONS:
        j = json.loads(read(folder / f"{stem}.json"))
        rating = str(j["rating"]).strip().capitalize()
        conf = float(j["confidence"])
        dims[label] = (rating, f"{rating} ({conf_bucket(conf)}, {conf:.2f})", conf)
    return {"overall": CODEX_OVERALL[raw], "dims": dims}


def load_comparison():
    tables = parse_md_tables(read(COMPARISON_MD))
    hdr, rows = next(t for t in tables if t[0] and t[0][0] == "ID")
    return hdr, rows


def load_corrections():
    data = yaml.safe_load(read(CORRECTIONS_YML)) or {}
    corrections = data.get("corrections") or []
    notes = data.get("notes") or []
    valid_pids = {cid.split("_")[0] for cid in MAPPING}
    for i, c in enumerate(corrections):
        for key in ("pid", "reader", "file_scope", "anchor", "note"):
            if not c.get(key):
                fail(f"corrections.yml entry {i + 1}: missing '{key}'")
        if c["pid"] not in valid_pids:
            fail(f"corrections.yml entry {i + 1}: unknown pid {c['pid']!r}")
        if c["reader"] not in ("claude", "codex"):
            fail(f"corrections.yml entry {i + 1}: reader must be claude or codex")
        for a in [c] + list(c.get("extra_anchors") or []) + list(c.get("pointers") or []):
            if a.get("file_scope") not in ("synthesis", "review", "both"):
                fail(f"corrections.yml entry {i + 1}: bad file_scope {a.get('file_scope')!r}")
        c.setdefault("date", "2026-09-25")
        c["date"] = str(c["date"])
    for i, n in enumerate(notes):
        if n.get("pid") not in valid_pids or not n.get("note"):
            fail(f"corrections.yml note {i + 1}: needs a valid pid and a note")
    return corrections, notes


# --------------------------------------------------------------------------
# Page builders
# --------------------------------------------------------------------------


def correction_specs(corrections, pid, reader, target):
    """Insertion specs for one generated copy: target is 'synthesis' or 'review'."""
    specs = []
    for n, c in enumerate(corrections):
        if c["pid"] != pid or c["reader"] != reader:
            continue
        block = [f"> **Correction ({c['date']}).** {' '.join(c['note'].split())}"]
        anchors = [(c["anchor"], c["file_scope"], c.get("allow_multiple"))]
        anchors += [(a["anchor"], a["file_scope"], a.get("allow_multiple")) for a in c.get("extra_anchors") or []]
        for anchor, scope, allow in anchors:
            if scope in (target, "both"):
                specs.append({"anchor": anchor, "block": block, "allow_multiple": allow,
                              "tag": f"entry{n + 1}:note", "entry": n})
        for p in c.get("pointers") or []:
            if p["file_scope"] in (target, "both"):
                specs.append({"anchor": p["anchor"], "block": [p["text"].strip()],
                              "allow_multiple": p.get("allow_multiple"),
                              "tag": f"entry{n + 1}:pointer", "entry": n})
    return specs


def render_body(lines, specs, label, counts_by_entry, target):
    lines = demote(lines)
    lines = ensure_block_spacing(lines)
    lines, counts = apply_insertions(lines, specs, label)
    for tag, k in counts.items():
        entry = int(tag.split(":")[0][5:]) - 1
        kind = tag.split(":")[1]
        counts_by_entry[entry][(target, kind)] += k
    lines = guard_rules(lines)
    lines = escape_dollars(lines)
    # trim leading/trailing blank lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def claude_banner(pid, rnd):
    if rnd == 2:
        return BANNER_CLAUDE_R2
    extra = BANNER_CLAUDE_R1_EXTRA.get(pid)
    return BANNER_CLAUDE_R1 + (" " + extra if extra else "")


def build_paper(p, corrections, notes, counts_by_entry):
    pid, sid = p["pid"], p["short_id"]
    out_dir = SITE / "papers" / sid
    claude_dir = CLAUDE_REVIEWS / p["claude_folder"]
    codex_dir = CODEX_REVIEWS / p["codex_id"]

    # --- syntheses for the tabs
    tabs = {}
    for reader, d in (("claude", claude_dir), ("codex", codex_dir)):
        _h1, lines = split_h1(read(d / "SYNTHESIS.md"))
        lines = strip_metadata(lines)
        specs = correction_specs(corrections, pid, reader, "synthesis")
        tabs[reader] = render_body(lines, specs, f"{sid} {reader} SYNTHESIS.md", counts_by_entry, "synthesis")

    # --- full reviews
    fulls = {}
    for reader, d in (("claude", claude_dir), ("codex", codex_dir)):
        _h1, lines = split_h1(read(d / "REVIEW.md"))
        specs = correction_specs(corrections, pid, reader, "review")
        fulls[reader] = render_body(lines, specs, f"{sid} {reader} REVIEW.md", counts_by_entry, "review")

    # --- paper page
    fm = OrderedDict([
        ("title", p["title"]),
        ("pid", pid),
        ("authors", p["authors"]),
        ("journal", p["journal"]),
        ("doi", p["doi"]),
        ("online", p["online"]),
        ("claude", p["claude_overall"]),
        ("codex", p["codex_overall"]),
        ("agree", p["agree"]),
        ("verified", p["verified"]),
        ("round", p["round"]),
        # `journal` is a reserved scholarly-metadata key that Quarto's schema expects to be
        # an object; the listing needs it as a plain string, so skip schema validation here.
        ("validate-yaml", False),
        # Quarto leaves tab headings out of the TOC, so it would list only "Responses".
        ("toc", False),
        ("body-classes", "paper-page"),
    ])
    paper_notes = [" ".join(n["note"].split()) for n in notes if n["pid"] == pid]
    callout = ["::: {.callout-note title=\"About these reviews\"}", claude_banner(pid, p["round"]), "", BANNER_CODEX]
    for n in paper_notes:
        callout += ["", f"**Note.** {n}"]
    callout.append(":::")

    rows = ["| | Claude | Codex |", "|---|---|---|",
            f"| **Overall** | {p['claude_overall_full']} | {p['codex_overall']} |"]
    for label, *_ in DIMENSIONS:
        rows.append(f"| {label} | {p['claude_dims'][label][1]} | {p['codex_dims'][label][1]} |")

    body = [
        front_matter(fm),
        "",
        GENERATED_NOTICE,
        "",
        f"**Authors:** {p['authors']}  ",
        f"**Journal:** {p['journal_full']}, {p['online'][:4]}  ",
        f"**DOI:** [{p['doi']}](https://doi.org/{p['doi']})  ",
        f"**Published online:** {p['online']}  ",
        f"**Reviewed:** Claude {p['claude_review_date']}; Codex {p['codex_review_date']}",
        "",
        *callout,
        "",
        *rows,
        "",
        ": Overall rating and the five sub-review ratings, with confidence in parentheses "
        "(for Codex, the label and the sub-review's own 0 to 1 score).",
        "",
        "- [Full Claude review (synthesis + five sub-reviews)](claude.qmd)",
        "- [Full Codex review](codex.qmd)",
        "",
        "::: {.panel-tabset}",
        "",
        "## Claude synthesis",
        "",
        tabs["claude"],
        "",
        "## Codex synthesis",
        "",
        tabs["codex"],
        "",
        ":::",
        "",
        "## Responses",
        "",
        RESPONSES_TEXT,
        "",
        GISCUS_PLACEHOLDER,
    ]
    write(out_dir / "index.qmd", "\n".join(body))

    for reader, banner, name in (("claude", claude_banner(pid, p["round"]), "Claude"),
                                 ("codex", BANNER_CODEX, "Codex")):
        fm = OrderedDict([("title", f"{name} review: {p['title']}"), ("pid", pid), ("toc", True)])
        page = [
            front_matter(fm),
            "",
            GENERATED_NOTICE,
            "",
            "[← Back to the paper page](index.qmd)",
            "",
            "::: {.callout-note title=\"About this review\"}",
            banner,
            ":::",
            "",
            fulls[reader],
        ]
        write(out_dir / f"{reader}.qmd", "\n".join(page))


def build_corrections_page(corrections, notes, papers_by_pid):
    lines = [
        front_matter(OrderedDict([("title", "Corrections")])),
        "",
        GENERATED_NOTICE,
        "",
        CORRECTIONS_INTRO,
        "",
        "| Date | Paper | Reader | Where | What was wrong | Correction |",
        "|----------|------------------|-------|--------------------|-------------------------|------------------------------|",
    ]

    def cell(s):
        return " ".join(str(s or "").split()).replace("|", "\\|")

    for c in corrections:
        p = papers_by_pid[c["pid"]]
        page = "claude.qmd" if c["reader"] == "claude" else "codex.qmd"
        paper = f"[{p['authors']}](papers/{p['short_id']}/index.qmd) ({p['journal']})"
        reader = f"[{c['reader'].capitalize()}](papers/{p['short_id']}/{page})"
        lines.append(f"| {c['date']} | {cell(paper)} | {reader} | {cell(c.get('where'))} | "
                     f"{cell(c.get('what_was_wrong'))} | {cell(c.get('correction'))} |")
    lines += ["", "## Per-paper notes", ""]
    for n in notes:
        p = papers_by_pid[n["pid"]]
        lines.append(f"- [{p['authors']}](papers/{p['short_id']}/index.qmd) ({p['journal']}): "
                     f"{' '.join(n['note'].split())}")
    lines += ["", CORRECTIONS_OUTRO]
    lines = escape_dollars(lines)
    write(SITE / "corrections.qmd", "\n".join(lines))


def build_prompts_include():
    (SITE / "prompts").mkdir(exist_ok=True)
    parts = [GENERATED_NOTICE, ""]
    for stem, title in PROMPTS:
        src = CLAUDE_PROMPTS / f"{stem}.md"
        text = read(src)
        shutil.copyfile(src, SITE / "prompts" / f"{stem}.md")
        longest = max([len(m) for m in re.findall(r"`+", text)] + [0])
        fence = "`" * max(4, longest + 1)
        parts += [
            f"### {title}",
            "",
            f"Source file: [`prompts/{stem}.md`](prompts/{stem}.md)",
            "",
            f"{fence} {{.markdown}}",
            text.rstrip("\n"),
            fence,
            "",
        ]
    write(SITE / "_includes/prompts.qmd", "\n".join(parts))


def build_comparison_include(papers_by_codex_id):
    hdr, rows = load_comparison()
    out = [GENERATED_NOTICE, "",
           "Key to the Weak columns: M methods, L literature, W writing, C contribution, "
           "R reproducibility; – none.", "",
           "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for r in rows:
        cid = r[0]
        if cid not in papers_by_codex_id:
            fail(f"COMPARISON_ratings.md: unknown ID {cid}")
        p = papers_by_codex_id[cid]
        out.append("| " + " | ".join([f"[{cid}](papers/{p['short_id']}/index.qmd)"] + r[1:]) + " |")
    write(SITE / "_includes/comparison_table.qmd", "\n".join(out))
    return hdr, rows


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main():
    for path in (CLAUDE_REVIEWS, CODEX_REVIEWS, MANIFEST_MD, COMPARISON_MD, RESULTS_R1, RESULTS_R2, CLAUDE_PROMPTS):
        if not Path(path).exists():
            fail(f"source not found: {path}")

    manifest = load_manifest()
    claude_results = load_claude_results()
    corrections, notes = load_corrections()

    papers = []
    for codex_id, folder in MAPPING.items():
        if codex_id not in manifest:
            fail(f"{codex_id} missing from MANIFEST.md")
        if folder not in claude_results:
            fail(f"{folder} missing from the Claude RESULTS tables")
        for req in (CLAUDE_REVIEWS / folder / "SYNTHESIS.md", CLAUDE_REVIEWS / folder / "REVIEW.md",
                    CODEX_REVIEWS / codex_id / "SYNTHESIS.md", CODEX_REVIEWS / codex_id / "REVIEW.md"):
            if not req.exists():
                fail(f"missing source file {req}")
        rnd = ROUND_BY_PREFIX[folder[:8]]
        cr = claude_results[folder]
        if cr["results_round"] != rnd:
            fail(f"{codex_id}: folder prefix says round {rnd} but it is listed in round {cr['results_round']} RESULTS")
        cx = load_codex(codex_id)
        diff = SEVERITY[cx["overall"]] - SEVERITY[cr["overall"]]
        agree = "Same" if diff == 0 else ("Codex harsher" if diff < 0 else "Codex softer")
        m = manifest[codex_id]
        papers.append({
            "pid": codex_id.split("_")[0],
            "short_id": short_pid(codex_id),
            "codex_id": codex_id,
            "claude_folder": folder,
            "round": rnd,
            "verified": "Page-verified" if rnd == 2 else "Not page-verified",
            "claude_review_date": CLAUDE_REVIEW_DATE[rnd],
            "codex_review_date": CODEX_REVIEW_DATE,
            **m,
            "claude_overall": cr["overall"],
            "claude_overall_full": cr["overall_full"],
            "claude_dims": cr["dims"],
            "codex_overall": cx["overall"],
            "codex_dims": cx["dims"],
            "agree": agree,
        })
    if len(set(claude_results)) != 33:
        fail(f"expected 33 rows across the RESULTS tables, found {len(claude_results)}")

    papers_by_pid = {p["pid"]: p for p in papers}
    papers_by_codex_id = {p["codex_id"]: p for p in papers}

    # --- cross-check against COMPARISON_ratings.md
    hdr, rows = load_comparison()
    mismatches = []
    for r in rows:
        d = dict(zip(hdr, r))
        p = papers_by_codex_id[d["ID"]]
        if d["Codex overall"] != p["codex_overall"]:
            mismatches.append(f"{d['ID']}: Codex overall {d['Codex overall']!r} vs JSON {p['codex_overall']!r}")
        if d["Claude overall"] != p["claude_overall"]:
            mismatches.append(f"{d['ID']}: Claude overall {d['Claude overall']!r} vs RESULTS {p['claude_overall']!r}")
        rel = {"=": "Same", "harsher": "Codex harsher", "softer": "Codex softer"}[d["Rel"]]
        if rel != p["agree"]:
            mismatches.append(f"{d['ID']}: Rel {d['Rel']!r} vs computed {p['agree']!r}")
        agree_n = sum(p["claude_dims"][lab][0] == p["codex_dims"][lab][0] for lab, *_ in DIMENSIONS)
        if d["Dims agree"] != f"{agree_n}/5":
            mismatches.append(f"{d['ID']}: Dims agree {d['Dims agree']!r} vs computed {agree_n}/5")
        for who, key in (("codex", "Codex Weak"), ("claude", "Claude Weak")):
            weak = "".join(code for lab, _c, _s, code in DIMENSIONS if p[f"{who}_dims"][lab][0] == "Weak") or "–"
            if d[key] != weak:
                mismatches.append(f"{d['ID']}: {key} {d[key]!r} vs computed {weak!r}")
    if len(rows) != 33:
        mismatches.append(f"COMPARISON_ratings.md has {len(rows)} rows, expected 33")
    if mismatches:
        fail("COMPARISON_ratings.md disagrees with the source ratings:\n  " + "\n  ".join(mismatches))

    # --- clean generated outputs, then write
    papers_root = SITE / "papers"
    if papers_root.exists():
        shutil.rmtree(papers_root)
    counts_by_entry = [Counter() for _ in corrections]
    for p in papers:
        build_paper(p, corrections, notes, counts_by_entry)
    build_corrections_page(corrections, notes, papers_by_pid)
    build_prompts_include()
    build_comparison_include(papers_by_codex_id)

    # every correction must have landed in every copy its scope names
    for n, c in enumerate(corrections):
        need = {"synthesis", "review"} if c["file_scope"] == "both" else {c["file_scope"]}
        got = {t for (t, kind), k in counts_by_entry[n].items() if kind == "note" and k > 0}
        if not need <= got:
            fail(f"correction {n + 1} ({c['pid']} {c['reader']}): note missing from {sorted(need - got)}")

    # --- manifest.csv
    fields = ["pid", "short_id", "codex_id", "claude_folder", "round", "journal", "journal_full", "authors",
              "title", "doi", "online", "claude_review_date", "codex_review_date", "verified",
              "claude_overall", "claude_overall_full", "codex_overall", "agree"]
    for lab, *_ in DIMENSIONS:
        fields += [f"claude_{lab.lower()}", f"codex_{lab.lower()}", f"codex_{lab.lower()}_confidence"]
    fields += ["corrections", "notes"]
    with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in papers:
            row = {k: p[k] for k in fields[:18]}
            for lab, *_ in DIMENSIONS:
                row[f"claude_{lab.lower()}"] = p["claude_dims"][lab][1]
                row[f"codex_{lab.lower()}"] = p["codex_dims"][lab][0]
                row[f"codex_{lab.lower()}_confidence"] = f"{p['codex_dims'][lab][2]:.2f}"
            row["corrections"] = sum(1 for c in corrections if c["pid"] == p["pid"])
            row["notes"] = sum(1 for n in notes if n["pid"] == p["pid"])
            w.writerow(row)

    # --- summary
    n_index = len(list(papers_root.glob("*/index.qmd")))
    n_claude = len(list(papers_root.glob("*/claude.qmd")))
    n_codex = len(list(papers_root.glob("*/codex.qmd")))
    print("Build summary")
    print(f"  papers:        {len(papers)}")
    print(f"  index pages:   {n_index}")
    print(f"  claude pages:  {n_claude}")
    print(f"  codex pages:   {n_codex}")
    print(f"  Claude overall: {dict(Counter(p['claude_overall'] for p in papers))}")
    print(f"  Codex overall:  {dict(Counter(p['codex_overall'] for p in papers))}")
    print(f"  agree:          {dict(Counter(p['agree'] for p in papers))}")
    print(f"  verified:       {dict(Counter(p['verified'] for p in papers))}")
    print("  corrections inserted (per entry; tab = synthesis tab on the paper page, full = full-review page):")
    for n, c in enumerate(corrections):
        cnt = counts_by_entry[n]
        print(f"    {n + 1}. {c['pid']} {c['reader']}: notes tab={cnt[('synthesis', 'note')]} "
              f"full={cnt[('review', 'note')]}; pointers tab={cnt[('synthesis', 'pointer')]} "
              f"full={cnt[('review', 'pointer')]}")
    print(f"  per-paper notes: {len(notes)} ({', '.join(n['pid'] for n in notes)})")
    print(f"  blank lines added before blocks for Pandoc: {dict(BLOCK_SPACING_STATS)}")
    print("  COMPARISON_ratings.md cross-check: OK (33 rows)")
    print(f"  manifest.csv written: {MANIFEST_CSV.relative_to(SITE)} ({len(papers)} rows)")
    if n_index != 33 or n_claude != 33 or n_codex != 33 or len(papers) != 33:
        fail("expected 33 papers and 33 pages of each kind")


if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
