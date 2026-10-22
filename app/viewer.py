"""The resume viewer: its page and the base resume it shows beside each generated one.

The page is served only where API docs are enabled (the tailnet-only docs listener) and holds no data
itself: on load it reads everything from the viewer's read endpoints, which need no API key.
"""
import threading
from pathlib import Path

from app.rendering import TEMPLATE_DIR, TEMPLATE_SUFFIXES, render_pdf


class BaseResumeCache:
    """The base resume PDF, rendered once and again whenever a template file changes.

    Keyed by the name, size and modification time of the files render_pdf copies, so the PDF is always
    the one POST /resume would save when it keeps the base resume.
    """

    def __init__(self, template_dir: Path = TEMPLATE_DIR):
        self._dir = Path(template_dir)
        self._lock = threading.Lock()
        self._key = None
        self._pdf = None

    def _fingerprint(self) -> tuple:
        files = sorted(p for p in self._dir.iterdir() if p.is_file() and p.suffix.lower() in TEMPLATE_SUFFIXES)
        return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files)

    def get(self) -> bytes:
        """Raises RenderError when the base resume cannot be rendered."""
        with self._lock:  # one render at a time; concurrent requests wait for it rather than render too
            key = self._fingerprint()
            if self._pdf is None or key != self._key:
                self._pdf, self._key = render_pdf(template_dir=self._dir), key
            return self._pdf


def content_security_policy(nonce: str) -> str:
    """Only the page's own nonce-tagged script and style run; data comes from this origin; PDFs show in
    frames from blob: URLs the page makes itself."""
    return "; ".join([
        "default-src 'none'",
        f"script-src 'nonce-{nonce}'",
        f"style-src 'nonce-{nonce}'",
        "connect-src 'self'",
        "frame-src blob:",
        "object-src blob:",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ])


def page(nonce: str) -> str:
    return PAGE.replace("__NONCE__", nonce)


# Everything inline, nothing from another origin. Data is inserted with textContent only, never innerHTML,
# so posting text and resume content can never become markup.
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Resume viewer</title>
<style nonce="__NONCE__">
:root {
  --bg: #f6f7f9; --panel: #ffffff; --text: #1d2330; --muted: #5d6676; --line: #dde1e7;
  --accent: #2f5bd3; --accent-soft: #e6ecfb; --good: #1f7a45; --good-soft: #e3f4ea;
  --warn: #9a5b00; --warn-soft: #fdf1dc; --bad: #b3261e; --bad-soft: #fbe7e5;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151b; --panel: #1b1f27; --text: #e6e9ef; --muted: #9aa3b2; --line: #2d333e;
    --accent: #8fb0ff; --accent-soft: #1f2a44; --good: #6fd19a; --good-soft: #17301f;
    --warn: #f0b75c; --warn-soft: #3a2c12; --bad: #ff8a80; --bad-soft: #3d1b19;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
h1 { font-size: 16px; margin: 0; }
h2 { font-size: 15px; margin: 0 0 8px; }
h3 { font-size: 13px; margin: 0 0 6px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
a { color: var(--accent); }
.hidden { display: none !important; }
.muted { color: var(--muted); }
header.top { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px;
  border-bottom: 1px solid var(--line); background: var(--panel); position: sticky; top: 0; z-index: 2; }
#load-error { max-width: 420px; margin: 12vh auto; padding: 24px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
#load-error button { margin-top: 12px; padding: 7px 14px; font: inherit; border: 1px solid var(--accent);
  background: var(--accent); color: #fff; border-radius: 6px; cursor: pointer; }
#load-error .error { color: var(--bad); margin: 0; }
#app { display: grid; grid-template-columns: 300px 1fr; height: calc(100% - 45px); }
#list { border-right: 1px solid var(--line); overflow-y: auto; background: var(--panel); }
#list button { display: block; width: 100%; text-align: left; padding: 10px 14px; border: 0; border-bottom: 1px solid var(--line);
  background: transparent; color: inherit; font: inherit; cursor: pointer; }
#list button:hover { background: var(--accent-soft); }
#list button[aria-current="true"] { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
#list .company { font-weight: 600; }
#list .meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; font-size: 12px; }
#detail { overflow-y: auto; padding: 16px; min-width: 0; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; background: var(--accent-soft); color: var(--accent); }
.badge.good { background: var(--good-soft); color: var(--good); }
.badge.warn { background: var(--warn-soft); color: var(--warn); }
.badge.bad { background: var(--bad-soft); color: var(--bad); }
.title-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 12px; }
.title-row .role { font-size: 18px; font-weight: 600; }
dl.fields { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 12px 0 0; }
dl.fields dt { color: var(--muted); }
dl.fields dd { margin: 0; overflow-wrap: anywhere; }
details > summary { cursor: pointer; }
pre.posting { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; max-height: 420px; overflow-y: auto;
  background: var(--bg); padding: 10px; border-radius: 6px; margin: 8px 0 0; }
.scores { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.score { border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.score .value { font-size: 30px; font-weight: 700; line-height: 1.1; }
.score.pass .value { color: var(--good); }
.score.fail .value { color: var(--bad); }
.bar { height: 6px; background: var(--line); border-radius: 3px; margin: 4px 0 8px; overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--accent); }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
ul.items { margin: 0; padding-left: 18px; }
ul.items li { margin: 3px 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.req { border-top: 1px solid var(--line); padding: 8px 0; }
.req:first-of-type { border-top: 0; }
.req summary { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.req .evidence { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; }
.req blockquote { margin: 4px 0; padding: 4px 10px; border-left: 3px solid var(--line); color: var(--muted); }
.panes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; }
.pane header { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--line); }
.pane iframe { width: 100%; height: 1100px; border: 0; background: #fff; }
.pane .empty { padding: 40px 16px; text-align: center; color: var(--muted); }
.note { padding: 8px 12px; border-radius: 6px; background: var(--warn-soft); color: var(--warn); margin-bottom: 12px; }
@media (max-width: 1100px) {
  .panes, .columns, .req .evidence { grid-template-columns: 1fr; }
}
@media (max-width: 800px) {
  #app { grid-template-columns: 1fr; height: auto; }
  #list { max-height: 40vh; border-right: 0; border-bottom: 1px solid var(--line); }
  .pane iframe { height: 80vh; }
}
</style>
</head>
<body>
<header class="top">
  <h1>Resume viewer</h1>
  <span id="status" class="muted"></span>
</header>

<div id="load-error" class="hidden" role="alert">
  <p id="load-error-message" class="error"></p>
  <button id="retry" type="button">Try again</button>
</div>

<div id="app" class="hidden">
  <nav id="list" aria-label="Applications"></nav>
  <main id="detail"><p class="muted">Select an application.</p></main>
</div>

<script nonce="__NONCE__">
"use strict";
(() => {
  const STATUS_LABEL = {
    tailored: "Tailored",
    base_meets_threshold: "Base kept",
    no_job_description: "Not scored",
  };
  const RANK = { missing: 0, partial: 1, met: 2 };
  let applications = [];
  let selected = null;
  let baseUrl = null;          // blob: URL of the base resume, fetched once per page load
  let generatedUrl = null;     // blob: URL of the selected application's resume
  let loadToken = 0;           // ignores responses for an application no longer selected

  const $ = (id) => document.getElementById(id);

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (name === "class") node.className = value;
      else node.setAttribute(name, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function safeLink(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "https:" || parsed.protocol === "http:") {
        return el("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer" }, url);
      }
    } catch (_) { /* not a URL */ }
    return document.createTextNode(url);
  }

  function when(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    return isNaN(date) ? iso : date.toLocaleString();
  }

  function percent(fraction) {
    return Math.round((fraction || 0) * 100) + "%";
  }

  async function api(path, asBlob) {
    const response = await fetch(path, { cache: "no-store", credentials: "omit" });
    if (!response.ok) {
      let message = response.status + " " + response.statusText;
      try { message = (await response.json()).message || message; } catch (_) { /* not JSON */ }
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return asBlob ? response.blob() : response.json();
  }

  // --- the list ---

  function statusBadge(report) {
    if (!report) return el("span", { class: "badge warn" }, "No report");
    const kind = report.status === "tailored" ? "good" : report.status === "no_job_description" ? "warn" : "";
    return el("span", { class: "badge " + kind }, STATUS_LABEL[report.status] || report.status);
  }

  function scoreText(report) {
    if (!report || report.base_score === null || report.base_score === undefined) return null;
    const generated = report.status === "tailored" ? report.tailored_score : report.base_score;
    return report.base_score + " → " + generated;
  }

  function renderList() {
    const nav = $("list");
    nav.replaceChildren();
    if (!applications.length) {
      nav.append(el("p", { class: "muted" }, "No applications recorded."));
      return;
    }
    for (const item of applications) {
      const score = scoreText(item.report);
      nav.append(el("button", { type: "button", "data-id": item.id, "aria-current": item.id === selected ? "true" : "false" },
        el("div", { class: "company" }, item.company),
        el("div", {}, item.role),
        el("div", { class: "meta" },
          el("span", { class: "badge" }, item.status),
          statusBadge(item.report),
          score ? el("span", { class: "muted" }, score) : null,
        ),
      ));
    }
  }

  async function loadList() {
    $("status").textContent = "Loading…";
    const body = await api("/applications");
    applications = body.applications;
    $("app").classList.remove("hidden");
    $("status").textContent = applications.length + (applications.length === 1 ? " application" : " applications");
    renderList();
    const wanted = location.hash.slice(1);
    if (wanted && applications.some((a) => a.id === wanted)) select(wanted);
  }

  // --- the detail ---

  function detailsCard(app) {
    const fields = [
      ["Status", app.status], ["Location", app.location], ["Work type", app.work_type], ["Salary", app.salary],
      ["Posted", app.date_posted], ["Sponsorship", app.sponsorship], ["Why it fits", app.why_it_fits],
      ["Job link", app.job_link && safeLink(app.job_link)],
      ["Careers page", app.company_careers_url && safeLink(app.company_careers_url)],
      ["Employer domain", app.official_employer_domain],
      ["Recorded", when(app.created_at)], ["Updated", when(app.updated_at)],
    ].filter(([, value]) => value);
    return el("section", { class: "card" },
      el("div", { class: "title-row" }, el("span", { class: "role" }, app.role), el("span", {}, app.company)),
      el("dl", { class: "fields" }, fields.map(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
      app.full_job_description
        ? el("details", { class: "posting-wrap" }, el("summary", {}, "Posting text"), el("pre", { class: "posting" }, app.full_job_description))
        : null,
    );
  }

  function scoreCard(label, breakdown, threshold) {
    const pass = breakdown.score >= threshold;
    const meter = (name, value) => [
      el("div", { class: "muted" }, name + " " + percent(value)),
      el("div", { class: "bar" }, el("span", { class: "fill", "data-width": percent(value) })),
    ];
    return el("div", { class: "score " + (pass ? "pass" : "fail") },
      el("h3", {}, label),
      el("div", { class: "value" }, breakdown.score),
      el("div", { class: "muted" }, pass ? "At or above " + threshold : "Below " + threshold),
      meter("Keywords", breakdown.keyword_coverage),
      meter("Requirements", breakdown.requirement_coverage),
    );
  }

  function scoresCard(report) {
    const card = el("section", { class: "card" }, el("h2", {}, "Match against the posting"));
    if (report.status === "no_job_description") {
      card.append(el("p", { class: "muted" }, "Not scored: the posting text was missing or too short to score, so the base resume was saved."));
      return card;
    }
    const generated = report.tailored || report.base;
    card.append(
      el("p", { class: "muted" }, "Threshold " + report.threshold + ". Generated " + when(report.generated_at) + "."),
      el("div", { class: "scores" },
        scoreCard("Base", report.base, report.threshold),
        scoreCard(report.tailored ? "Generated (tailored)" : "Generated (base kept)", generated, report.threshold)),
    );
    return card;
  }

  function improvements(report) {
    if (!report.tailored) return [];
    const before = Object.fromEntries(report.base.requirements.map((r) => [r.id, r]));
    return report.tailored.requirements.filter((r) => before[r.id] && RANK[r.counted] > RANK[before[r.id].counted])
      .map((r) => ({ requirement: r, from: before[r.id].counted }));
  }

  function addedCard(report) {
    const card = el("section", { class: "card" }, el("h2", {}, "What was added"));
    const improved = improvements(report);
    if (report.status !== "tailored" || (!report.added_terms.length && !improved.length)) {
      card.append(el("p", { class: "muted" }, report.status === "tailored"
        ? "No keywords were added and no requirement improved; the wording and order changed."
        : "Nothing was added: the generated resume is the base resume unchanged."));
      return card;
    }
    if (report.added_terms.length) {
      card.append(el("h3", {}, "Keywords"), el("div", { class: "chips" },
        report.added_terms.map((term) => el("span", { class: "badge good" }, term))));
    }
    if (improved.length) {
      card.append(el("h3", {}, "Requirements"), el("ul", { class: "items" }, improved.map(({ requirement, from }) =>
        el("li", {}, requirement.text + " ", el("span", { class: "muted" }, from + " → " + requirement.counted)))));
    }
    return card;
  }

  function gapsCard(report) {
    const generated = report.tailored || report.base;
    const missingKeywords = generated.keywords.filter((k) => !k.present);
    const weak = generated.requirements.filter((r) => r.counted !== "met");
    const card = el("section", { class: "card" }, el("h2", {}, "Gaps still found"));
    if (!missingKeywords.length && !weak.length && !report.rejected_terms.length) {
      card.append(el("p", { class: "muted" }, "None: every posting keyword and requirement is covered."));
      return card;
    }
    if (missingKeywords.length) {
      card.append(el("h3", {}, "Keywords not in the generated resume"), el("ul", { class: "items" },
        missingKeywords.map((k) => el("li", {}, k.term + " ", el("span", { class: "muted" }, "(" + k.importance + ")")))));
    }
    if (weak.length) {
      card.append(el("h3", {}, "Requirements not fully met"), el("ul", { class: "items" }, weak.map((r) =>
        el("li", {}, r.text + " ",
          el("span", { class: "badge " + (r.counted === "partial" ? "warn" : "bad") }, r.counted),
          el("span", { class: "muted" }, " (" + r.importance + ")")))));
    }
    if (report.rejected_terms.length) {
      card.append(el("h3", {}, "Keywords the judge rejected"), el("ul", { class: "items" }, report.rejected_terms.map((t) =>
        el("li", {}, t.term + " ", el("span", { class: "muted" }, "— " + t.reason)))));
    }
    return card;
  }

  function statusBadgeFor(counted) {
    return el("span", { class: "badge " + (counted === "met" ? "good" : counted === "partial" ? "warn" : "bad") }, counted);
  }

  function evidence(label, row) {
    const quotes = row ? row.evidence : [];
    return el("div", {},
      el("h3", {}, label),
      row && row.unverified ? el("p", { class: "muted" }, "Assessed " + row.status + ", counted missing: " + row.reason) : null,
      quotes.length ? quotes.map((q) => el("blockquote", {}, q)) : el("p", { class: "muted" }, "No quoted evidence."),
    );
  }

  function requirementsCard(report) {
    const tailored = report.tailored ? Object.fromEntries(report.tailored.requirements.map((r) => [r.id, r])) : null;
    return el("section", { class: "card" },
      el("h2", {}, "Requirements, base vs generated"),
      report.base.requirements.map((base) => {
        const generated = tailored ? tailored[base.id] : base;
        return el("details", { class: "req" },
          el("summary", {},
            el("strong", {}, base.id),
            el("span", {}, base.text),
            el("span", { class: "muted" }, base.importance),
            statusBadgeFor(base.counted), "→", statusBadgeFor(generated ? generated.counted : "missing")),
          el("div", { class: "evidence" }, evidence("Base", base), evidence("Generated", generated)));
      }),
    );
  }

  function pane(label, note) {
    const body = el("div", { class: "empty" }, "Loading…");
    const node = el("section", { class: "pane" },
      el("header", {}, el("strong", {}, label), note ? el("span", { class: "muted" }, note) : el("span", {})),
      body);
    return { node, body, header: node.querySelector("header") };
  }

  function showPdf(target, url, title) {
    // Fit the page width and hide the thumbnail sidebar in the browser's own PDF viewer.
    target.body.replaceWith(el("iframe", { src: url + "#navpanes=0&view=FitH", title }));
    target.header.append(el("a", { href: url, target: "_blank", rel: "noopener" }, "Open in tab"));
  }

  function showEmpty(target, message) {
    target.body.replaceChildren(message);
  }

  async function loadPdfs(app, token, basePane, generatedPane, legacyNote) {
    try {
      if (!baseUrl) baseUrl = URL.createObjectURL(await api("/resume/base.pdf", true));
      if (token === loadToken) showPdf(basePane, baseUrl, "Base resume");
    } catch (error) {
      if (token === loadToken) showEmpty(basePane, "Base resume unavailable: " + error.message);
    }
    try {
      const blob = await api("/application/" + app.id + "/resume.pdf", true);
      if (token !== loadToken) return;
      generatedUrl = URL.createObjectURL(blob);
      showPdf(generatedPane, generatedUrl, "Generated resume");
    } catch (error) {
      if (token !== loadToken) return;
      if (error.status === 404) {
        showEmpty(generatedPane, "No resume has been generated for this application yet.");
        if (legacyNote) legacyNote.remove();  // nothing was generated, so there is no old resume to explain
      } else {
        showEmpty(generatedPane, "Resume unavailable: " + error.message);
      }
    }
  }

  function applyMeters(root) {
    // Widths go through the CSSOM, which the style policy allows, rather than style attributes, which it blocks.
    for (const fill of root.querySelectorAll(".fill")) fill.style.width = fill.getAttribute("data-width");
  }

  async function select(id) {
    selected = id;
    const token = ++loadToken;
    if (generatedUrl) { URL.revokeObjectURL(generatedUrl); generatedUrl = null; }
    if (location.hash.slice(1) !== id) history.replaceState(null, "", "#" + id);
    renderList();
    const detail = $("detail");
    detail.replaceChildren(el("p", { class: "muted" }, "Loading…"));
    let body;
    try {
      body = await api("/application/" + id);
    } catch (error) {
      if (token === loadToken) detail.replaceChildren(el("p", { class: "note" }, error.message));
      return;
    }
    if (token !== loadToken) return;
    const app = body.application;
    const report = body.report && body.report.version === 1 ? body.report : null;
    const parts = [detailsCard(app)];
    let generatedNote = null;
    let legacyNote = null;
    if (!report) {
      legacyNote = el("p", { class: "note" }, "No scoring report exists for this resume: it was generated before reports were kept. Generating the resume again creates one.");
      parts.push(legacyNote);
    } else {
      parts.push(scoresCard(report));
      if (report.base) parts.push(el("div", { class: "columns" }, addedCard(report), gapsCard(report)), requirementsCard(report));
      if (report.status !== "tailored") generatedNote = "Base resume unchanged";
    }
    const basePane = pane("Base");
    const generatedPane = pane("Generated", generatedNote);
    parts.push(el("div", { class: "panes" }, basePane.node, generatedPane.node));
    detail.replaceChildren(...parts);
    applyMeters(detail);
    detail.scrollTop = 0;
    loadPdfs(app, token, basePane, generatedPane, legacyNote);
  }

  // --- wiring ---

  async function start() {
    $("load-error").classList.add("hidden");
    try {
      await loadList();
    } catch (error) {
      $("status").textContent = "";
      $("load-error-message").textContent = "Could not load applications: " + error.message;
      $("load-error").classList.remove("hidden");
    }
  }

  $("retry").addEventListener("click", start);

  $("list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-id]");
    if (button) select(button.getAttribute("data-id"));
  });

  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (id && id !== selected && applications.some((a) => a.id === id)) select(id);
  });

  start();
})();
</script>
</body>
</html>
"""
