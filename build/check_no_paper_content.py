#!/usr/bin/env python3
"""Fail if any paper PDF, extracted paper text or image file is in the repository.

The site publishes reviews only. The papers themselves (PDFs, extracted text)
and any page renders or figure images must never be committed.

Checks every file git would commit (tracked plus untracked-but-not-ignored).
Outside a git checkout it walks the tree, skipping .git, _site and .quarto.
With --site it also checks the rendered _site/ directory.

Exit status 0 = clean, 1 = forbidden files found.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_EXT = {
    ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".heic",
}
FORBIDDEN_NAME = [
    re.compile(r"^paper_text\.txt$", re.I),        # Claude pipeline extracted text
    re.compile(r"^P\d{2}_.*\.txt$", re.I),          # Codex pipeline extracted text (P05_AERAOpen_britton.txt)
    re.compile(r".*corrigendum.*\.(pdf|txt)$", re.I),
]
SKIP_DIRS = {".git", "_site", ".quarto"}


def repo_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8")
        return [ROOT / p for p in out.split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [Path(dirpath) / f for f in filenames]
        return files


def site_files():
    site = ROOT / "_site"
    if not site.is_dir():
        return []
    return [p for p in site.rglob("*") if p.is_file()]


def forbidden(path):
    name = path.name
    if path.suffix.lower() in FORBIDDEN_EXT:
        return True
    return any(rx.match(name) for rx in FORBIDDEN_NAME)


def main():
    files = repo_files()
    if "--site" in sys.argv[1:]:
        files += site_files()
    bad = sorted({str(p.relative_to(ROOT)) for p in files if p.exists() and forbidden(p)})
    if bad:
        print("FAIL: paper content or image files found (these must never be committed or published):")
        for b in bad:
            print(f"  {b}")
        sys.exit(1)
    print(f"OK: checked {len(files)} files; no PDFs, extracted paper text or images.")


if __name__ == "__main__":
    main()
