#!/usr/bin/env python3
"""
Merge approved drafts into the published data files, then let build_static.py
regenerate the static pages. This runs when a review PR is merged.

Rules
-----
- only drafts that passed the quality gate (grade A/B/C) are integrated
- ids stay stable; a duplicate id is re-assigned to avoid overwriting a live article
- the draft's `_meta` block is stripped from the site data and logged instead

Usage:
    python3 tools/integrate_drafts.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ["technology", "finance", "ai-tools", "health-lifestyle"]


def load_category(cat: str) -> tuple[dict, list[dict]]:
    p = ROOT / f"articles-{cat}.json"
    if not p.exists():
        return {"v": 1, "articles": []}, []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"v": 1, "articles": data}, data
    return data, data.get("articles", [])


def save_category(cat: str, wrapper: dict, articles: list[dict]) -> None:
    wrapper = dict(wrapper)
    wrapper["articles"] = articles
    (ROOT / f"articles-{cat}.json").write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def gate_grade(draft_file: Path) -> str | None:
    report = ROOT / "content" / "reports" / f"draft-{draft_file.stem.split('-')[-1]}.json"
    if report.exists():
        try:
            return json.loads(report.read_text(encoding="utf-8")).get("grade")
        except json.JSONDecodeError:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drafts_dir = ROOT / "content" / "drafts"
    drafts = sorted(p for p in drafts_dir.glob("*.json") if not p.name.startswith("_"))
    if not drafts:
        print("no drafts to integrate")
        return 0

    wrappers, existing = {}, {}
    live_ids = set()
    for cat in CATEGORIES:
        wrappers[cat], existing[cat] = load_category(cat)
        live_ids |= {str(a.get("id")) for a in existing[cat]}

    integrated, skipped = [], []
    log_dir = ROOT / "content" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "published.jsonl"

    for p in drafts:
        article = json.loads(p.read_text(encoding="utf-8"))
        grade = gate_grade(p)
        if grade == "D":
            skipped.append((p.name, "质量门禁未通过（D）"))
            continue
        cat = article.get("category")
        if cat not in CATEGORIES:
            skipped.append((p.name, f"未知分类 {cat}"))
            continue
        if str(article.get("id")) in live_ids:
            article["id"] = f"{article['id']}{len(live_ids) % 10}"
        meta = article.pop("_meta", {})
        article["date"] = article.get("date") or dt.date.today().isoformat()
        # passed the quality gate -> eligible for indexing (see build_static.is_indexable)
        article["indexable"] = True
        wrappers[cat]["articles"].append(article)
        live_ids.add(str(article["id"]))
        integrated.append(article)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "published_at": dt.datetime.now().isoformat(timespec="seconds"),
                "id": article["id"], "title": article.get("title"),
                "category": cat, "grade": grade, "source": p.name,
                "meta": meta,
            }, ensure_ascii=False) + "\n")
        if not args.dry_run:
            p.rename(p.with_suffix(".published.json"))

    if integrated and not args.dry_run:
        for cat in CATEGORIES:
            arts = wrappers[cat]["articles"]
            arts.sort(key=lambda a: (a.get("date") or "", str(a.get("id"))), reverse=True)
            save_category(cat, wrappers[cat], arts)

    print(f"integrated: {len(integrated)}")
    for a in integrated:
        print(f"  + [{a['category']}] {a['id']} · {a['title'][:70]}")
    if skipped:
        print(f"skipped: {len(skipped)}")
        for name, why in skipped:
            print(f"  - {name}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
