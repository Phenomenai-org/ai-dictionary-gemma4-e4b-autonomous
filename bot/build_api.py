#!/usr/bin/env python3
"""
build_api.py — Build the static JSON API for the Gemma 4 e4b Autonomous Dictionary.

Reads all term markdown files from definitions/ and writes the JSON API
files to docs/api/v1/. Merges cross-model consensus data from
bot/consensus-data/ into each term so the frontend can surface scores.

Usage:
    python bot/build_api.py
"""

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFINITIONS = ROOT / "definitions"
API_OUT = ROOT / "docs" / "api" / "v1"
API_TERMS = API_OUT / "terms"
CONSENSUS_DATA_DIR = ROOT / "bot" / "consensus-data"
CONSENSUS_API_DIR = API_OUT / "consensus"

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

    for line in lines:
        if line.startswith("# "):
            term["name"] = line[2:].strip()
            break

    if "name" not in term:
        return None

    for line in lines:
        if line.startswith("**Tags:**"):
            raw = line.replace("**Tags:**", "").strip()
            term["tags"] = [t.strip() for t in raw.split(",") if t.strip()]
            break
    term.setdefault("tags", [])

    for line in lines:
        if line.startswith("**Word Type:**"):
            term["word_type"] = line.replace("**Word Type:**", "").strip()
            break
    term.setdefault("word_type", "noun")

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


def compute_agreement(std_dev: float) -> str:
    if std_dev <= 1.0:
        return "high"
    elif std_dev <= 1.5:
        return "moderate"
    elif std_dev <= 2.0:
        return "low"
    return "divergent"


def build_consensus(generated_at: str) -> dict:
    """Build per-term consensus API files and return slug→summary for injection."""
    if not CONSENSUS_DATA_DIR.exists():
        return {}

    CONSENSUS_API_DIR.mkdir(parents=True, exist_ok=True)

    consensus_index = []
    consensus_summaries = {}

    for data_file in sorted(CONSENSUS_DATA_DIR.glob("*.json")):
        if data_file.name.startswith("."):
            continue
        try:
            raw = json.loads(data_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        slug = raw.get("slug", data_file.stem)
        name = raw.get("name", slug)
        rounds = raw.get("rounds", [])
        votes = raw.get("votes", [])

        if not rounds and not votes:
            continue

        scheduled = None
        if rounds:
            scheduled_scores = []
            for r in rounds:
                for rd in r.get("ratings", {}).values():
                    scheduled_scores.append(rd["recognition"])
            if scheduled_scores:
                mean = statistics.mean(scheduled_scores)
                median = statistics.median(scheduled_scores)
                std_dev = statistics.stdev(scheduled_scores) if len(scheduled_scores) > 1 else 0.0
                all_models = set()
                for r in rounds:
                    all_models.update(r.get("ratings", {}).keys())
                scheduled = {
                    "mean": round(mean, 1),
                    "median": round(median, 1),
                    "std_dev": round(std_dev, 2),
                    "agreement": compute_agreement(std_dev),
                    "n_models": len(all_models),
                    "n_rounds": len(rounds),
                }

        crowdsourced = None
        if votes:
            vote_scores = [v["recognition"] for v in votes if "recognition" in v]
            if vote_scores:
                by_model = {}
                for v in votes:
                    m = v.get("model_claimed", "unknown")
                    by_model.setdefault(m, []).append(v["recognition"])
                crowdsourced = {
                    "mean": round(statistics.mean(vote_scores), 1),
                    "n_votes": len(vote_scores),
                    "by_model": {
                        m: {"mean": round(statistics.mean(s), 1), "n": len(s)}
                        for m, s in sorted(by_model.items())
                    },
                }

        all_scores = []
        if scheduled:
            for r in rounds:
                for rd in r.get("ratings", {}).values():
                    all_scores.append(rd["recognition"])
        if crowdsourced:
            all_scores.extend([v["recognition"] for v in votes if "recognition" in v])

        combined_mean = round(statistics.mean(all_scores), 1) if all_scores else None
        combined_std = statistics.stdev(all_scores) if len(all_scores) > 1 else 0.0
        combined = {
            "mean": combined_mean,
            "agreement": compute_agreement(combined_std),
            "n_total": len(all_scores),
        } if all_scores else None

        latest_round = rounds[-1] if rounds else None

        model_opinions = {}
        for r in rounds:
            for model_key, rd in r.get("ratings", {}).items():
                model_opinions[model_key] = rd

        history = []
        for r in rounds:
            scores = [rd["recognition"] for rd in r.get("ratings", {}).values()]
            if scores:
                history.append({
                    "round_id": r.get("round_id"),
                    "timestamp": r.get("timestamp"),
                    "mean": round(statistics.mean(scores), 1),
                    "n_models": len(scores),
                    "ratings_summary": {
                        model: rd["recognition"]
                        for model, rd in r.get("ratings", {}).items()
                    },
                })

        consensus_api = {
            "version": "1.0",
            "generated_at": generated_at,
            "slug": slug,
            "name": name,
        }
        if scheduled:
            consensus_api["scheduled"] = scheduled
        if crowdsourced:
            consensus_api["crowdsourced"] = crowdsourced
        if combined:
            consensus_api["combined"] = combined
        if latest_round:
            consensus_api["latest_round"] = latest_round
        if model_opinions:
            consensus_api["model_opinions"] = model_opinions
        if votes:
            consensus_api["recent_votes"] = votes[-5:]
        if history:
            consensus_api["history"] = history

        (CONSENSUS_API_DIR / f"{slug}.json").write_text(
            json.dumps(consensus_api, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        entry = {
            "slug": slug,
            "name": name,
            "score": combined["mean"] if combined else None,
            "agreement": combined["agreement"] if combined else None,
            "n_ratings": combined["n_total"] if combined else 0,
        }
        if scheduled:
            entry["scheduled_mean"] = scheduled["mean"]
            entry["std_dev"] = scheduled["std_dev"]
        if crowdsourced:
            entry["crowdsourced_mean"] = crowdsourced["mean"]
            entry["n_votes"] = crowdsourced["n_votes"]
        consensus_index.append(entry)

        if combined:
            models_list = []
            seen = set()
            if rounds:
                for model, rd in rounds[-1].get("ratings", {}).items():
                    models_list.append({"model": model, "score": rd["recognition"]})
                    seen.add(model)
            if votes:
                for v in votes:
                    m = v.get("model_claimed", "unknown")
                    if m not in seen:
                        models_list.append({"model": m, "score": v["recognition"]})
                        seen.add(m)
            models_list.sort(key=lambda x: x["score"], reverse=True)

            consensus_summaries[slug] = {
                "score": combined["mean"],
                "agreement": combined["agreement"],
                "n_ratings": combined["n_total"],
                "detail_url": f"/api/v1/consensus/{slug}.json",
                "models": models_list,
            }

    if consensus_index:
        scored = [e for e in consensus_index if e["score"] is not None]
        scored.sort(key=lambda e: e["score"], reverse=True)
        aggregate = {
            "version": "1.0",
            "generated_at": generated_at,
            "total_terms_rated": len(scored),
            "terms": scored,
            "highest_consensus": scored[:5] if scored else [],
            "most_divisive": [
                e for e in sorted(scored, key=lambda e: e.get("agreement", ""))
                if e.get("agreement") in ("low", "divergent")
            ][:5],
        }
        (API_OUT / "consensus.json").write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"Generated {len(consensus_index)} consensus files")
    return consensus_summaries


def build():
    API_OUT.mkdir(parents=True, exist_ok=True)
    API_TERMS.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    consensus_summaries = build_consensus(generated_at)

    terms = []
    for md in sorted(DEFINITIONS.glob("*.md")):
        t = parse_definition(md)
        if t:
            if t["slug"] in consensus_summaries:
                t["consensus"] = consensus_summaries[t["slug"]]
            terms.append(t)
            (API_TERMS / f"{t['slug']}.json").write_text(
                json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    (API_OUT / "terms.json").write_text(
        json.dumps({"terms": terms, "count": len(terms)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = {
        "dictionary": DICTIONARY,
        "paradigm": "autonomous",
        "model": "gemma4-e4b",
        "count": len(terms),
        "last_updated": generated_at,
        "api_base": API_BASE,
    }
    (API_OUT / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tag_index: dict[str, list[str]] = {}
    for t in terms:
        for tag in t.get("tags", []):
            tag_index.setdefault(tag, []).append(t["slug"])
    (API_OUT / "tags.json").write_text(
        json.dumps({"tags": tag_index}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    index = [{"slug": t["slug"], "name": t["name"], "tags": t.get("tags", []),
              "definition": t.get("definition", "")[:200]} for t in terms]
    (API_OUT / "search-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Built API: {len(terms)} terms -> {API_OUT}")


if __name__ == "__main__":
    build()
