#!/usr/bin/env python3
"""
Render a draft as a real page so reviewers (and Cloudflare PR previews) can see
exactly what will ship, with site CSS and layout.

Output: articles/_preview-<slug>.html  (noindex, deleted again on publish)

Usage:
    python3 tools/preview_draft.py content/drafts/issue-12.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_static as bs  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: preview_draft.py <draft.json>", file=sys.stderr)
        return 2

    draft = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    slug = (draft.get("_meta") or {}).get("slug") or str(draft.get("id", "draft"))
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug)[:60]

    all_articles = bs.load_articles()
    body_pool = [a for a in all_articles if a.get("category") == draft.get("category")][:3]
    header, footer = bs.extract_shell()
    page = bs.build_page(draft, all_articles + body_pool, header, footer)
    # build_static may already emit a robots meta (legacy-noindex default);
    # strip it so the preview's stricter noindex,nofollow is the only one.
    page = re.sub(r'\s*<meta name="robots"[^>]*>', "", page, count=1)
    page = page.replace(
        "<head>",
        '<head>\n    <meta name="robots" content="noindex,nofollow">',
        1,
    )
    # 预览页不该对外声明 canonical，避免被当成正式页面
    page = re.sub(r'\s*<link rel="canonical"[^>]*>', "", page)
    page = re.sub(r'\s*<script type="application/ld\+json">.*?</script>', "", page, flags=re.S)

    out = Path("articles") / f"_preview-{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
