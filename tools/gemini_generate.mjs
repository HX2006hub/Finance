#!/usr/bin/env node
/**
 * Brief -> article draft, via Gemini.
 *
 * Reads content/briefs/<slug>.json (produced from the GitHub issue form),
 * asks Gemini for a structured article, validates the result against hard
 * requirements, and writes:
 *   content/drafts/<slug>.json  full article object (same shape as articles-*.json)
 *   content/drafts/<slug>.md    readable preview for the PR body
 *
 * The script never publishes anything; tools/qa_gate.py decides what happens next.
 *
 * Usage:
 *   node tools/gemini_generate.mjs --brief content/briefs/issue-12.json
 *   node tools/gemini_generate.mjs --brief ... --dry-run     # print prompt, no API call
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models';
const MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
const API_KEY = process.env.GEMINI_API_KEY;

const BANNED_PHRASES = [
  "in today's fast-paced", "in today's world", "in the ever-evolving",
  'plays a vital role', 'plays a crucial role', 'it is important to note',
  'delve into', 'game-changer', 'unlock the potential', 'stay ahead of the curve',
  'seamless', 'cutting-edge', 'revolutionize', 'harness the power',
  'a testament to', 'navigate the complexities', 'rapidly evolving',
  'at the forefront', 'paradigm shift',
];

const RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string', description: '50-65 characters, specific, no clickbait, no year padding' },
    slug: { type: 'string', description: 'kebab-case, <= 60 chars' },
    meta_description: { type: 'string', description: '140-160 characters' },
    excerpt: { type: 'string', description: 'One sentence, 110-165 characters' },
    body_html: {
      type: 'string',
      description: 'Article body as HTML: <p>, <h2>, <h3>, <ul><li>, <ol><li>, <strong>, <em>, <a href>. No <html>/<head>/<body>. 1100-1500 words.',
    },
    faq: {
      type: 'array',
      description: 'Exactly 3 genuinely useful questions readers would ask',
      items: {
        type: 'object',
        properties: {
          question: { type: 'string' },
          answer_html: { type: 'string', description: '2-4 sentences, HTML <p> allowed' },
        },
        required: ['question', 'answer_html'],
      },
    },
    sources: {
      type: 'array',
      description: 'Every URL actually used as a factual basis',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          url: { type: 'string' },
        },
        required: ['title', 'url'],
      },
    },
    tags: { type: 'array', items: { type: 'string' } },
  },
  required: ['title', 'slug', 'meta_description', 'excerpt', 'body_html', 'faq', 'sources'],
};

function readJSON(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function buildPrompt(brief) {
  const today = new Date().toISOString().slice(0, 10);
  const points = brief.points.map((p, i) => `${i + 1}. ${p}`).join('\n');
  const sources = (brief.sources || []).length
    ? brief.sources.map((u) => `- ${u}`).join('\n')
    : '- (none supplied: propose 3-5 authoritative sources in the sources array and cite only those; if you cannot verify a fact, omit it)';

  return `You are a professional technology/industry writer producing ONE article for HelloInsights.

TODAY: ${today}
CATEGORY: ${brief.category}
TOPIC: ${brief.topic}
AUDIENCE: ${brief.audience || 'general professional readers'}
ANGLE: ${brief.angle || '(decide a specific angle yourself, then keep it)'}
TARGET KEYWORDS (use naturally, never stuff): ${(brief.keywords || []).join(', ') || '(none)'}

THE WRITER'S OWN VIEWPOINTS (this is the point of the article — every one of these MUST become its own H2 section, developed with evidence, not restated):
${points}

THE AUTHOR'S CONCLUSION (use as the basis of the closing section; do not soften or reverse it):
"${brief.my_take}"

FACT SOURCES (the ONLY places numbers, dates, company claims and statistics may come from):
${sources}

HARD RULES
1. Every number, percentage, date, price and named study MUST come from the sources above and be hyperlinked inline, e.g. <a href="URL" rel="noopener" target="_blank">source</a>. If a figure is not in the sources, leave it out. Never invent statistics or quotes.
2. 1100-1500 words of body text. Structure: 1-2 intro paragraphs, then one H2 per viewpoint (4-6 H2 sections total, H3 allowed), then a closing H2 that states the author's conclusion, then the FAQ.
3. Include at least 2 external citations and ${
    (brief.internal_links || []).length
      ? `at least 1 internal link to /articles/<id>.html for ids: ${(brief.internal_links || []).join(', ')}`
      : 'no internal links (none provided)'
  }.
4. Use <ul>/<ol> at least twice and <strong> sparingly (max 8 times) — the page renders plain <p> walls badly.
5. Write concrete, specific prose: name companies, products, numbers, dates. Short paragraphs (2-4 sentences). Vary sentence length.
6. BANNED phrasing (any occurrence fails review): ${BANNED_PHRASES.join('; ')}.
7. No hype, no "both sides equally" hedging, no listicle padding, no filler intro about how important the topic is.
8. ${
    brief.ymyl
      ? 'This is a YMYL topic: no personalised financial/medical advice, no predictions presented as fact; the page adds a disclaimer automatically.'
      : 'Stay factual; opinion must be clearly presented as opinion.'
  }
9. Output valid JSON matching the schema. HTML fragments only — no markdown inside body_html, no <html>/<head>/<body>, no <script>, no inline styles, no <h1> (the page renders the title itself).
10. Title: specific and informative, 50-65 characters, no clickbait, do not append the year unless the source material is year-specific.`;
}

async function callGemini(prompt, attempt) {
  const url = `${API_BASE}/${MODEL}:generateContent?key=${API_KEY}`;
  const body = {
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: attempt === 0 ? 0.85 : 0.55,
      topP: 0.95,
      maxOutputTokens: 8192,
      responseMimeType: 'application/json',
      responseSchema: RESPONSE_SCHEMA,
    },
    safetySettings: [
      'HARM_CATEGORY_HARASSMENT',
      'HARM_CATEGORY_HATE_SPEECH',
      'HARM_CATEGORY_SEXUALLY_EXPLICIT',
      'HARM_CATEGORY_DANGEROUS_CONTENT',
    ].map((category) => ({ category, threshold: 'BLOCK_ONLY_HIGH' })),
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Gemini HTTP ${res.status}: ${text.slice(0, 500)}`);
  }
  const json = await res.json();
  const text = json?.candidates?.[0]?.content?.parts?.map((p) => p.text).join('') || '';
  if (!text) throw new Error('Gemini returned an empty candidate (possibly blocked by safety settings)');
  return JSON.parse(text);
}

function stripTags(html) {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function countWords(html) {
  return (stripTags(html).match(/[A-Za-z0-9'’]+/g) || []).length;
}

function countExternalLinks(html) {
  const urls = [...html.matchAll(/<a\s[^>]*href="([^"]+)"/gi)].map((m) => m[1]);
  return urls.filter((u) => /^https?:\/\//i.test(u) && !/unsplash\.com|helloinsights\.online/i.test(u)).length;
}

function validateDraft(d) {
  const problems = [];
  const words = countWords(d.body_html || '');
  const h2 = (d.body_html || '').match(/<h2\b/gi)?.length || 0;
  const cites = countExternalLinks(d.body_html || '');

  if (words < 700) problems.push(`字数不足：${words} 词（要求 ≥1100，硬下限 700）`);
  if (h2 < 3) problems.push(`H2 小节只有 ${h2} 个（要求 ≥4）`);
  if (cites < 2) problems.push(`正文引用只有 ${cites} 个（要求 ≥2）`);
  if (!/<\/(ul|ol)>/i.test(d.body_html || '')) problems.push('没有列表');
  if (/<h1\b/i.test(d.body_html || '')) problems.push('正文里出现了 H1');
  if (/<script|<style/i.test(d.body_html || '')) problems.push('正文含 script/style');
  if ((d.title || '').length > 75) problems.push(`标题 ${d.title.length} 字符，过长`);

  const lower = stripTags(d.body_html || '').toLowerCase();
  const banned = BANNED_PHRASES.filter((p) => lower.includes(p));
  if (banned.length) problems.push(`命中禁用句式：${banned.join('、')}`);

  return { problems, words, h2, cites };
}

function toArticle(draft, brief) {
  const today = new Date().toISOString().slice(0, 10);
  const faqHtml = (draft.faq || [])
    .map((f) => `<h3>${f.question}</h3>\n${f.answer_html}`)
    .join('\n');

  const sourcesHtml = (draft.sources || []).length
    ? `<h2>Sources</h2>\n<ul>\n${draft.sources
        .map((s) => `<li><a href="${s.url}" rel="noopener" target="_blank">${s.title || s.url}</a></li>`)
        .join('\n')}\n</ul>`
    : '';

  const disclaimer = brief.ymyl
    ? `<p><em>This article is for general information only. ${
        brief.category === 'finance'
          ? 'It is not investment advice and does not take into account your personal circumstances.'
          : 'It is not medical advice; consult a qualified professional before making health decisions.'
      }</em></p>`
    : '';

  const content = [
    draft.body_html,
    faqHtml ? `<h2>FAQ</h2>\n${faqHtml}` : '',
    sourcesHtml,
    disclaimer,
  ]
    .filter(Boolean)
    .join('\n');

  return {
    id: String(Date.now()).slice(-8),
    category: brief.category,
    title: draft.title,
    excerpt: draft.excerpt || draft.meta_description,
    image: `https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&h=450&fit=crop&fm=webp&q=80`,
    date: today,
    content,
    _meta: {
      slug: brief.slug,
      meta_description: draft.meta_description,
      keywords: draft.keywords || brief.keywords || [],
      sources: draft.sources || [],
      tags: draft.tags || [],
      brief_issue: brief.issue || null,
      model: MODEL,
      generated_at: new Date().toISOString(),
    },
  };
}

function toMarkdown(article, brief) {
  const body = (article.content || '')
    .replace(/<h2[^>]*>/gi, '\n## ')
    .replace(/<h3[^>]*>/gi, '\n### ')
    .replace(/<\/h[23]>/gi, '\n')
    .replace(/<li[^>]*>/gi, '\n- ')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<a\s[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/gi, '[$2]($1)')
    .replace(/<(strong|em)[^>]*>(.*?)<\/\1>/gi, '**$2**')
    .replace(/<[^>]+>/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return [
    `# ${article.title}`,
    '',
    `> ${article.excerpt}`,
    '',
    `分类：\`${article.category}\` · 简报：#${brief.issue || '-'} · 模型：\`${MODEL}\``,
    '',
    body,
  ].join('\n');
}

async function main() {
  const args = process.argv.slice(2);
  const get = (flag) => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : null;
  };
  const briefPath = get('--brief');
  const outPath = get('--out');
  const dryRun = args.includes('--dry-run');

  if (!briefPath) {
    console.error('用法：node tools/gemini_generate.mjs --brief content/briefs/x.json [--out content/drafts/x.json] [--dry-run]');
    process.exit(2);
  }

  const brief = readJSON(briefPath);
  const slug = brief.slug || 'draft';
  const out = outPath || path.join('content', 'drafts', `${slug}.json`);
  const prompt = buildPrompt(brief);

  if (dryRun) {
    console.log('--- PROMPT ---\n' + prompt);
    return;
  }
  if (!API_KEY) {
    console.error('缺少 GEMINI_API_KEY。把 Google AI Studio 的 key 加到仓库 Secrets（Settings → Secrets → Actions）。');
    process.exit(3);
  }

  let draft = null;
  let report = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const candidate = await callGemini(prompt, attempt);
    const check = validateDraft(candidate);
    if (!check.problems.length) {
      draft = candidate;
      report = check;
      break;
    }
    console.error(`第 ${attempt + 1} 次生成未通过硬性校验：\n- ${check.problems.join('\n- ')}`);
    report = check;
    if (attempt === 1) {
      console.error('两次均未通过，放弃。');
      process.exit(4);
    }
  }

  const article = toArticle(draft, brief);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(article, null, 2), 'utf8');

  const mdPath = out.replace(/\.json$/, '.md');
  fs.writeFileSync(mdPath, toMarkdown(article, brief), 'utf8');

  console.log(`draft: ${out}`);
  console.log(`preview: ${mdPath}`);
  console.log(`words: ${report.words} · H2: ${report.h2} · citations: ${report.cites}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
