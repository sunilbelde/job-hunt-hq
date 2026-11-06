"""The resume viewer: its page and the base resume and cover letter it shows beside each generated one.

The page is served only where API docs are enabled (the installed service's local listener, reached only from the Mac) and holds no data
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


# Drafted and re-rendered only by the owner; the service serves it unchanged and never writes it.
BASE_COVER_LETTER = TEMPLATE_DIR / "COVER_LETTER.pdf"


def read_base_cover_letter() -> bytes | None:
    """The owner's base cover letter (data/COVER_LETTER.pdf), read again on every call, or None when it is missing or unreadable."""
    try:
        return BASE_COVER_LETTER.read_bytes()
    except OSError:
        return None


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
#app { display: grid; grid-template-columns: 320px 1fr; height: calc(100% - 45px); }
#side { display: flex; flex-direction: column; min-height: 0; border-right: 1px solid var(--line); background: var(--panel); }
#link-box { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px; border-bottom: 1px solid var(--line); }
#link-box input { flex: 1; min-width: 0; font: inherit; font-size: 13px; padding: 5px 8px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--panel); color: inherit; }
#link-box button { font: inherit; font-size: 13px; padding: 5px 10px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); color: inherit; cursor: pointer; }
#link-box button:disabled { opacity: 0.6; cursor: default; }
#link-note { flex-basis: 100%; margin: 0; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
#link-note.failed { color: var(--bad); }
#filters { display: grid; gap: 8px; padding: 12px; border-bottom: 1px solid var(--line); }
#filters input, #filters select, .actions select { font: inherit; font-size: 13px; padding: 5px 8px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--bg); color: var(--text); min-width: 0; }
#filter-search { width: 100%; }
#filters .filter-row { display: flex; align-items: center; gap: 8px; }
#filters .filter-row select { flex: 1; }
#filters .dates { display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr); align-items: center; gap: 6px;
  font-size: 12px; color: var(--muted); }
#filters .dates input { width: 100%; font-size: 12px; padding: 4px 6px; }
button.link { padding: 4px 2px; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
button.link:hover { text-decoration: underline; }
#list { flex: 1; overflow-y: auto; padding: 6px; }
#list > p { padding: 0 8px; }
#list button.entry { display: grid; gap: 2px; width: 100%; margin: 0 0 4px; padding: 9px 11px; text-align: left; border: 1px solid transparent;
  border-radius: 8px; background: transparent; color: inherit; font: inherit; cursor: pointer; }
#list button.entry:hover { background: var(--bg); border-color: var(--line); }
#list button.entry.current { background: var(--accent-soft); border-color: var(--accent); }
#list button.entry:focus-visible, .actions button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.entry .line { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; min-width: 0; }
.entry .company { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entry-score { flex: none; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.entry-score .pass { color: var(--good); }
.entry-score .fail { color: var(--bad); }
.entry .role { font-size: 13px; color: var(--muted); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.entry .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; margin-top: 4px; font-size: 12px; }
.entry .meta .badge { padding: 0 7px; font-size: 11.5px; line-height: 18px; }
.entry .date { margin-left: auto; color: var(--muted); white-space: nowrap; }
.pill { display: inline-block; padding: 0 7px; border: 1px solid currentColor; border-radius: 999px; font-size: 11.5px; line-height: 16px; }
.pill.s-verified, .pill.s-withdrawn { color: var(--muted); }
.pill.s-applied { color: var(--accent); }
.pill.s-interviewing { color: var(--warn); }
.pill.s-offer { color: var(--good); }
.pill.s-rejected { color: var(--bad); }
.pill.origin { color: var(--muted); border-style: dashed; }
.pill.origin.o-link { color: var(--accent); }
.pill.easy-apply { color: var(--accent); }
.running { display: inline-flex; align-items: center; gap: 5px; color: var(--accent); }
.dot { display: inline-block; flex: none; width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .25; } }
@media (prefers-reduced-motion: reduce) { .dot { animation: none; } }
#list button.clear-filters { margin: 0 8px; padding: 4px 12px; font: inherit; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); color: inherit; cursor: pointer; }
.actions { position: sticky; top: -16px; z-index: 1; margin: -16px -16px 14px; padding: 12px 16px; background: var(--panel);
  border-bottom: 1px solid var(--line); }
.actions .title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }
.actions .title .role { font-size: 17px; font-weight: 600; }
.actions .title .company { color: var(--muted); }
.actions .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }
.actions .field { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.actions .spacer { flex: 1; }
button.action { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; font: inherit; font-size: 13px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel); color: var(--text); cursor: pointer; }
button.action:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
button.action.busy { color: var(--accent); }
button.action:disabled, .actions select:disabled { opacity: .6; cursor: default; }
.actions button.danger { background: transparent; }
.action-note { margin: 8px 0 0; min-height: 1.2em; font-size: 12px; color: var(--good); }
.action-note.error { color: var(--bad); }
#detail { overflow-y: auto; padding: 16px; min-width: 0; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; background: var(--accent-soft); color: var(--accent); }
.badge.good { background: var(--good-soft); color: var(--good); }
.badge.warn { background: var(--warn-soft); color: var(--warn); }
.badge.bad { background: var(--bad-soft); color: var(--bad); }
.card > h2:first-child { margin-bottom: 4px; }
dl.fields { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0 0; }
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
.switch { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; margin-bottom: 12px; background: var(--panel); }
.switch button { padding: 6px 14px; border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; }
.switch button + button { border-left: 1px solid var(--line); }
.switch button[aria-pressed="true"] { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.panes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; }
.pane header { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--line); }
.pane iframe { width: 100%; height: 1100px; border: 0; background: #fff; }
.pane .empty { padding: 40px 16px; text-align: center; color: var(--muted); }
button.danger { padding: 4px 12px; font: inherit; border: 1px solid var(--bad); background: var(--bad-soft);
  color: var(--bad); border-radius: 6px; cursor: pointer; }
button.danger:hover { background: var(--bad); color: var(--panel); }
button.danger:disabled { opacity: .6; cursor: default; }
.note { padding: 8px 12px; border-radius: 6px; background: var(--warn-soft); color: var(--warn); margin-bottom: 12px; }
@media (max-width: 1100px) {
  .panes, .columns, .req .evidence { grid-template-columns: 1fr; }
}
@media (max-width: 800px) {
  #app { grid-template-columns: 1fr; height: auto; }
  #side { max-height: 50vh; border-right: 0; border-bottom: 1px solid var(--line); }
  .actions { position: static; }
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
  <aside id="side">
    <form id="link-box" aria-label="Apply from a job link">
      <input id="link-input" type="text" inputmode="url" autocomplete="off" placeholder="Job link" aria-label="Job link">
      <button id="link-go" type="submit">Apply from link</button>
      <p id="link-note" class="hidden" role="status"></p>
    </form>
    <div id="filters" role="search" aria-label="Filter applications">
      <input id="filter-search" type="search" placeholder="Search company or role" aria-label="Search company or role" autocomplete="off">
      <div class="filter-row">
        <select id="filter-status" aria-label="Status"><option value="">All statuses</option></select>
        <button id="filter-clear" type="button" class="link hidden">Clear</button>
      </div>
      <div class="dates">
        <span>Recorded</span>
        <input id="filter-from" type="date" aria-label="Recorded from" title="Recorded from">
        <input id="filter-to" type="date" aria-label="Recorded to" title="Recorded to">
      </div>
    </div>
    <nav id="list" aria-label="Applications"></nav>
  </aside>
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
  const APPLICATION_STATUSES = ["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"];
  let applications = [];
  let selected = null;
  let baseUrl = null;          // blob: URL of the base resume, fetched once per page load
  let generatedUrl = null;     // blob: URL of the selected application's resume
  let baseLetterUrl = null;    // blob: URL of the base cover letter, fetched once per page load
  let generatedLetterUrl = null;  // blob: URL of the selected application's cover letter
  let loadToken = 0;           // ignores responses for an application no longer selected
  let detailStatus = null;     // the selected application's status text in the details
  const filters = { q: "", status: "", from: "", to: "" };  // "from" and "to" are YYYY-MM-DD recorded days
  const notes = {};            // application ID → { text, error }: its last action's note, shown in its action bar
  const busy = new Set();      // application IDs with a status, fill or delete request in flight
  const KINDS = ["resume", "cover_letter"];
  const KIND = {
    resume: { label: "resume", title: "Resume", short: "Resume", path: "resume" },
    cover_letter: { label: "cover letter", title: "Cover letter", short: "Letter", path: "cover-letter" },
  };
  const POLL_MS = 5000;        // how often the list is re-read while a job runs
  const LINK_WATCH_MS = 15 * 60 * 1000;  // how long after a link is started the list keeps being re-read
  const ADDED_VIA = { link: "ByLink", manual: "Manual" };
  const EASY_APPLY = "linkedin_easy_apply";  // no form to fill: the owner applies on LinkedIn
  let linkWatchUntil = 0;      // until then a link session may still record its application
  const starting = new Set();  // "<id>:<kind>" with a generation request in flight
  const known = {};            // application ID → { resume, cover_letter }: generated PDFs this page has loaded
  let bar = null;              // the selected application's action bar
  let currentDoc = "resume";   // the document view shown: "resume" or "letter"
  let letterView = null;       // the selected application's cover letter panes and whether they are loaded
  let pollTimer = null;
  let listEpoch = 0;           // bumped by every write, so a poll that started before it cannot undo it

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

  // Writes send their body as JSON; the server refuses any other content type.
  async function api(path, asBlob, { method = "GET", body } = {}) {
    const init = { method, cache: "no-store", credentials: "omit" };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const response = await fetch(path, init);
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

  function itemOf(id) {
    return applications.find((item) => item.id === id) || null;
  }

  function jobOf(id, kind) {
    const item = itemOf(id);
    return item && item.jobs ? item.jobs[kind] : null;
  }

  function isRunning(job) {
    return Boolean(job && job.status === "running");
  }

  function statusBadge(report) {
    if (!report) return el("span", { class: "badge warn" }, "No report");
    const kind = report.status === "tailored" ? "good" : report.status === "no_job_description" ? "warn" : "";
    return el("span", { class: "badge " + kind }, STATUS_LABEL[report.status] || report.status);
  }

  // "38 → 61", the generated score coloured against the threshold.
  function scoreNode(report) {
    if (!report || report.base_score === null || report.base_score === undefined) return null;
    const generated = report.status === "tailored" ? report.tailored_score : report.base_score;
    return el("span", { class: "entry-score" }, report.base_score + " → ",
      el("strong", { class: generated >= report.threshold ? "pass" : "fail" }, generated));
  }

  function localDay(iso) {
    const date = new Date(iso);
    if (isNaN(date)) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
  }

  function shortDay(iso) {
    const date = new Date(iso);
    return isNaN(date) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function filtering() {
    return Boolean(filters.q.trim() || filters.status || filters.from || filters.to);
  }

  // Recorded is when the application was stored (created_at), never when the job was posted.
  function matches(item) {
    const q = filters.q.trim().toLowerCase();
    if (q && !item.company.toLowerCase().includes(q) && !item.role.toLowerCase().includes(q)) return false;
    if (filters.status && item.status !== filters.status) return false;
    const day = localDay(item.created_at);
    if (filters.from && day < filters.from) return false;
    if (filters.to && day > filters.to) return false;
    return true;
  }

  function updateCount() {
    const total = applications.length;
    const noun = total === 1 ? " application" : " applications";
    $("status").textContent = filtering() ? applications.filter(matches).length + " of " + total + noun : total + noun;
    $("filter-clear").classList.toggle("hidden", !filtering());
  }

  function clearFilters() {
    filters.q = filters.status = filters.from = filters.to = "";
    $("filter-search").value = $("filter-status").value = $("filter-from").value = $("filter-to").value = "";
    renderList();
  }

  function runningNote(item) {
    const kinds = KINDS.filter((kind) => isRunning(item.jobs && item.jobs[kind]));
    if (!kinds.length) return null;
    return el("span", { class: "running" }, el("span", { class: "dot", "aria-hidden": "true" }),
      kinds.map((kind) => KIND[kind].short + "…").join(" "));
  }

  // One button per application: it only selects. Every action is in the selected application's action bar.
  function entry(item) {
    const current = item.id === selected;
    return el("button", { type: "button", class: current ? "entry current" : "entry", "data-id": item.id,
                          "aria-current": current ? "true" : "false" },
      el("span", { class: "line" }, el("span", { class: "company" }, item.company), scoreNode(item.report)),
      el("span", { class: "role" }, item.role),
      el("span", { class: "meta" },
        el("span", { class: "pill s-" + item.status }, item.status),
        el("span", { class: "pill origin o-" + item.added_via, title: "How this posting was added" },
          ADDED_VIA[item.added_via]),
        item.posting_source_type === EASY_APPLY
          ? el("span", { class: "pill easy-apply", title: "No official posting: apply on LinkedIn yourself" }, "Easy Apply")
          : null,
        statusBadge(item.report),
        runningNote(item),
        el("span", { class: "date", title: "Recorded " + when(item.created_at) }, shortDay(item.created_at)),
      ),
    );
  }

  function renderList() {
    const nav = $("list");
    nav.replaceChildren();
    updateCount();
    if (!applications.length) {
      nav.append(el("p", { class: "muted" }, "No applications recorded."));
      return;
    }
    const shown = applications.filter(matches);
    if (!shown.length) {
      nav.append(el("p", { class: "muted" }, "No applications match these filters."),
        el("button", { type: "button", class: "clear-filters" }, "Clear filters"));
      return;
    }
    nav.append(...shown.map(entry));
  }

  async function loadList() {
    $("status").textContent = "Loading…";
    const body = await api("/applications");
    applications = body.applications;
    $("app").classList.remove("hidden");
    renderList();
    schedulePoll();
    const wanted = location.hash.slice(1);
    if (wanted && applications.some((a) => a.id === wanted)) select(wanted);
  }

  // --- job progress ---

  function anyRunning() {
    return applications.some((item) => KINDS.some((kind) => isRunning(item.jobs && item.jobs[kind])));
  }

  // One timer at a time, and only while some job runs or a link session may still record its application.
  function schedulePoll() {
    if (pollTimer === null && (anyRunning() || Date.now() < linkWatchUntil)) pollTimer = setTimeout(poll, POLL_MS);
  }

  async function poll() {
    pollTimer = null;
    const epoch = listEpoch;
    let body;
    try {
      body = await api("/applications");
    } catch (_) {
      if (pollTimer === null) pollTimer = setTimeout(poll, POLL_MS);  // keep the last list and try again
      return;
    }
    if (epoch !== listEpoch) return schedulePoll();  // a write landed meanwhile; this list may predate it
    const before = new Map(applications.map((item) => [item.id, item.jobs || {}]));
    applications = body.applications;
    for (const item of applications) {
      for (const kind of KINDS) {
        const now = item.jobs && item.jobs[kind];
        if (isRunning((before.get(item.id) || {})[kind]) && now && !isRunning(now)) finished(item, kind, now);
      }
    }
    renderList();
    renderActions();
    schedulePoll();
  }

  function finished(item, kind, job) {
    const title = KIND[kind].title;
    if (job.status === "failed") {
      notes[item.id] = { text: title + " failed: " + (job.error || "unknown error"), error: true };
      return;  // the documents shown are still the current ones
    }
    (known[item.id] = known[item.id] || {})[kind] = true;
    notes[item.id] = { text: title + " generated" };
    if (item.id !== selected) return;
    if (kind === "resume") select(item.id, { keepDocument: true });  // new PDF, scores, additions and gaps
    else refreshLetters();
  }

  // --- the action bar ---

  function hasDocument(id, kind) {
    const item = itemOf(id);
    const job = jobOf(id, kind);
    return Boolean((job && job.status === "done") || (kind === "resume" && item && item.report)
      || (known[id] && known[id][kind]));
  }

  function actionBar(app) {
    const status = el("select", { "aria-label": "Status of " + app.company + " – " + app.role },
      APPLICATION_STATUSES.map((value) => el("option", { value, selected: value === app.status }, value)));
    status.addEventListener("change", () => changeStatus(app, status.value));
    const buttons = {};
    for (const kind of KINDS) {
      buttons[kind] = el("button", { type: "button", class: "action", "data-kind": kind });
      buttons[kind].addEventListener("click", () => startGeneration(app, kind));
    }
    const fill = el("button", { type: "button", class: "action",
      title: "Open a Claude Code tab in Herdr that fills this application's form" }, "Fill form");
    fill.addEventListener("click", () => fillForm(app));
    fill.classList.toggle("hidden", app.posting_source_type === EASY_APPLY);
    const del = el("button", { type: "button", class: "danger" }, "Delete");
    del.addEventListener("click", () => deleteApplication(app));
    const note = el("p", { class: "action-note", role: "status", "aria-live": "polite" });
    bar = { id: app.id, status, buttons, fill, del, note };
    const node = el("section", { class: "actions", "aria-label": "Actions" },
      el("div", { class: "title" }, el("span", { class: "role" }, app.role), el("span", { class: "company" }, app.company)),
      el("div", { class: "row" },
        el("label", { class: "field" }, "Status", status),
        buttons.resume, buttons.cover_letter, fill, el("span", { class: "spacer" }), del),
      note);
    renderActions();
    return node;
  }

  // Brings the action bar in line with the list, the requests in flight and the last note.
  function renderActions() {
    if (!bar || bar.id !== selected) return;
    const id = bar.id;
    const item = itemOf(id);
    const writing = busy.has(id);
    if (item && !writing) bar.status.value = item.status;
    bar.status.disabled = bar.fill.disabled = bar.del.disabled = writing;
    for (const kind of KINDS) {
      const running = isRunning(jobOf(id, kind));
      const pending = starting.has(id + ":" + kind);
      const button = bar.buttons[kind];
      button.disabled = running || pending;
      button.classList.toggle("busy", running || pending);
      button.replaceChildren(...(running || pending
        ? [el("span", { class: "dot", "aria-hidden": "true" }), (pending ? "Starting " : "Generating ") + KIND[kind].label + "…"]
        : [(hasDocument(id, kind) ? "Regenerate " : "Generate ") + KIND[kind].label]));
    }
    const note = notes[id];
    bar.note.textContent = note ? note.text : "";
    bar.note.classList.toggle("error", Boolean(note && note.error));
  }

  async function changeStatus(app, wanted) {
    busy.add(app.id);
    notes[app.id] = { text: "Saving…" };
    renderActions();
    try {
      const body = await api("/viewer/application/" + app.id, false, { method: "PATCH", body: { status: wanted } });
      listEpoch++;
      const item = itemOf(app.id);
      if (item) item.status = body.status;
      app.status = body.status;
      if (selected === app.id && detailStatus) detailStatus.textContent = body.status;
      notes[app.id] = { text: "Status saved" };
    } catch (error) {
      notes[app.id] = { text: "Not saved: " + error.message, error: true };  // the re-render shows the stored status
    } finally {
      busy.delete(app.id);
      renderList();
      renderActions();
    }
  }

  // Starts the same background job as the keyed API; regenerating asks first, since the new file replaces the old.
  async function startGeneration(app, kind) {
    const label = KIND[kind].label;
    if (hasDocument(app.id, kind) && !confirm("Regenerate the " + label + " for " + app.company + " – " + app.role
        + "? The new " + label + " replaces the current one when the run finishes.")) return;
    const key = app.id + ":" + kind;
    starting.add(key);
    notes[app.id] = { text: "Starting the " + label + "…" };
    renderActions();
    try {
      const body = await api("/viewer/application/" + app.id + "/" + KIND[kind].path, false, { method: "POST" });
      listEpoch++;
      const item = itemOf(app.id);
      if (item) {
        item.jobs = item.jobs || { resume: null, cover_letter: null };
        item.jobs[kind] = { status: "running", started_at: body.started_at, finished_at: null, error: null };
      }
      notes[app.id] = { text: KIND[kind].title + " started; it takes a few minutes" };
      schedulePoll();
    } catch (error) {
      notes[app.id] = { text: KIND[kind].title + " not started: " + error.message, error: true };
    } finally {
      starting.delete(key);
      renderList();
      renderActions();
    }
  }

  // Opens a Herdr tab running Claude Code with the form-filler skill for this application. Nothing is sent but
  // the ID; the session asks for anything else in its own tab, and never submits unless asked there.
  async function fillForm(app) {
    busy.add(app.id);
    notes[app.id] = { text: "Opening…" };
    renderActions();
    try {
      const body = await api("/viewer/application/" + app.id + "/fill", false, { method: "POST" });
      notes[app.id] = { text: (body.already_open ? "Already open in Herdr tab " : "Opened Herdr tab ") + body.tab_label };
    } catch (error) {
      notes[app.id] = { text: "Not opened: " + error.message, error: true };
    } finally {
      busy.delete(app.id);
      renderActions();
    }
  }

  function linkNote(text, failed) {
    $("link-note").textContent = text;
    $("link-note").classList.toggle("failed", failed);
    $("link-note").classList.remove("hidden");
  }

  // Opens a Herdr tab running Claude Code with the apply-from-link skill. The session records the application,
  // so the list is re-read for a while afterwards; a posting the session drops is reported only in its tab.
  async function applyFromLink(event) {
    event.preventDefault();
    const link = $("link-input").value.trim();
    if (!link || $("link-go").disabled) return;
    $("link-go").disabled = true;
    linkNote("Opening…", false);
    try {
      const body = await api("/viewer/apply-from-link", false, { method: "POST", body: { link } });
      linkNote((body.already_open ? "Already open in Herdr tab " : "Opened Herdr tab ") + body.tab_label, false);
      $("link-input").value = "";
      linkWatchUntil = Date.now() + LINK_WATCH_MS;
      schedulePoll();
    } catch (error) {
      linkNote("Not opened: " + error.message, true);
    } finally {
      $("link-go").disabled = false;
    }
  }

  async function deleteApplication(app) {
    if (!confirm("Delete " + app.company + " – " + app.role + "? This cannot be undone.")) return;
    busy.add(app.id);
    notes[app.id] = { text: "Deleting…" };
    renderActions();
    try {
      await api("/viewer/application/" + app.id, false, { method: "DELETE" });
    } catch (error) {
      busy.delete(app.id);
      notes[app.id] = { text: "Not deleted: " + error.message, error: true };
      renderActions();
      return;
    }
    listEpoch++;
    busy.delete(app.id);
    delete notes[app.id];
    removed(app.id);
  }

  function removed(id) {
    applications = applications.filter((a) => a.id !== id);
    if (selected === id) {
      selected = null;
      bar = letterView = null;
      loadToken++;  // drop any PDF still loading for it
      for (const url of [generatedUrl, generatedLetterUrl]) if (url) URL.revokeObjectURL(url);
      generatedUrl = generatedLetterUrl = null;
      history.replaceState(null, "", location.pathname + location.search);
      $("detail").replaceChildren(el("p", { class: "muted" }, "Select an application."));
    }
    renderList();
  }

  // --- the detail ---

  function detailsCard(app) {
    detailStatus = el("span", {}, app.status);
    const fields = [
      ["Status", detailStatus],["Location", app.location], ["Work type", app.work_type], ["Salary", app.salary],
      ["Posted", app.date_posted], ["Sponsorship", app.sponsorship], ["Why it fits", app.why_it_fits],
      ["Job link", app.job_link && safeLink(app.job_link)],
      ["Careers page", app.company_careers_url && safeLink(app.company_careers_url)],
      ["Employer domain", app.official_employer_domain],
      ["Recorded", when(app.created_at)], ["Updated", when(app.updated_at)],
    ].filter(([, value]) => value);
    return el("section", { class: "card" },
      el("h2", {}, "Details"),
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
      (known[app.id] = known[app.id] || {}).resume = true;
      renderActions();
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

  async function loadLetters(app, token, panes) {
    const basePane = pane("Base");
    const generatedPane = pane("Generated");
    panes.append(basePane.node, generatedPane.node);
    try {
      if (!baseLetterUrl) baseLetterUrl = URL.createObjectURL(await api("/cover-letter/base.pdf", true));
      if (token === loadToken) showPdf(basePane, baseLetterUrl, "Base cover letter");
    } catch (error) {
      if (token === loadToken) showEmpty(basePane, "Base cover letter unavailable: " + error.message);
    }
    try {
      const blob = await api("/application/" + app.id + "/cover-letter.pdf", true);
      if (token !== loadToken) return;
      generatedLetterUrl = URL.createObjectURL(blob);
      showPdf(generatedPane, generatedLetterUrl, "Generated cover letter");
      (known[app.id] = known[app.id] || {}).cover_letter = true;
      renderActions();
    } catch (error) {
      if (token !== loadToken) return;
      showEmpty(generatedPane, error.status === 404
        ? "No cover letter has been generated for this application yet."
        : "Cover letter unavailable: " + error.message);
    }
  }

  // Resume and cover letter panes share one spot; the letters are fetched only the first time they are shown.
  function documentSwitch(app, token, resumePanes, letterPanes) {
    const view = letterView = { app, token, panes: letterPanes, loaded: false };
    const resumeTab = el("button", { type: "button", "aria-pressed": "true", "data-doc": "resume" }, "Resume");
    const letterTab = el("button", { type: "button", "aria-pressed": "false", "data-doc": "letter" }, "Cover letter");
    const node = el("div", { class: "switch", role: "group", "aria-label": "Document" }, resumeTab, letterTab);
    function show(letter) {
      currentDoc = letter ? "letter" : "resume";
      resumeTab.setAttribute("aria-pressed", String(!letter));
      letterTab.setAttribute("aria-pressed", String(letter));
      resumePanes.classList.toggle("hidden", letter);
      letterPanes.classList.toggle("hidden", !letter);
      if (letter && !view.loaded) {
        view.loaded = true;
        loadLetters(app, token, letterPanes);
      }
    }
    node.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-doc]");
      if (button) show(button.getAttribute("data-doc") === "letter");
    });
    if (currentDoc === "letter") show(true);
    return node;
  }

  // A new cover letter for the selected application: fetch it now if the letters are shown, else on the next switch.
  function refreshLetters() {
    if (!letterView) return;
    if (generatedLetterUrl) { URL.revokeObjectURL(generatedLetterUrl); generatedLetterUrl = null; }
    letterView.panes.replaceChildren();
    letterView.loaded = currentDoc === "letter";
    if (letterView.loaded) loadLetters(letterView.app, letterView.token, letterView.panes);
  }

  function applyMeters(root) {
    // Widths go through the CSSOM, which the style policy allows, rather than style attributes, which it blocks.
    for (const fill of root.querySelectorAll(".fill")) fill.style.width = fill.getAttribute("data-width");
  }

  // keepDocument: reload after a finished job without leaving the document view or the scroll position.
  async function select(id, { keepDocument = false } = {}) {
    selected = id;
    detailStatus = null;
    bar = letterView = null;
    if (!keepDocument) currentDoc = "resume";
    const token = ++loadToken;
    if (generatedUrl) { URL.revokeObjectURL(generatedUrl); generatedUrl = null; }
    if (generatedLetterUrl) { URL.revokeObjectURL(generatedLetterUrl); generatedLetterUrl = null; }
    if (location.hash.slice(1) !== id) history.replaceState(null, "", "#" + id);
    renderList();
    const detail = $("detail");
    const scroll = detail.scrollTop;
    if (!keepDocument) detail.replaceChildren(el("p", { class: "muted" }, "Loading…"));
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
    const parts = [actionBar(app), detailsCard(app)];
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
    const resumePanes = el("div", { class: "panes" }, basePane.node, generatedPane.node);
    const letterPanes = el("div", { class: "panes hidden" });
    parts.push(documentSwitch(app, token, resumePanes, letterPanes), resumePanes, letterPanes);
    detail.replaceChildren(...parts);
    applyMeters(detail);
    detail.scrollTop = keepDocument ? scroll : 0;
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
  $("link-box").addEventListener("submit", applyFromLink);

  $("list").addEventListener("click", (event) => {
    if (event.target.closest("button.clear-filters")) return clearFilters();
    const button = event.target.closest("button.entry");
    if (button) select(button.getAttribute("data-id"));
  });
  $("filter-clear").addEventListener("click", clearFilters);
  $("filter-search").addEventListener("input", () => {
    filters.q = $("filter-search").value;
    renderList();
  });

  for (const value of APPLICATION_STATUSES) $("filter-status").append(el("option", { value }, value));
  for (const [key, id] of [["status", "filter-status"], ["from", "filter-from"], ["to", "filter-to"]]) {
    $(id).addEventListener("change", () => {
      filters[key] = $(id).value;
      renderList();
    });
  }

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
