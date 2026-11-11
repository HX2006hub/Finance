#!/usr/bin/env python3
"""
Turn a GitHub issue (created from .github/ISSUE_TEMPLATE/article-brief.yml)
into a structured brief JSON for the generator.

Issue Forms render as markdown like:

    ### 主题 *

    2026 年 AI 编程助手为什么开始按 token 计费

    ### 分类 *

    ai-tools

Usage:
    python3 tools/issue_to_brief.py /tmp/issue.md --issue 12 --out content/briefs/issue-12.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FIELD_MAP = {
    "主题": "topic",
    "分类": "category",
    "目标读者": "audience",
    "核心观点": "points",
    "我的判断": "my_take",
    "可引用来源": "sources",
    "目标关键词": "keywords",
}

VALID_CATEGORIES = {"technology", "finance", "ai-tools", "health-lifestyle"}
YMYL = {"finance", "health-lifestyle"}


def parse_sections(md: str) -> dict[str, str]:
    """Split issue body on '### <label>' headings."""
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in md.splitlines():
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            label = re.sub(r"\s*\*+\s*$", "", m.group(1)).strip()
            current, buf = label, []
        elif current is not None:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def split_points(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if s and s != "_No response_":
            out.append(s)
    return out


def split_urls(text: str) -> list[str]:
    return [u.strip().rstrip(">").strip() for u in re.findall(r"https?://[^\s)>\]]+", text)]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "article"


def build_brief(md: str, issue: str | None) -> dict:
    sections = {}
    for label, value in parse_sections(md).items():
        key = FIELD_MAP.get(label)
        if key:
            sections[key] = value

    category = (sections.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "technology"

    points = split_points(sections.get("points", ""))
    brief = {
        "topic": sections.get("topic", "").strip(),
        "category": category,
        "audience": sections.get("audience", "").strip(),
        "points": points,
        "my_take": sections.get("my_take", "").strip(),
        "sources": split_urls(sections.get("sources", "")),
        "internal_links": [],
        "keywords": [k.strip() for k in re.split(r"[,，]", sections.get("keywords", "")) if k.strip()],
        "slug": slugify(sections.get("topic", "")) + (f"-{issue}" if issue else ""),
        "issue": issue,
        "ymyl": category in YMYL,
    }
    return brief


def validate(brief: dict) -> list[str]:
    problems = []
    if len(brief["topic"]) < 8:
        problems.append("主题太短或为空")
    if len(brief["points"]) < 2:
        problems.append("核心观点少于 2 条")
    if len(brief["my_take"]) < 10:
        problems.append("『我的判断』为空或过短（这是原创性的来源，必须写）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("issue_file")
    ap.add_argument("--issue", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    md = Path(args.issue_file).read_text(encoding="utf-8")
    brief = build_brief(md, args.issue)

    problems = validate(brief)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    if problems:
        print("BRIEF_INVALID: " + "；".join(problems), file=sys.stderr)
        return 2

    print(f"brief ok: {out} · {brief['category']} · {len(brief['points'])} 条观点")
    return 0


if __name__ == "__main__":
    sys.exit(main())
