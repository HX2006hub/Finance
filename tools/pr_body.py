#!/usr/bin/env python3
"""
Compose the review PR body from a qa_gate draft report + the generated markdown.

Usage:
    python3 tools/pr_body.py --report content/reports/draft-12.json \
        --preview content/drafts/issue-12.md --issue 12 --out /tmp/pr-body.md
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
from pathlib import Path

GRADE_LABEL = {
    "A": "A · 可自动发布（本期未开放）",
    "B": "B · 需人工确认后合并",
    "C": "C · 建议重写，附扣分明细",
    "D": "D · 未通过，已打回",
}
DIM_NAME = {
    "sourcing": "事实可溯源", "points": "观点落地", "originality": "原创度",
    "specificity": "具体性", "structure": "结构", "seo": "SEO", "compliance": "合规",
}


def html_to_md(raw: str) -> str:
    """Minimal, review-friendly HTML -> Markdown (no dependency)."""
    s = raw
    s = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", s, flags=re.I | re.S)
    s = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", s, flags=re.I | re.S)
    s = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", s, flags=re.I | re.S)
    s = re.sub(r"<a\s[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"[\2](\1)", s, flags=re.I | re.S)
    s = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", s, flags=re.I | re.S)
    s = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", s, flags=re.I | re.S)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def load_preview(preview_path: Path) -> str:
    if preview_path.exists():
        return preview_path.read_text(encoding="utf-8")
    draft = preview_path.with_suffix(".json")
    if draft.exists():
        a = json.loads(draft.read_text(encoding="utf-8"))
        return "\n".join([
            f"# {a.get('title', '')}", "", f"> {a.get('excerpt', '')}", "",
            html_to_md(a.get("content", "")),
        ])
    return "(预览文件缺失)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--preview", required=True)
    ap.add_argument("--issue", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r = json.loads(Path(args.report).read_text(encoding="utf-8"))
    preview = load_preview(Path(args.preview))

    lines = [
        f"## 草稿评分：**{r['score']:.1f} / 100** · {GRADE_LABEL.get(r['grade'], r['grade'])}",
        "",
        "| 维度 | 得分 | 满分 |",
        "|---|---|---|",
    ]
    maxes = {"sourcing": 25, "points": 20, "originality": 15, "specificity": 10,
             "structure": 15, "seo": 10, "compliance": 5}
    for key, val in r["subscores"].items():
        if key in maxes:
            lines.append(f"| {DIM_NAME.get(key, key)} | {val} | {maxes[key]} |")

    if r["redlines"]:
        lines += ["", "### 命中红线（必须解决才能合并）", ""]
        lines += [f"- {h}" for h in r["redlines"]]

    if r["notes"]:
        lines += ["", "### 扣分原因", ""]
        lines += [f"- {n}" for n in r["notes"][:12]]

    lines += [
        "",
        "---",
        "",
        "## 审核清单（勾完再合并）",
        "",
        "- [ ] 每个数字/日期都能在 Sources 里找到",
        "- [ ] “我的判断”那段写的是我的立场，没有被 AI 改写或软化",
        "- [ ] 删掉了空话段落（至少 3 处）",
        "- [ ] 标题与正文一致，不夸张",
        "- [ ] 图片/引用无版权风险",
        "",
        "> 合并即发布：会自动重建静态页、更新 sitemap 并部署。",
        "",
        "---",
        "",
        "<details><summary>草稿全文（点击展开）</summary>",
        "",
        preview,
        "",
        "</details>",
    ]

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"pr body -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
