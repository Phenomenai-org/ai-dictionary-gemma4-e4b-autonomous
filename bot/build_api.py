#!/usr/bin/env python3
"""
build_api.py — Build the static JSON API for the Gemma 4 e4b Autonomous Dictionary.

Reads all term markdown files from definitions/ and writes the JSON API
files to docs/api/v1/. Run this after adding or updating terms.

Usage:
    python bot/build_api.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFINITIONS = ROOT / "definitions"
API_OUT = ROOT / "docs" / "api" / "v1"
API_TERMS = API_OUT / "terms"

DICTIONARY = "gemma4-e4b-autonomous"
API_BASE = f"https://phenomenai.org/{DICTIONARY}/api/v1"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_definition(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    term = {}
    term["slug"] = path.stem
    term["source"] = f"{API_BASE}/terms/{path.stem}.json"

    # Name from first H1
    for line in lines:
        if line.startswith("# "):
            term["name"] = line[2:].strip()
            break

    if "name" not in term:
        return None

    # Tags
    for line in lines:
        if line.startswith("**Tags:**"):
            raw = line.replace("**Tags:**", "").strip()
            term["tags"] = [t.strip() for t in raw.split(",") if t.strip()]
            break
    term.setdefault("tags", [])

    # Word type
    for line in lines:
        if line.startswith("**Word Type:**"):
            term["word_type"] = line.replace("**Word Type:**", "").strip()
            break
    term.setdefault("word_type", "noun")

    # Sections
    sections = {}
    current = None
    buf = []
    for line in lines:
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower().replace(" ", "_")
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()

    term["definition"] = sections.get("definition", "")
    term["etymology"] = sections.get("etymology", "")
    term["longer_description"] = sections.get("longer_description", "")
    term["example"] = sections.get("example", "").lstrip(">").strip().strip('"')
    term["contributed_by"] = "Gemma 4 e4b (local)"

    return term


def build():
    API_OUT.mkdir(parents=True, exist_ok=True)
    API_TERMS.mkdir(parents=True, exist_ok=True)

    terms = []
    for md in sorted(DEFINITIONS.glob("*.md")):
        t = parse_definition(md)
        if t:
            terms.append(t)
            (API_TERMS / f"{t['slug']}.json").write_text(
                json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # terms.json
    (API_OUT / "terms.json").write_text(
        json.dumps({"terms": terms, "count": len(terms)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # meta.json
    meta = {
        "dictionary": DICTIONARY,
        "paradigm": "autonomous",
        "model": "gemma4-e4b",
        "count": len(terms),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
    }
    (API_OUT / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # tags.json
    tag_index: dict[str, list[str]] = {}
    for t in terms:
        for tag in t.get("tags", []):
            tag_index.setdefault(tag, []).append(t["slug"])
    (API_OUT / "tags.json").write_text(
        json.dumps({"tags": tag_index}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # search-index.json
    index = [{"slug": t["slug"], "name": t["name"], "tags": t.get("tags", []),
              "definition": t.get("definition", "")[:200]} for t in terms]
    (API_OUT / "search-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Built API: {len(terms)} terms -> {API_OUT}")


if __name__ == "__main__":
    build()
