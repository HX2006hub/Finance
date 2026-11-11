#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate static, SEO-complete article pages from the JSON article store.

Outputs:
  articles/<id>.html      -> one crawlable page per article
  cards-<category>.json   -> lightweight card data for index/category pages
  sitemap.xml             -> regenerated sitemap pointing at static pages

Run:  python tools/build_static.py
"""
import json
import os
import re
import html
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://www.helloinsights.online"

# ---------------------------------------------------------------------------
# noindex switch
#
# ARTICLES_INDEX_MODE (env var), default "legacy-noindex":
#   legacy-noindex -> articles WITHOUT an explicit "indexable": true flag are
#                     rendered with <meta name="robots" content="noindex,follow">
#                     and excluded from sitemap.xml. Only pipeline-generated
#                     articles (flagged by integrate_drafts.py) get indexed.
#   all-index      -> everything indexed (flip this once legacy content is
#                     replaced/reviewed and quality is trusted site-wide)
#   all-noindex    -> everything noindex (emergency brake)
#
# Per-article override in articles-*.json:  "indexable": true / false
# ---------------------------------------------------------------------------
INDEX_MODE = os.environ.get("ARTICLES_INDEX_MODE", "legacy-noindex").strip().lower()
if INDEX_MODE not in ("legacy-noindex", "all-index", "all-noindex"):
    raise SystemExit("ARTICLES_INDEX_MODE must be legacy-noindex | all-index | all-noindex, got: %r" % INDEX_MODE)


def is_indexable(a):
    if INDEX_MODE == "all-noindex":
        return False
    if INDEX_MODE == "all-index":
        return True
    return bool(a.get("indexable"))

CATEGORIES = ["technology", "finance", "ai-tools", "health-lifestyle"]
CAT_NAMES = {
    "technology": "Technology",
    "finance": "Finance",
    "ai-tools": "AI Tools",
    "health-lifestyle": "Health & Lifestyle",
}
FALLBACK_IMG = {
    "technology": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&h=400&fit=crop",
    "finance": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&h=400&fit=crop",
    "ai-tools": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=600&h=400&fit=crop",
    "health-lifestyle": "https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=600&h=400&fit=crop",
}

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='6' fill='%23ff6b35'/%3E%3Ctext x='16' y='23' "
           "text-anchor='middle' fill='white' font-family='Arial,sans-serif' font-weight='bold' "
           "font-size='22'%3EH%3C/text%3E%3C/svg%3E")


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def write(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load_articles():
    articles = []
    for cat in CATEGORIES:
        data = json.loads(read("articles-%s.json" % cat))
        for a in data.get("articles", []):
            a.setdefault("category", cat)
            articles.append(a)
    return articles


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def meta_desc(a, limit=155):
    text = strip_tags(a.get("excerpt") or a.get("content") or a.get("title"))
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "\u2026"
    return text


def human_date(d):
    try:
        dt = datetime.date.fromisoformat(d)
        return dt.strftime("%B ") + str(dt.day) + dt.strftime(", %Y")
    except Exception:
        return d or ""


def hero_url(img, cat):
    base = img or FALLBACK_IMG.get(cat, "")
    base = base.replace("w=600&h=400", "w=1200&h=600").replace("w=800&h=450", "w=1200&h=600")
    if "fm=webp" not in base:
        base += ("&" if "?" in base else "?") + "fm=webp"
    return base


def card_img(img, cat):
    base = img or FALLBACK_IMG.get(cat, "")
    return base


CSS_EXTRA = """
    .breadcrumb{font-size:.85rem;color:#888;margin:1rem 0 1.2rem;}
    .breadcrumb a{color:#ff6b35;text-decoration:none;}
    .breadcrumb a:hover{text-decoration:underline;}
    .article-grid{display:grid;gap:1.2rem;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));}
    .back-link{display:inline-block;margin:2rem 0 3rem;color:#ff6b35;text-decoration:none;font-weight:600;}
"""


def extract_shell():
    src = read("article.html")
    header = src[src.index('<header class="header">'): src.index("</header>") + len("</header>")]
    footer = src[src.index('<footer class="footer">'): src.index("</footer>") + len("</footer>")]
    href_re = re.compile(r'href="(?!https?:|\.\./|#|mailto:)([^"]+)"')

    def prefix(block):
        return href_re.sub(lambda m: 'href="../%s"' % m.group(1), block)

    return prefix(header), prefix(footer)


def build_page(a, all_articles, header, footer):
    cat = a.get("category", "finance")
    cat_name = CAT_NAMES.get(cat, cat)
    title = (a.get("title") or "Article").strip()
    desc = meta_desc(a)
    url = "%s/articles/%s.html" % (BASE_URL, a["id"])
    img = hero_url(a.get("image"), cat)
    date_iso = (a.get("date") or "").strip()
    date_human = human_date(date_iso)
    content = a.get("content") or "<p>%s</p>" % html.escape(a.get("excerpt", ""))
    indexable = is_indexable(a)
    robots_meta = ("" if indexable
                   else '<meta name="robots" content="noindex,follow">\n')

    related = [x for x in all_articles if x.get("category") == cat and x.get("id") != a["id"]]
    related.sort(key=lambda x: x.get("date") or "", reverse=True)
    related = related[:3]
    rel_html = "".join(
        '<article class="article-card">'
        '<div class="card-image"><a href="../articles/%s.html"><img src="%s" alt="%s" '
        'width="600" height="400" loading="lazy" decoding="async"></a></div>'
        '<div class="card-content"><span class="card-category">%s</span>'
        '<h3 class="card-title"><a href="../articles/%s.html">%s</a></h3>'
        '<p class="card-excerpt">%s</p>'
        '<div class="card-meta"><span>%s</span></div>'
        '<a href="../articles/%s.html" class="read-more-btn">Read More</a></div></article>'
        % (
            x["id"], card_img(x.get("image"), x.get("category")),
            html.escape(x.get("title", ""), quote=True), CAT_NAMES.get(x.get("category"), ""),
            x["id"], html.escape(x.get("title", "")),
            html.escape(x.get("excerpt", "")), human_date(x.get("date")),
            x["id"],
        )
        for x in related
    )

    ld_article = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": desc,
        "image": [img],
        "datePublished": (date_iso + "T08:00:00+00:00") if date_iso else "",
        "dateModified": (date_iso + "T08:00:00+00:00") if date_iso else "",
        "articleSection": cat_name,
        "inLanguage": "en",
        "author": {"@type": "Organization", "name": "HelloInsights"},
        "publisher": {
            "@type": "Organization",
            "name": "HelloInsights",
            "logo": {"@type": "ImageObject", "url": BASE_URL + "/logo.svg"},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
    }
    ld_crumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": cat_name,
             "item": "%s/category.html?cat=%s" % (BASE_URL, cat)},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    }
    esc = lambda s: html.escape(s, quote=True)

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | HelloInsights {cat_name}</title>
<meta name="description" content="{desc}">
{robots_meta}<link rel="canonical" href="{url}">
<link rel="icon" href="{favicon}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="HelloInsights">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="article:published_time" content="{date_iso}">
<meta property="article:section" content="{cat_name}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{img}">
<link rel="preconnect" href="https://images.unsplash.com" crossorigin>
<link rel="dns-prefetch" href="https://images.unsplash.com">
<link rel="preconnect" href="https://pagead2.googlesyndication.com" crossorigin>
<link rel="stylesheet" href="../style.css">
<script type="application/ld+json">{ld_article}</script>
<script type="application/ld+json">{ld_crumb}</script>
<script src="../ads-config.js" defer></script>
<style>{css_extra}</style>
</head>
<body>
{header}
<main class="container">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="../index.html">Home</a> &rsaquo;
    <a href="../category.html?cat={cat}">{cat_name}</a> &rsaquo;
    <span>{title}</span>
  </nav>
  <div data-ad-slot="article-banner"></div>
  <article class="article-detail">
    <div class="article-hero">
      <img src="{img}" alt="{title}" width="1200" height="600" loading="eager" fetchpriority="high">
    </div>
    <div class="article-body">
      <header class="article-header">
        <span class="card-category">{cat_name}</span>
        <h1>{title}</h1>
        <div class="article-meta"><span>{date_human}</span></div>
      </header>
      <div class="article-content">
{content}
      </div>
    </div>
  </article>
  <div data-ad-slot="article-mgid"></div>
  <section class="internal-links-section" style="margin-top:3rem;">
    <h2 class="section-title">Related Articles</h2>
    <div class="article-grid">{rel_html}</div>
  </section>
  <a class="back-link" href="../category.html?cat={cat}">&larr; More {cat_name} articles</a>
</main>
{footer}
<button class="back-to-top" id="backToTop" onclick="scrollToTop()">&uarr;</button>
<script>
function toggleMenu(){{var n=document.getElementById('navContainer');if(n)n.classList.toggle('active');}}
function scrollToTop(){{window.scrollTo({{top:0,behavior:'smooth'}});}}
(function(){{var si=document.getElementById('searchInput'),sb=document.getElementById('searchBtn');
function go(){{var q=(si&&si.value||'').trim();location.href='../index.html'+(q?'?q='+encodeURIComponent(q):'');}}
if(sb)sb.addEventListener('click',function(e){{e.preventDefault();go();}});
if(si)si.addEventListener('keypress',function(e){{if(e.key==='Enter'){{e.preventDefault();go();}}}});}})();
window.addEventListener('scroll',function(){{var b=document.getElementById('backToTop');if(b)b.style.display=window.scrollY>400?'block':'none';}});
</script>
</body>
</html>
""".format(
        title=esc(title), cat_name=esc(cat_name), desc=esc(desc), url=url,
        robots_meta=robots_meta,
        favicon=FAVICON, img=esc(img), date_iso=date_iso, date_human=esc(date_human),
        ld_article=json.dumps(ld_article, ensure_ascii=False),
        ld_crumb=json.dumps(ld_crumb, ensure_ascii=False),
        css_extra=CSS_EXTRA, header=header, footer=footer,
        cat=cat, content=content, rel_html=rel_html,
    )


def build_cards(all_articles):
    for cat in CATEGORIES:
        items = [a for a in all_articles if a.get("category") == cat]
        items.sort(key=lambda x: x.get("date") or "", reverse=True)
        lean = [{
            "id": a["id"],
            "category": cat,
            "title": a.get("title", ""),
            "excerpt": a.get("excerpt", ""),
            "image": a.get("image", ""),
            "date": a.get("date", ""),
            "url": "articles/%s.html" % a["id"],
        } for a in items]
        write("cards-%s.json" % cat, json.dumps(
            {"version": int(datetime.datetime.now().timestamp()), "articles": lean},
            ensure_ascii=False, separators=(",", ":")))


def build_sitemap(all_articles):
    today = datetime.date.today().isoformat()
    rows = [
        (BASE_URL + "/", today, "daily", "1.0"),
        (BASE_URL + "/about.html", today, "monthly", "0.3"),
        (BASE_URL + "/contact.html", today, "monthly", "0.3"),
        (BASE_URL + "/privacy.html", today, "yearly", "0.2"),
        (BASE_URL + "/terms.html", today, "yearly", "0.2"),
    ]
    for cat in CATEGORIES:
        rows.append(("%s/category.html?cat=%s" % (BASE_URL, cat), today, "daily", "0.8"))
    for a in sorted(all_articles, key=lambda x: x.get("date") or "", reverse=True):
        if not is_indexable(a):
            continue  # noindex pages must not be listed in the sitemap
        rows.append(("%s/articles/%s.html" % (BASE_URL, a["id"]),
                     a.get("date") or today, "monthly", "0.6"))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq, prio in rows:
        parts.append("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n"
                     "    <changefreq>%s</changefreq>\n    <priority>%s</priority>\n  </url>"
                     % (loc, lastmod, freq, prio))
    parts.append("</urlset>")
    write("sitemap.xml", "\n".join(parts) + "\n")
    return len(rows)


def main():
    articles = load_articles()
    header, footer = extract_shell()
    for a in articles:
        write(os.path.join("articles", "%s.html" % a["id"]),
              build_page(a, articles, header, footer))
    build_cards(articles)
    total = build_sitemap(articles)
    print("articles written: %d" % len(articles))
    print("indexable: %d  (mode: %s)" % (sum(1 for a in articles if is_indexable(a)), INDEX_MODE))
    print("sitemap urls: %d" % total)


if __name__ == "__main__":
    main()
