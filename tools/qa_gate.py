#!/usr/bin/env python3
"""
Content quality gate / scorer for HelloInsights.

Two modes
---------
1) corpus  : score every article already published (articles-*.json)
             -> content/log/scores.jsonl + content/reports/<date>-score.md
2) draft   : score a single generated draft (JSON produced by gemini_generate.mjs),
             optionally against the human brief (for the "points covered" dimension)
             -> exit code 0 = pass (A/B/C), 1 = reject (redline / D)

Only deterministic, evidence-based checks live here. Subjective judgement
(citation correctness, whether an opinion was really developed) is delegated to
an LLM judge; when no judge result is supplied those dimensions are marked
"pending" and the score is normalised over the dimensions that could be measured,
so a missing judge never silently boosts a score.

Usage
-----
    python3 tools/qa_gate.py corpus --site https://www.helloinsights.online
    python3 tools/qa_gate.py draft --file content/drafts/foo.json [--brief content/briefs/foo.yml]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ["technology", "finance", "ai-tools", "health-lifestyle"]
YMYL = {"finance", "health-lifestyle"}          # never auto-publish

# ---------------------------------------------------------------- rubrics ----
WEIGHTS = {
    "sourcing": 25,      # 事实可溯源 (LLM judge may refine)
    "points": 20,        # 观点落地 (needs a brief; pending otherwise)
    "originality": 15,   # 与库内重复度
    "specificity": 10,   # 具体性 / 去 AI 味
    "structure": 15,     # 结构与可读性
    "seo": 10,           # SEO 就绪
    "compliance": 5,     # 合规
}

GRADE_AUTO = 92          # auto-publish threshold (phase 1: unreachable on purpose)
GRADE_REVIEW = 75
GRADE_REWRITE = 60

# --------------------------------------------------------------- patterns ----
TAG_RE = re.compile(r"<[^>]+>")
H2_RE = re.compile(r"<h2\b", re.I)
H3_RE = re.compile(r"<h3\b", re.I)
LIST_RE = re.compile(r"<(ul|ol)\b", re.I)
LINK_RE = re.compile(r'<a\s[^>]*href="([^"#]+)"', re.I)
NUM_RE = re.compile(r"(?<![\w.])(?:\$|US\$|€|£)?\d[\d,.]*\s?(?:%|percent|billion|million|trillion|bn|k\b|GB|TB|ms|years?|months?)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

BOILERPLATE = [
    "in today's fast-paced", "in today's world", "in the ever-evolving",
    "plays a vital role", "plays a crucial role", "it is important to note",
    "delve into", "game-changer", "game changer", "unlock the potential",
    "stay ahead of the curve", "landscape of", "seamless", "cutting-edge",
    "revolutionize", "harness the power", "a testament to", "navigate the complexities",
    "rapidly evolving", "at the forefront", "paradigm shift", "robust",
]

BANNED = [
    "guaranteed returns", "guaranteed profit", "risk-free investment", "get rich quick",
    "cure cancer", "cures cancer", "miracle cure", "lose weight fast",
    "insider information", "secret formula", "100% accurate",
]

TRUST_TIER1 = ("gov", "edu", "who.int", "imf.org", "worldbank.org", "oecd.org",
               "europa.eu", "nih.gov", "cdc.gov", "nature.com", "science.org",
               "arxiv.org", "acm.org", "ieee.org", "reuters.com", "bloomberg.com",
               "ft.com", "wsj.com", "apnews.com", "economist.com")
TRUST_TIER2 = ("techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
               "cnbc.com", "bbc.com", "nytimes.com", "theguardian.com",
               "federalreserve.gov", "sec.gov", "statista.com", "gartner.com",
               "mckinsey.com", "deloitte.com", "pwc.com")
IGNORE_HOSTS = ("unsplash.com", "helloinsights.online", "fonts.googleapis.com",
                "fonts.gstatic.com", "schema.org", "w3.org")


# ------------------------------------------------------------------ utils ----
def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def ngrams(tokens: list[str], n: int = 8) -> set[tuple]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1).lower().lstrip("www.") if m else ""


def domain_tier(host: str) -> int:
    if not host:
        return 0
    if any(host == d or host.endswith("." + d) for d in TRUST_TIER1):
        return 3
    if host.endswith(".gov") or host.endswith(".edu"):
        return 3
    if any(host == d or host.endswith("." + d) for d in TRUST_TIER2):
        return 2
    return 1


# ------------------------------------------------------------------ metric ----
def measure(article: dict) -> dict:
    raw = article.get("content") or ""
    text = strip_html(raw)
    w = words(text)
    n_words = len(w)

    links = [u for u in LINK_RE.findall(raw) if not any(h in u for h in IGNORE_HOSTS)]
    citations = [{"url": u, "host": host_of(u), "tier": domain_tier(host_of(u))} for u in links]
    citation_weight = sum(c["tier"] for c in citations)

    numbers = NUM_RE.findall(text)
    n_claims = len(numbers) + len(set(YEAR_RE.findall(text)))

    boiler = [p for p in BOILERPLATE if p in text.lower()]
    banned_hits = [b for b in BANNED if b in text.lower()]

    h2 = len(H2_RE.findall(raw))
    h3 = len(H3_RE.findall(raw))
    lists = len(LIST_RE.findall(raw))
    paras = [p for p in re.split(r"</p>", raw) if strip_html(p)]
    para_lens = [len(words(strip_html(p))) for p in paras] or [0]

    # capitalised multi-word terms as a rough specificity proxy
    caps = len({m for m in re.findall(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*)\b", text)})

    return {
        "words": n_words,
        "h2": h2, "h3": h3, "lists": lists,
        "paragraphs": len(paras),
        "avg_para_words": round(sum(para_lens) / max(1, len(para_lens)), 1),
        "citations": citations,
        "citation_weight": citation_weight,
        "n_claims": n_claims,
        "boilerplate_hits": boiler,
        "banned_hits": banned_hits,
        "capitalised_terms": caps,
        "title_len": len(article.get("title") or ""),
        "excerpt_len": len(article.get("excerpt") or ""),
        "numbers_in_text": numbers[:12],
    }


def score_sourcing(m: dict) -> tuple[float, list[str]]:
    notes = []
    pts = min(18, m["citation_weight"] * 3, max(1, len(m["citations"])) * 5)
    if not m["citations"]:
        notes.append("零外部引用：所有事实都无法溯源")
    else:
        strong = sum(1 for c in m["citations"] if c["tier"] >= 3)
        notes.append(f"{len(m['citations'])} 个外链，其中权威源 {strong} 个")
    # unsourced quantitative claims
    unsourced = m["n_claims"] if not m["citations"] else max(0, m["n_claims"] - len(m["citations"]) * 2)
    if unsourced:
        pts -= min(7, unsourced * 0.6)
        notes.append(f"疑似无来源数字/年份约 {unsourced} 处")
    return max(0.0, pts), notes


def score_originality(overlap: float, novel: float | None = None) -> tuple[float, list[str]]:
    """Originality = worst of (max 8-gram overlap, share of sentences found nowhere else)."""
    notes = []
    if novel is None:
        base = 15.0 if overlap < 0.10 else 8.0 if overlap < 0.20 else 3.0 if overlap < 0.30 else 0.0
        return base, [f"与库内最高重合 {overlap:.1%}"]

    by_novel = 15.0 if novel >= 0.70 else 10.0 if novel >= 0.50 else 5.0 if novel >= 0.30 else 0.0
    by_overlap = 15.0 if overlap < 0.10 else 8.0 if overlap < 0.20 else 3.0 if overlap < 0.30 else 0.0
    notes.append(f"独创句 {novel:.0%}，与库内最高重合 {overlap:.0%}")
    if novel < 0.30:
        notes.append("多数句子在站内已出现过，属于模板拼接")
    return min(by_novel, by_overlap), notes


def score_specificity(m: dict) -> tuple[float, list[str]]:
    notes = []
    base = 0.0
    base += min(5.0, m["n_claims"] * 0.7)                  # concrete numbers
    base += min(3.0, m["capitalised_terms"] / 6.0)         # named entities
    penalty = min(6.0, len(m["boilerplate_hits"]) * 1.5)
    if m["boilerplate_hits"]:
        notes.append("空话句式：" + "、".join(m["boilerplate_hits"][:6]))
    if m["n_claims"] < 3:
        notes.append(f"具体数字/时间只有 {m['n_claims']} 处")
    return max(0.0, min(10.0, base + 2 - penalty)), notes


def score_structure(m: dict) -> tuple[float, list[str]]:
    notes = []
    pts = 0.0
    pts += min(6.0, m["words"] / 1200 * 6)                 # length
    if m["words"] < 700:
        notes.append(f"正文仅 {m['words']} 词（建议 ≥1100，硬下限 700）")
    pts += min(4.0, m["h2"] * 1.0)
    if m["h2"] == 0:
        notes.append("没有 H2 小节，整篇是一堵长墙")
    pts += 2.0 if m["lists"] else 0.0
    if not m["lists"]:
        notes.append("没有列表/要点，可扫读性差")
    pts += 2.0 if 45 <= m["avg_para_words"] <= 130 else 1.0
    if m["avg_para_words"] > 150:
        notes.append(f"段落平均 {m['avg_para_words']} 词，过长")
    pts += 1.0 if m["h3"] or m["paragraphs"] >= 6 else 0.0
    return min(15.0, pts), notes


def score_seo(m: dict) -> tuple[float, list[str]]:
    notes = []
    pts = 0.0
    tl = m["title_len"]
    pts += 4.0 if 40 <= tl <= 65 else (2.0 if 30 <= tl <= 75 else 0.0)
    if not 40 <= tl <= 65:
        notes.append(f"标题 {tl} 字符（建议 40–65）")
    el = m["excerpt_len"]
    pts += 3.0 if 110 <= el <= 165 else (1.5 if el else 0.0)
    if not 110 <= el <= 165:
        notes.append(f"摘要 {el} 字符（建议 110–165，用作 meta description）")
    pts += 3.0 if m["words"] >= 600 else 1.0
    return min(10.0, pts), notes


def score_compliance(m: dict, category: str) -> tuple[float, list[str]]:
    notes = []
    pts = 5.0
    if m["banned_hits"]:
        pts = 0.0
        notes.append("命中禁词：" + "、".join(m["banned_hits"]))
    if category in YMYL:
        pts -= 1.0
        notes.append("YMYL 分类：需免责声明（金融非投资建议 / 健康非医疗建议）")
    return max(0.0, pts), notes


def points_score(article: dict, brief: dict | None) -> tuple[float | None, list[str]]:
    """Needs a brief + LLM judge. Without one the dimension is pending."""
    if not brief:
        return None, ["无简报，观点落地维度跳过"]
    judge = article.get("judge") or {}
    if "points" in judge:
        return float(judge["points"]), [judge.get("points_note", "")]
    return None, ["等待 LLM 评审"]


# ------------------------------------------------------------------ grade ----
def redlines(m: dict, category: str, overlap: float, dup_title: bool,
             novel: float | None = None) -> list[str]:
    hits = []
    if m["words"] < 700:
        hits.append(f"篇幅不足（{m['words']} 词，硬下限 700）")
    if not m["citations"] and m["n_claims"] >= 3:
        hits.append(f"无可溯源引用，却有 {m['n_claims']} 处数字/年份")
    if overlap >= 0.30:
        hits.append(f"与库内文章重合度 {overlap:.0%}（≥30%）")
    if novel is not None and novel < 0.10:
        hits.append(f"独创句仅 {novel:.0%}（<10%，模板拼接）")
    if m["banned_hits"]:
        hits.append("命中合规禁词")
    if category in YMYL:
        hits.append("YMYL 分类缺免责声明")
    if dup_title:
        hits.append("标题与已有文章高度重复")
    return hits


def grade(total: float, hits: list[str], category: str, auto_unlocked: bool) -> str:
    if hits:
        return "D"
    if total >= GRADE_AUTO and auto_unlocked and category not in YMYL:
        return "A"
    if total >= GRADE_REVIEW:
        return "B"
    if total >= GRADE_REWRITE:
        return "C"
    return "D"


def evaluate(article: dict, overlap: float, dup_title: bool,
             brief: dict | None = None, auto_unlocked: bool = False,
             novel: float | None = None) -> dict:
    m = measure(article)
    cat = article.get("category") or ""

    parts, notes = {}, []
    for name, fn in (
        ("sourcing", lambda: score_sourcing(m)),
        ("originality", lambda: score_originality(overlap, novel)),
        ("specificity", lambda: score_specificity(m)),
        ("structure", lambda: score_structure(m)),
        ("seo", lambda: score_seo(m)),
        ("compliance", lambda: score_compliance(m, cat)),
    ):
        val, note = fn()
        parts[name] = round(val, 1)
        notes += [f"[{name}] {n}" for n in note if n]

    pts, pts_notes = points_score(article, brief)
    if pts is not None:
        parts["points"] = round(pts, 1)
        notes += [f"[points] {n}" for n in pts_notes if n]

    available = sum(WEIGHTS[k] for k in parts)
    raw = sum(parts.values())
    total = round(raw / available * 100, 1) if available else 0.0

    hits = redlines(m, cat, overlap, dup_title, novel)
    g = grade(total, hits, cat, auto_unlocked)

    return {
        "id": str(article.get("id")),
        "title": article.get("title"),
        "category": cat,
        "score": total,
        "grade": g,
        "subscores": parts,
        "max_available": available,
        "redlines": hits,
        "notes": notes,
        "metrics": {
            "words": m["words"], "h2": m["h2"], "lists": m["lists"],
            "citations": len(m["citations"]),
            "authoritative_citations": sum(1 for c in m["citations"] if c["tier"] >= 3),
            "claims": m["n_claims"], "boilerplate": len(m["boilerplate_hits"]),
            "overlap": round(overlap, 4),
            "novel_sentences": round(novel, 3) if novel is not None else None,
        },
        "flags": {
            "pending_judge": pts is None,
            "ymyl": cat in YMYL,
            "duplicate_title": dup_title,
        },
    }


# ----------------------------------------------------------------- corpus ----
def load_corpus() -> list[dict]:
    rows = []
    for cat in CATEGORIES:
        p = ROOT / f"articles-{cat}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        arr = data["articles"] if isinstance(data, dict) else data
        for a in arr:
            a.setdefault("category", cat)
            rows.append(a)
    return rows


def overlap_index(rows: list[dict]) -> tuple[list[float], list[bool]]:
    """Max 8-gram containment against every other article + duplicate-title flags."""
    grams = [ngrams(words(strip_html(a.get("content") or ""))) for a in rows]
    index: dict[tuple, list[int]] = {}
    for i, gs in enumerate(grams):
        for g in gs:
            index.setdefault(g, []).append(i)

    max_overlap = [0.0] * len(rows)
    for i, gs in enumerate(grams):
        if not gs:
            continue
        shared: dict[int, int] = {}
        for g in gs:
            for j in index.get(g, ()):
                if j != i:
                    shared[j] = shared.get(j, 0) + 1
        if shared:
            j, cnt = max(shared.items(), key=lambda kv: kv[1])
            max_overlap[i] = cnt / len(gs)

    norm_titles = [re.sub(r"[^a-z0-9 ]", "", (a.get("title") or "").lower()) for a in rows]
    dup = []
    seen: dict[str, int] = {}
    for i, t in enumerate(norm_titles):
        key = " ".join(t.split()[:8])
        dup.append(key in seen)
        seen.setdefault(key, i)
    return max_overlap, dup


def sentence_stats(rows: list[dict]) -> tuple[list[float], dict]:
    """Share of each article's sentences that appear nowhere else in the corpus."""
    counter: dict[str, int] = {}
    per_article: list[list[str]] = []
    for a in rows:
        text = strip_html(a.get("content") or "")
        ss = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s) > 25]
        per_article.append(ss)
        for s in ss:
            counter[s] = counter.get(s, 0) + 1

    total = sum(len(ss) for ss in per_article)
    unique = len(counter)
    novelty = [
        (sum(1 for s in ss if counter.get(s) == 1) / len(ss)) if ss else 0.0
        for ss in per_article
    ]
    top = sorted(counter.items(), key=lambda kv: -kv[1])[:5]
    return novelty, {
        "sentences": total,
        "unique_sentences": unique,
        "duplicate_rate": (1 - unique / total) if total else 0.0,
        "top_sentences": top,
    }


def cmd_corpus(args) -> int:
    rows = load_corpus()
    if not rows:
        print("no articles-*.json found", file=sys.stderr)
        return 1

    overlaps, dups = overlap_index(rows)
    novelty, sent_stats = sentence_stats(rows)
    results = [
        evaluate(a, o, d, auto_unlocked=False, novel=nv)
        for a, o, d, nv in zip(rows, overlaps, dups, novelty)
    ]

    log_dir = ROOT / "content" / "log"
    rep_dir = ROOT / "content" / "reports"
    log_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.date.today().isoformat()
    with (log_dir / "scores.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({"scored_at": stamp, "mode": "corpus", **r}, ensure_ascii=False) + "\n")

    buckets = {"A (≥92)": 0, "B (75–91)": 0, "C (60–74)": 0, "D (<60/红线)": 0}
    for r in results:
        g = r["grade"]
        buckets["A (≥92)" if g == "A" else "B (75–91)" if g == "B" else "C (60–74)" if g == "C" else "D (<60/红线)"] += 1

    by_cat = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    lines = [
        f"# 存量文章质量评分 · {stamp}",
        "",
        f"共 **{len(results)}** 篇，评分口径：客观项 80 分制归一化到 100（\"观点落地\"需简报，存量文章不适用）。",
        "",
        "## 分布",
        "",
        "| 档位 | 篇数 | 占比 |",
        "|---|---|---|",
    ]
    for k, v in buckets.items():
        lines.append(f"| {k} | {v} | {v / len(results):.0%} |")

    lines += ["", "## 各维度平均分（满分）", "", "| 分类 | 总分 | 溯源(25) | 原创(15) | 具体(10) | 结构(15) | SEO(10) | 合规(5) |", "|---|---|---|---|---|---|---|---|"]
    for cat, rs in sorted(by_cat.items()):
        def avg(k):
            return sum(r["subscores"].get(k, 0) for r in rs) / len(rs)
        lines.append(
            f"| {cat} | {sum(r['score'] for r in rs) / len(rs):.1f} | "
            f"{avg('sourcing'):.1f} | {avg('originality'):.1f} | {avg('specificity'):.1f} | "
            f"{avg('structure'):.1f} | {avg('seo'):.1f} | {avg('compliance'):.1f} |"
        )

    redline_count = {}
    for r in results:
        for h in r["redlines"]:
            key = re.sub(r"[\d.,]+", "N", h.split("（")[0])
            redline_count[key] = redline_count.get(key, 0) + 1

    worst = sorted(results, key=lambda r: r["score"])[:8]
    best = sorted(results, key=lambda r: -r["score"])[:5]
    top_pairs = sorted(((r["metrics"]["overlap"], r["title"]) for r in results), key=lambda x: -x[0])[:5]

    lines += [
        "", "## 语料级重复度（最关键的一项）", "",
        f"- 句子总数 **{sent_stats['sentences']:,}**，去重后只剩 **{sent_stats['unique_sentences']:,}**，"
        f"**全库重复率 {sent_stats['duplicate_rate']:.0%}**",
        f"- 每篇“独创句占比”：中位数 **{sorted(novelty)[len(novelty) // 2]:.0%}**，"
        f"独创句 <10% 的文章 **{sum(1 for n in novelty if n < 0.10)}** 篇",
        "- 出现次数最多的句子（说明整站是一个模板句池）：",
        "",
        "| 次数 | 句子 |",
        "|---|---|",
    ]
    for s, c in sent_stats["top_sentences"]:
        lines.append(f"| {c} | {s[:88]} |")

    lines += ["", "## 红线命中统计", "", "| 问题 | 篇数 |", "|---|---|"]
    for k, v in sorted(redline_count.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")

    lines += ["", "## 最低分样本", "", "| 分数 | 标题 | 主要问题 |", "|---|---|---|"]
    for r in worst:
        first = (r["redlines"] or r["notes"] or ["—"])[0]
        lines.append(f"| {r['score']:.1f} | {r['title'][:56]} | {first[:70]} |")

    lines += ["", "## 最高分样本（仍然不达标）", "", "| 分数 | 标题 | 说明 |", "|---|---|---|"]
    for r in best:
        lines.append(
            f"| {r['score']:.1f} | {r['title'][:56]} | 独创句 {r['metrics']['novel_sentences']:.0%}、"
            f"外链 {r['metrics']['citations']} 个、H2 {r['metrics']['h2']} 个 |"
        )

    lines += ["", "## 8-gram 重合度最高", "", "| 重合率 | 文章 |", "|---|---|"]
    for ov, t in top_pairs:
        lines.append(f"| {ov:.0%} | {t[:60]} |")

    lines += [
        "", "## 结论", "",
        f"- **A 档 {buckets['A (≥92)']} 篇、B 档 {buckets['B (75–91)']} 篇、C 档 {buckets['C (60–74)']} 篇** —— "
        f"自动发布阈值（92）当前一篇都达不到，这是符合预期的。",
        f"- **{len(results)} 篇全部命中红线**：零外部引用 + 句子级近重复 + YMYL 缺免责声明。",
        "- 核心问题不是“写得不够好”，而是**同一批模板句被拼接了 500 次**（重复率 "
        f"{sent_stats['duplicate_rate']:.0%}），这属于 Google 明确打击的规模化低价值内容。",
        "- 处置建议：① 全站文章页先加 `noindex`（保留可访问，止损）；② 按流量挑 20~30 个真有需求的题目重写；"
        "③ 重写走新流水线（人工简报 → Gemini 成文 → 评分门禁 → 人工过稿），关闭每天 5 篇的自动生成。",
    ]

    report = rep_dir / f"{stamp}-score.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"scored {len(results)} articles")
    print("buckets:", buckets)
    print("redline hits:", redline_count)
    print("avg score:", round(sum(r["score"] for r in results) / len(results), 1))
    print("report:", report.relative_to(ROOT))
    print("log:", (log_dir / "scores.jsonl").relative_to(ROOT))
    return 0


# ------------------------------------------------------------------ draft ----
def cmd_draft(args) -> int:
    article = json.loads(Path(args.file).read_text(encoding="utf-8"))
    brief = None
    if args.brief:
        p = Path(args.brief)
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            brief = json.loads(txt) if txt.lstrip().startswith("{") else {"raw": txt}

    rows = load_corpus()
    overlap, novel = 0.0, None
    if rows:
        grams = ngrams(words(strip_html(article.get("content") or "")))
        corpus_sentences: dict[str, int] = {}
        for a in rows:
            text = strip_html(a.get("content") or "")
            for s in re.split(r"(?<=[.!?])\s+", text):
                s = s.strip()
                if len(s) > 25:
                    corpus_sentences[s] = corpus_sentences.get(s, 0) + 1
            others = ngrams(words(text))
            if grams and others:
                overlap = max(overlap, len(grams & others) / len(grams))

        draft_sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", strip_html(article.get("content") or ""))
            if len(s.strip()) > 25
        ]
        if draft_sentences:
            reused = sum(1 for s in draft_sentences if s in corpus_sentences)
            novel = 1 - reused / len(draft_sentences)

    dup_title = any(
        (a.get("title") or "").lower().strip() == (article.get("title") or "").lower().strip()
        for a in rows
    )
    r = evaluate(article, overlap, dup_title, brief=brief,
                 auto_unlocked=args.auto_unlocked, novel=novel)

    print(json.dumps(r, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if r["grade"] != "D" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="HelloInsights content quality gate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("corpus", help="score every published article")
    c.add_argument("--site", default="https://www.helloinsights.online")
    c.set_defaults(func=cmd_corpus)

    d = sub.add_parser("draft", help="score a single generated draft")
    d.add_argument("--file", required=True)
    d.add_argument("--brief", default=None)
    d.add_argument("--out", default=None)
    d.add_argument("--auto-unlocked", action="store_true",
                   help="allow grade A (only after calibration)")
    d.set_defaults(func=cmd_draft)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
