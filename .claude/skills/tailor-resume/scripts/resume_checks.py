"""Checks on tailored content: the no-fabrication guards, compiling it into the base template, and
measuring the page.

Every finding is a dict with a `code`, an optional `where` (a skills line, a keyword or a bullet such as
"j2#1") and a `detail` that says what to change. Hard findings reject the content; soft ones are targets
and warnings the skill keeps revising toward.

The facts come from the base resume and the owner's profile facts (jN.fK), which a bullet of the same
job may cite like a base bullet. The one addition is the posting keywords the judge or a profile fact
approved (resume_terms.Terms), each only where its evidence allows it.
"""
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import pdfplumber

from resume_model import BaseResume, Content, ContentError, markup_to_plain, markup_to_tex, plain_to_tex, resume_text
from resume_score import keyword_present, normalize
from resume_terms import Terms

MAX_BULLET_CHARS = 400
MAX_SKILL_CHARS = 80
UNRENDERABLE = {"structure_mismatch", "invalid_text"}  # content with these cannot be compiled
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_WORD = re.compile(r"\w+")
ECHO_WORDS = 3  # soft: a run of this many words copied from the posting reads as pasted
ECHO_CONTENT_WORDS = 2  # ... when at least this many of them are not stopwords
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or our over than that the their this "
    "to via was we were what when which while who will with you your".split())

COMPILE_TIMEOUT = 90
MARGIN_PT = 36.0  # the 0.5 in geometry margins of BASE.tex
FILL_FLOOR = 0.90  # hard: share of the text area height the content must reach
FILL_TARGET = 0.96  # soft: below this the skill keeps revising
SHORT_LAST_LINE = 0.25  # soft: a wrapped bullet whose last line is narrower than this wastes a line
BULLET_GLYPHS = ("•", "∙", "·")
LINE_TOLERANCE_PT = 2.0

_OVERFULL = re.compile(r"Overfull \\hbox \((?P<by>[\d.]+)pt too wide\).*?at lines (?P<a>\d+)--(?P<b>\d+)")


def check_content(base: BaseResume, content: Content, keywords: list[dict],
                  terms: Terms | None = None, posting: str | None = None) -> tuple[list[dict], list[dict]]:
    """Hard findings and warnings for tailored content, checked against the base resume with its profile
    facts and the approved posting keywords (`terms`; None means none were). With the posting text, bullets
    that copy its phrasing are warned about too (`echoed_phrase`).

    The header, education, job headings and certifications are not in the content at all, so they
    cannot change; these checks cover what can.
    """
    terms = terms or Terms()
    errors, warnings = _structure(base, content), []
    if any(e["code"] == "structure_mismatch" for e in errors):
        return errors, warnings
    base_text = normalize(resume_text(base, base.content()))
    errors += _skills(base, content, base_text, terms)
    facts_text = "\n".join(normalize(markup_to_plain(f.text)) for job in base.jobs for f in job.facts)
    echoes = _grams(posting) if posting else set()
    bullet_errors, bullet_warnings = _bullets(base, content, f"{base_text}\n{facts_text}", terms, echoes)
    errors += bullet_errors
    warnings += bullet_warnings
    if not any(e["code"] == "invalid_text" for e in errors):
        errors += _keywords(base_text, normalize(resume_text(base, content)), keywords, terms)
        errors += _placement(content, terms)
    return errors, warnings


def _structure(base: BaseResume, content: Content) -> list[dict]:
    errors = []
    expected = [job.id for job in base.jobs]
    if [job.id for job in content.jobs] != expected:
        errors.append({"code": "structure_mismatch", "detail": f"jobs must be {', '.join(expected)}, in that order"})
    for job in content.jobs:
        if not job.bullets:
            errors.append({"code": "structure_mismatch", "where": job.id, "detail": "needs at least one bullet"})
    labels = {normalize(line.label): line.label for line in base.skills}
    seen = set()
    if not content.skills:
        errors.append({"code": "structure_mismatch", "detail": "keep at least one skills line"})
    for line in content.skills:
        key = normalize(line.label)
        if key not in labels:
            errors.append({"code": "unknown_label", "where": f"skills:{line.label}",
                           "detail": f"use one of the base labels: {', '.join(labels.values())}"})
        elif key in seen:
            errors.append({"code": "structure_mismatch", "where": f"skills:{line.label}", "detail": "label used twice"})
        seen.add(key)
        if not line.items:
            errors.append({"code": "structure_mismatch", "where": f"skills:{line.label}", "detail": "has no items"})
    return errors


def _skills(base: BaseResume, content: Content, base_text: str, terms: Terms) -> list[dict]:
    errors = []
    base_items = {normalize(item) for line in base.skills for item in line.items} | terms.forms()
    for line in content.skills:
        for item in [line.label, *line.items]:
            problem = _text_problem(item, MAX_SKILL_CHARS, plain_to_tex)
            if problem:
                errors.append({"code": "invalid_text", "where": f"skills:{line.label}", "detail": f"{item!r} {problem}"})
        for item in line.items:
            key = normalize(item)
            if key and key not in base_items and not keyword_present(base_text, {"term": item}):
                errors.append({"code": "unknown_skill", "where": f"skills:{line.label}",
                               "detail": f"{item!r} is not in the base resume or an approved keyword; remove it"})
    return errors


def _bullets(base: BaseResume, content: Content, source_text: str, terms: Terms,
             posting_grams: set[tuple[str, ...]]) -> tuple[list[dict], list[dict]]:
    """`source_text`: the base resume and the profile facts, normalized, for the bold phrase check.
    `posting_grams`: the posting's word runs, for the echoed phrase check (empty to skip it)."""
    errors, warnings = [], []
    base_sources = base.sources()
    for job in content.jobs:
        for n, bullet in enumerate(job.bullets, 1):
            where = f"{job.id}#{n}"
            problem = _text_problem(bullet.text, MAX_BULLET_CHARS, markup_to_tex)
            if problem:
                errors.append({"code": "invalid_text", "where": where, "detail": problem})
                continue
            sources = []
            if not bullet.sources:
                errors.append({"code": "missing_source", "where": where,
                               "detail": f"cite the {job.id}.bN bullets or {job.id}.fN facts it comes from"})
            for source in bullet.sources:
                if source not in base_sources:
                    errors.append({"code": "missing_source", "where": where,
                                   "detail": f"{source} is not a base bullet or a profile fact"})
                elif base_sources[source][0].id != job.id:
                    errors.append({"code": "foreign_source", "where": where,
                                   "detail": f"{source} belongs to {base_sources[source][0].id}; a bullet stays under its own job"})
                else:
                    sources.append(markup_to_plain(base_sources[source][1].text))
            if sources:
                allowed = {n for text in sources for n in _NUMBER.findall(text)}
                extra = sorted(set(_NUMBER.findall(markup_to_plain(bullet.text))) - allowed)
                if extra:
                    errors.append({"code": "unsupported_number", "where": where,
                                   "detail": f"{', '.join(extra)} not in its sources; keep numbers exactly as in the sources"})
            for phrase in _echoes(bullet.text, " ".join(sources), posting_grams):
                warnings.append({"code": "echoed_phrase", "where": where,
                                 "detail": f'"{phrase}" is copied from the posting; describe the work in the '
                                           "owner's own words"})
            for phrase in _BOLD.findall(bullet.text):
                if not keyword_present(source_text, {"term": phrase}) and normalize(phrase) not in terms.forms():
                    warnings.append({"code": "new_bold_phrase", "where": where,
                                     "detail": f"**{phrase}** is not a phrase of the base resume or the profile facts; "
                                               "make sure it states the same fact"})
            if not bullet.text.endswith("."):
                warnings.append({"code": "no_final_period", "where": where, "detail": "base bullets end with a period"})
    return errors, warnings


def _words(text: str) -> list[str]:
    """Words for phrase matching: normalized, hyphens and slashes split, punctuation dropped."""
    return _WORD.findall(normalize(markup_to_plain(text)).replace("-", " ").replace("/", " "))


def _grams(text: str) -> set[tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i:i + ECHO_WORDS]) for i in range(len(words) - ECHO_WORDS + 1)}


def _echoes(bullet: str, sources: str, posting_grams: set[tuple[str, ...]]) -> list[str]:
    """The runs of the bullet's words that the posting has and its sources do not, each at least ECHO_WORDS
    long with ECHO_CONTENT_WORDS words that are not stopwords. Overlapping runs are joined into one phrase."""
    if not posting_grams:
        return []
    words, own = _words(bullet), _grams(sources)
    hits = [i for i in range(len(words) - ECHO_WORDS + 1)
            if (gram := tuple(words[i:i + ECHO_WORDS])) in posting_grams and gram not in own
            and sum(w not in STOPWORDS for w in gram) >= ECHO_CONTENT_WORDS]
    phrases, start, end = [], None, None
    for i in hits:
        if start is not None and i <= end:
            end = i + ECHO_WORDS
            continue
        if start is not None:
            phrases.append(" ".join(words[start:end]))
        start, end = i, i + ECHO_WORDS
    if start is not None:
        phrases.append(" ".join(words[start:end]))
    return phrases


def _keywords(base_text: str, tailored_text: str, keywords: list[dict], terms: Terms) -> list[dict]:
    errors = []
    approved = {normalize(a.term) for a in terms.approved}
    for kw in keywords:
        in_base, in_tailored = keyword_present(base_text, kw), keyword_present(tailored_text, kw)
        if in_tailored and not in_base and normalize(kw["term"]) not in approved:
            errors.append({"code": "unsupported_keyword", "where": kw["term"],
                           "detail": "the base resume never mentions it and the judge did not approve it; remove it"})
        elif in_base and not in_tailored:
            errors.append({"code": "lost_keyword", "where": kw["term"],
                           "detail": "the base resume mentions it and the posting asks for it; keep a mention"})
    return errors


def _placement(content: Content, terms: Terms) -> list[dict]:
    """An approved keyword may appear in a bullet only when the bullet cites a base bullet or fact holding
    its evidence. Skills lines may hold it anywhere (see _skills)."""
    errors = []
    for job in content.jobs:
        for n, bullet in enumerate(job.bullets, 1):
            text = normalize(markup_to_plain(bullet.text))
            for approved in terms.approved:
                if keyword_present(text, approved.keyword()) and not set(approved.sources) & set(bullet.sources):
                    errors.append({"code": "misplaced_keyword", "where": f"{job.id}#{n}",
                                   "detail": f"{approved.term!r} was approved for {approved.where()}; "
                                             "remove it from this bullet"})
    return errors


def check_coverage(plan, analysis: dict, base: BaseResume) -> list[dict]:
    """Hard findings for out/coverage.json, the run's plan for the requirements the base resume does not
    meet: {"R4": {"sources": ["j1.b1", "j1.f2"], "note": "..."}}. Every such requirement must be planned,
    with the base bullets and profile facts that show it (an empty list when none do)."""
    if plan is None:
        return [{"code": "coverage_plan", "detail": "write out/coverage.json first: each requirement the base "
                                                    "assessment does not mark met, with the bullets and facts that show it"}]
    if not isinstance(plan, dict):
        return [{"code": "coverage_plan", "detail": 'expected {"R1": {"sources": [...], "note": "..."}, ...}'}]
    errors = []
    ids = [req["id"] for req in analysis["requirements"]]
    weak = [rid for rid in ids if analysis["assessment"][rid]["status"] != "met"]
    known = base.sources()
    for rid in weak:
        if rid not in plan:
            errors.append({"code": "coverage_plan", "where": rid, "detail": "the base resume does not meet it; plan it"})
    for rid, entry in plan.items():
        if rid not in ids:
            errors.append({"code": "coverage_plan", "where": rid, "detail": "not a requirement of out/analysis.json"})
            continue
        sources = entry.get("sources") if isinstance(entry, dict) else None
        if not isinstance(sources, list) or not all(isinstance(x, str) for x in sources):
            errors.append({"code": "coverage_plan", "where": rid, "detail": 'expected {"sources": ["jN.bK", "jN.fK", ...]}'})
            continue
        unknown = [x for x in sources if x not in known]
        if unknown:
            errors.append({"code": "coverage_plan", "where": rid,
                           "detail": f"{', '.join(unknown)} is not a base bullet or a profile fact"})
    return errors


def planned_not_met(plan, assessment: dict) -> list[str]:
    """Lines for `run score tailored`: planned requirements with sources that the tailored assessment does
    not mark met."""
    if not isinstance(plan, dict):
        return []
    lines = []
    for rid, entry in plan.items():
        sources = entry.get("sources") if isinstance(entry, dict) else None
        status = (assessment.get(rid) or {}).get("status")
        if sources and status != "met":
            lines.append(f"planned, not met: {rid} ({', '.join(sources)}); assessed {status or 'missing'}")
    return lines


def added_keywords(base: BaseResume, content: Content, terms: Terms) -> list[str]:
    """The approved keywords the tailored content uses, in the judge's order."""
    text = normalize(resume_text(base, content))
    return [a.term for a in terms.approved if keyword_present(text, a.keyword())]


def _text_problem(text: str, limit: int, to_tex) -> str | None:
    if not text.strip():
        return "is empty"
    if len(text) > limit:
        return f"is {len(text)} characters; at most {limit}"
    try:
        to_tex(text)
    except ContentError as exc:
        return exc.detail
    return None


class CompileError(Exception):
    """tectonic failed or timed out. The message is for the script's own report only."""


@dataclass
class Compiled:
    pdf: bytes
    log: str


def compile_tex(tex: str, cls: Path) -> Compiled:
    """Compile in a throwaway folder holding only the TeX and the class file, like app/rendering.py."""
    with tempfile.TemporaryDirectory(prefix="tailor-build-") as tmp:
        work = Path(tmp)
        (work / "tailored.tex").write_text(tex, encoding="utf-8")
        shutil.copyfile(cls, work / "resume.cls")
        # --untrusted disables shell-escape; TECTONIC_CACHE_DIR from the environment keeps this offline.
        cmd = ["tectonic", "-X", "compile", "--untrusted", "--keep-logs", "--outdir", str(work), "tailored.tex"]
        try:
            result = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=COMPILE_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise CompileError(f"tectonic timed out after {COMPILE_TIMEOUT}s") from exc
        except OSError as exc:
            raise CompileError(f"could not run tectonic: {exc}") from exc
        pdf, log = work / "tailored.pdf", work / "tailored.log"
        if result.returncode != 0 or not pdf.is_file():
            raise CompileError(f"tectonic exited with {result.returncode}: {(result.stderr or result.stdout)[-1500:]}")
        return Compiled(pdf.read_bytes(), log.read_text(errors="replace") if log.is_file() else "")


@dataclass
class TextLine:
    top: float
    bottom: float
    words: list[tuple[str, float, float]]  # (text, x0, x1), left to right

    @property
    def x0(self) -> float:
        return self.words[0][1]

    @property
    def x1(self) -> float:
        return self.words[-1][2]

    @property
    def text(self) -> str:
        return " ".join(w[0] for w in self.words)


@dataclass
class Layout:
    pages: int
    fill: float
    lines_free: float
    overflow_lines: int
    short_lines: list[dict]
    overfull: list[dict]

    def hard_failures(self) -> list[dict]:
        found = []
        if self.pages != 1:
            found.append({"code": "one_page", "detail": f"{self.pages} pages: about {self.overflow_lines} lines spill "
                          "onto page 2. Shorten or drop the least relevant bullets."})
        elif self.fill < FILL_FLOOR:
            found.append({"code": "fill_floor", "detail": f"fills {self.fill:.1%} of the page, under the "
                          f"{FILL_FLOOR:.0%} floor; about {self.lines_free:.0f} lines are empty. Restore relevant base detail."})
        for item in self.overfull:
            found.append({"code": "overfull_line", "where": item["where"], "detail": f"runs {item['by_pt']:.1f}pt "
                          "into the right margin. Reword it so the line can break."})
        return found

    def soft_findings(self) -> list[dict]:
        found = []
        if self.pages == 1 and self.fill < FILL_TARGET:
            found.append({"code": "fill_target", "detail": f"fills {self.fill:.1%}, under the {FILL_TARGET:.0%} target; "
                          f"about {self.lines_free:.1f} lines are free for relevant base detail."})
        for item in self.short_lines:
            found.append({"code": "short_last_line", "where": item["where"], "detail": f"its last line holds only "
                          f"'{item['last_line']}' ({item['width']:.0%} of the width). Trim a few words or add detail "
                          "from its own sources."})
        return found

    def to_json(self) -> dict:
        return {"pages": self.pages, "fill": round(self.fill, 4), "lines_free": round(self.lines_free, 1),
                "short_lines": self.short_lines, "overfull": self.overfull}


def measure(compiled: Compiled, line_map: dict[int, str], bullet_refs: list[str]) -> Layout:
    """Page count, fill, short last lines and overfull lines of a compiled resume.

    `line_map` maps TeX lines to content (from resume_model.render); `bullet_refs` lists the rendered
    bullets in page order, so the bullets found on the page can be named.
    """
    with pdfplumber.open(io.BytesIO(compiled.pdf)) as pdf:
        pages = len(pdf.pages)
        page = pdf.pages[0]
        width, height = page.width, page.height
        lines = _text_lines(page)
        overflow = sum(len(_text_lines(p)) for p in pdf.pages[1:])
    bottom = max(line.bottom for line in lines)
    gaps = [b.top - a.top for a, b in zip(lines, lines[1:]) if 6 <= b.top - a.top <= 30]
    pitch = median(gaps) if gaps else 12.0
    return Layout(
        pages=pages,
        fill=(bottom - MARGIN_PT) / (height - 2 * MARGIN_PT),
        lines_free=max(0.0, (height - MARGIN_PT - bottom) / pitch),
        overflow_lines=overflow,
        short_lines=_short_last_lines(lines, width - MARGIN_PT, bullet_refs),
        overfull=_overfull(compiled.log, line_map),
    )


def _text_lines(page) -> list[TextLine]:
    lines: list[TextLine] = []
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        word = (w["text"], w["x0"], w["x1"])
        if lines and abs(lines[-1].top - w["top"]) <= LINE_TOLERANCE_PT:
            lines[-1].words.append(word)
            lines[-1].bottom = max(lines[-1].bottom, w["bottom"])
        else:
            lines.append(TextLine(w["top"], w["bottom"], [word]))
    for line in lines:
        line.words.sort(key=lambda word: word[1])
    return lines


def _short_last_lines(lines: list[TextLine], right: float, bullet_refs: list[str]) -> list[dict]:
    """Wrapped bullets whose last line is nearly empty. A one-line bullet cannot save a line, so it is skipped."""
    bullets: list[tuple[float, list[TextLine]]] = []
    current = None
    for line in lines:
        glyph = line.words[0][0]
        if glyph.startswith(BULLET_GLYPHS):
            # The text starts at the word after the glyph, unless extraction merged the two.
            text_x0 = line.words[1][1] if glyph in BULLET_GLYPHS and len(line.words) > 1 else line.x0
            current = (text_x0, [line])
            bullets.append(current)
        elif current and line.x0 >= current[0] - LINE_TOLERANCE_PT:
            current[1].append(line)
        else:
            current = None  # a job heading or section title ends the bullet
    named = len(bullets) == len(bullet_refs)
    short = []
    for n, (text_x0, group) in enumerate(bullets):
        if len(group) < 2:
            continue
        share = (group[-1].x1 - text_x0) / (right - text_x0)
        if share < SHORT_LAST_LINE:
            short.append({"where": bullet_refs[n] if named else f"bullet {n + 1}", "width": round(share, 2),
                          "last_line": group[-1].text})
    return short


def _overfull(log: str, line_map: dict[int, str]) -> list[dict]:
    """Overfull boxes inside content lines. Others, such as the header's long contact line, are not content's fault.

    TeX names a paragraph's lines, which for a bullet run from its own \\item line to the next one, so the
    first content line in the range is the culprit. The skills lines form one paragraph, named as a whole.
    """
    found = []
    for m in _OVERFULL.finditer(log):
        refs = [line_map[n] for n in range(int(m["a"]), int(m["b"]) + 1) if n in line_map]
        if refs:
            where = "skills" if refs[0].startswith("skills:") else refs[0]
            found.append({"where": where, "by_pt": float(m["by"]), "lines": [int(m["a"]), int(m["b"])]})
    return found
