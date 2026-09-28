# Reader's Guides: AI reviews of 33 education research papers

This repository builds a static Quarto website that publishes AI-generated retrospective reviews of 33 recent quantitative articles from four AERA journals. Every paper has two independent review sets, one from a Claude pipeline and one from a Codex (OpenAI GPT-6) pipeline, shown side by side with dated corrections applied at build time.

**No paper PDFs, extracted paper text or page images are in this repository, and none may ever be added.** Each paper page links to the article's DOI instead. `.gitignore` blocks the common file types, `build/check_no_paper_content.py` fails on them, and the publish workflow runs that check before and after rendering.

## Layout

| Path | What it is | Edit by hand? |
|---|---|---|
| `index.qmd` | Landing page: intro text and the listing table of papers | Yes |
| `methods.qmd` | Selection rule, pipelines, human checks; includes the prompts | Yes |
| `comparison.qmd` | Short text; includes the ratings comparison table | Yes |
| `styles.css`, `_quarto.yml` | Site styling and configuration | Yes |
| `build/corrections.yml` | Correction notes and per-paper notes | Yes |
| `build/build_site.py` | The generator (fixed banner and page text lives at its top) | Yes |
| `papers/<PID>/index.qmd`, `claude.qmd`, `codex.qmd` | Paper page and the two full reviews | No, generated |
| `corrections.qmd` | Corrections log | No, generated |
| `_includes/prompts.qmd`, `_includes/comparison_table.qmd` | Partials included by the Methods and Comparison pages | No, generated |
| `prompts/*.md` | Copies of the six prompts (also served as raw files) | No, copied |
| `build/manifest.csv` | One row per paper: metadata and both readers' ratings | No, generated |
| `build/export_data.py` | Writes `data/` from the essay's mistakes ledger and overreach census; drops every column holding paper text or notes and fails on any cell over 40 characters or with a quotation mark | Yes |
| `data/*.csv` | Quote-free code-only data behind the Mistakes audit and Overreach census pages: `mistakes_ledger.csv`, `overreach_claims.csv`, `paper_summary.csv` (copied into `_site/data/`) | No, generated |

Generated pages are committed, so the GitHub Actions workflow only has to run `quarto render`. It never needs the review archives.

## Rebuilding

The generator reads two local, read-only review archives (it never writes to them):

- Claude pipeline: `ai_paper_reviewer/reviews/` (plus the ratings tables in `landscape_aera_quant_202609/RESULTS*.md` and the prompts in `ai_paper_reviewer/prompts/reader/`)
- Codex pipeline: `second-reader/reviews/`, `second-reader/papers/MANIFEST.md`, `second-reader/COMPARISON_ratings.md`

Both default to paths under `/Users/yvp3tf/Documents/CC Sandbox/`; override with the environment variables `CLAUDE_REVIEWS`, `CODEX_ROOT` and `CLAUDE_PROMPTS`. It needs Python 3 and PyYAML.

```sh
python3 build/build_site.py          # regenerate papers/, corrections.qmd, _includes/, prompts/, build/manifest.csv
python3 build/check_no_paper_content.py
quarto render                        # writes _site/
quarto preview                       # optional: local preview with live reload
```

The generator fails loudly if a source file is missing, if `COMPARISON_ratings.md` disagrees with the ratings it reads from the source files, or if a correction anchor cannot be found. On success it prints the page counts, rating counts and how many correction notes it inserted per entry.

## Adding a correction

1. Add an entry under `corrections:` in `build/corrections.yml`: `pid` (e.g. `P07`), `reader` (`claude` or `codex`), `date`, `file_scope` (`synthesis` = the synthesis tab on the paper page, `review` = the full-review page, `both`), `anchor` (an exact substring of the sentence being corrected) and `note`. Add `where`, `what_was_wrong` and `correction` for the table on the Corrections page. Optional `extra_anchors` and `pointers` handle claims repeated elsewhere; the file's header comment explains them.
2. Run `python3 build/build_site.py`. The note is inserted as a dated blockquote directly after the paragraph or list item containing the anchor; the original text stays in place. The build stops if the anchor is missing, or matches more than once in a file (make the anchor longer until it is unique, or set `allow_multiple: true`).
3. Run `quarto render`, check the page, commit and push.

Per-paper notes (shown in the callout at the top of a paper page and on the Corrections page) go under `notes:` in the same file.

## Publishing (repository owner)

Nothing has been pushed; this is a local repository with no remote.

1. Create an empty **public** repository on GitHub (no README, license or .gitignore, so the first push is clean).
2. `git remote add origin https://github.com/OWNER/REPO.git`
3. `git push -u origin main`
4. In the repository, go to **Settings → Pages → Build and deployment** and set **Source** to **GitHub Actions**. The `Publish site` workflow (`.github/workflows/publish.yml`) runs on every push to `main`; re-run it from the Actions tab if the first run happened before this setting was changed. The site appears at `https://OWNER.github.io/REPO/`.
5. Optional custom domain: add a file named `CNAME` containing the domain (e.g. `reviews.example.org`), list it under `resources:` in `_quarto.yml` so it is copied into `_site/`, set the same domain under Settings → Pages → Custom domain, and point the domain's DNS at GitHub Pages.

After the site is live, set `site-url` in `_quarto.yml`. To turn on discussion threads, enable Discussions on the repository, install the giscus app, and fill in and uncomment the `comments: giscus:` block in `_quarto.yml` with the IDs from https://giscus.app.

## License

Site content is licensed CC BY 4.0; see `LICENSE`. The build scripts under `build/` are MIT-licensed; see `LICENSE-CODE`. The reviewed articles are not included and are not covered by either license.
