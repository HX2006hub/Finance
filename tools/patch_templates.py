#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-off patch: point templates at static article pages and lean card JSON."""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(name, pairs):
    path = os.path.join(ROOT, name)
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    original = src
    for old, new, expect in pairs:
        n = src.count(old)
        if n != expect:
            print("!! %s: expected %d hit(s), found %d for: %s" % (name, expect, n, old[:70]))
            sys.exit(1)
        src = src.replace(old, new)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print("patched %s (%d chars -> %d)" % (name, len(original), len(src)))


# ---------- index.html ----------
patch("index.html", [
    ('<link rel="stylesheet" href="style.css" media="print" onload="this.media=\'all\'">',
     '<link rel="stylesheet" href="style.css">', 1),
    ("'<h3 class=\"card-title\"><a href=\"article.html?id=' + article.id + '\">' + article.title + '</a></h3>' +",
     "'<h3 class=\"card-title\"><a href=\"articles/' + article.id + '.html\">' + article.title + '</a></h3>' +", 1),
    ("'<a href=\"article.html?id=' + article.id + '\" class=\"read-more-btn\">Read More</a>' +",
     "'<a href=\"articles/' + article.id + '.html\" class=\"read-more-btn\">Read More</a>' +", 1),
    ("html += '<a class=\"featured-card\" href=\"article.html?id=' + a.id + '\">' +",
     "html += '<a class=\"featured-card\" href=\"articles/' + a.id + '.html\">' +", 1),
    ("html += '<a class=\"latest-card\" href=\"article.html?id=' + a.id + '\">' +",
     "html += '<a class=\"latest-card\" href=\"articles/' + a.id + '.html\">' +", 1),
    ("fetch(CFG.jsonFile)",
     "fetch(CFG.cardsFile || CFG.jsonFile.replace('articles-', 'cards-'))", 1),
])

# ---------- category.html ----------
patch("category.html", [
    ("'<h3 class=\"card-title\"><a href=\"article.html?id=' + article.id + '\">' + article.title + '</a></h3>' +",
     "'<h3 class=\"card-title\"><a href=\"articles/' + article.id + '.html\">' + article.title + '</a></h3>' +", 1),
    ("'<a href=\"article.html?id=' + article.id + '\" class=\"read-more-btn\">Read More</a>' +",
     "'<a href=\"articles/' + article.id + '.html\" class=\"read-more-btn\">Read More</a>' +", 1),
    ("fetch('articles-' + currentCategory + '.json', { cache: 'force-cache' })",
     "fetch('cards-' + currentCategory + '.json', { cache: 'force-cache' })", 1),
    ("fetch('articles-index.json?v=' + Date.now())",
     "fetch('articles-index.json')", 1),
    ("return fetch('articles-' + currentCategory + '.json?v=' + v)",
     "return fetch('cards-' + currentCategory + '.json?v=' + v)", 1),
])

# ---------- article.html ----------
patch("article.html", [
    ("'<a href=\"article.html?id=' + article.id + '\">' + article.title + '</a>' +",
     "'<a href=\"articles/' + article.id + '.html\">' + article.title + '</a>' +", 1),
    ("'<a href=\"article.html?id=' + article.id + '\" class=\"read-more-btn\">Read More...</a>' +",
     "'<a href=\"articles/' + article.id + '.html\" class=\"read-more-btn\">Read More...</a>' +", 1),
    ('    <title>Article - HelloInsights</title>',
     '    <title>Article - HelloInsights</title>\n    <link rel="canonical" id="canonicalLink" href="https://www.helloinsights.online/">', 1),
])

# ---------- ads-config.js ----------
patch("ads-config.js", [
    ("    function getCurrentPage() {\n        var path = location.pathname.split('/').pop() || 'index.html';",
     "    function getCurrentPage() {\n        if (location.pathname.indexOf('/articles/') !== -1) return 'article';\n        var path = location.pathname.split('/').pop() || 'index.html';", 1),
])
print("all patches applied")
