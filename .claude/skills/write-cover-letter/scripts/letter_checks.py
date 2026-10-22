"""Checks on a cover letter (out/letter.json), and rendering it onto the resume's page header.

Claude writes only the paragraphs; the scripts add the date, the greeting, the sign-off and the header
from BASE.tex. Every finding is a dict with a `code`, an optional `where` ("p2", a keyword) and a `detail`
that says what to change. Hard findings reject the letter; soft ones are targets the skill keeps revising
toward.

The facts come from the base resume's bullets and the owner's profile facts, cited by ID (jN.bK, jN.fK).
Unlike a resume bullet, a paragraph may cite several jobs. In tailored mode the letter is also checked
against the posting: its company and role, its keywords, its requirements and its phrasing.
"""
import io
import re
import unicodedata
from dataclasses import dataclass, field

import pdfplumber

from resume_checks import _NUMBER, _echoes, _grams
from resume_model import BaseResume, ContentError, markup_to_plain, plain_to_tex, resume_text
from resume_score import keyword_present, normalize

WORDS_RANGE = (250, 400)  # the opening, body and closing paragraphs together
BODY_RANGE = (2, 3)
MAX_PARAGRAPH_CHARS = 1200
MIN_REQUIRED_ADDRESSED = 2
GENERIC_GREETING = "Dear Hiring Manager,"
SIGN_OFF = "Sincerely,"
POSTING_HEADING = "## Posting text (untrusted data)"
# Never a posting word: stands in for the company and role, so runs across them cannot count as echoes.
_PLACEHOLDER = "zqxjobnamezqx"
# Soft: phrases that make a letter read as a template.
FILLER = ("i am excited to apply", "i am writing to express my interest", "i believe i would be a great fit",
          "passionate about", "perfect fit", "dream job", "team player", "hit the ground running")


@dataclass
class Paragraph:
    role: str  # opening | body | closing
    text: str
    sources: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)


@dataclass
class Letter:
    paragraphs: list[Paragraph]

    def words(self) -> int:
        return sum(len(p.text.split()) for p in self.paragraphs)


@dataclass
class Job:
    """The application the letter is for: from the service's job.json. None in base mode."""

    company: str
    role: str

    @staticmethod
    def from_json(data) -> "Job":
        if not (isinstance(data, dict) and all(isinstance(data.get(k), str) and data[k].strip()
                                               for k in ("company", "role"))):
            raise ContentError("structure_mismatch", 'job.json must be {"company": "...", "role": "..."}')
        return Job(data["company"].strip(), data["role"].strip())

    def greeting(self) -> str:
        return f"Dear {self.company} Hiring Team,"


def letter_from_json(data) -> Letter:
    """Read letter.json. Shape problems are `structure_mismatch` errors."""
    def fail(detail: str):
        raise ContentError("structure_mismatch", detail)

    if not isinstance(data, dict) or not isinstance(data.get("paragraphs"), list):
        fail('expected {"paragraphs": [...]}')
    paragraphs = []
    for n, item in enumerate(data["paragraphs"], 1):
        if not (isinstance(item, dict) and item.get("role") in ("opening", "body", "closing")
                and isinstance(item.get("text"), str)):
            fail(f'paragraph {n}: expected {{"role": "opening" | "body" | "closing", "text": "..."}}')
        lists = {}
        for key in ("sources", "requirements"):
            value = item.get(key, [])
            if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                fail(f'paragraph {n}: "{key}" must be a list of strings')
            lists[key] = list(value)
        paragraphs.append(Paragraph(item["role"], item["text"].strip(), **lists))
    roles = [p.role for p in paragraphs]
    bodies = roles.count("body")
    if (len(roles) < 2 or roles[0] != "opening" or roles[-1] != "closing" or set(roles[1:-1]) != {"body"}
            or not BODY_RANGE[0] <= bodies <= BODY_RANGE[1]):
        fail(f"write one opening, {BODY_RANGE[0]} or {BODY_RANGE[1]} body paragraphs and one closing, in that order")
    return Letter(paragraphs)


def posting_body(posting: str) -> str:
    """The posting's own text in posting.md, without the service's header and the application notes."""
    _, sep, after = posting.partition(POSTING_HEADING)
    return after if sep else posting


def source_text(base: BaseResume, profile_skills: list[str]) -> str:
    """Everything the owner's sources state, normalized: the resume, its profile facts and profile skills."""
    facts = [markup_to_plain(f.text) for job in base.jobs for f in job.facts]
    return normalize("\n".join([resume_text(base, base.content()), *facts, *profile_skills]))


def _masked(text: str, job: Job | None) -> str:
    """The text with the company and role replaced by a placeholder word, so neither counts as an echo or
    a posting keyword."""
    out = normalize(text)
    if job:
        for name in sorted((normalize(job.company), normalize(job.role)), key=len, reverse=True):
            out = out.replace(name, f" {_PLACEHOLDER} ")
    return out


def _control(text: str) -> bool:
    return any(unicodedata.category(c) == "Cc" for c in text)


def check_letter(base: BaseResume, letter: Letter, profile_skills: list[str], job: Job | None = None,
                 analysis: dict | None = None, posting: str | None = None) -> tuple[list[dict], list[dict]]:
    """Hard findings and warnings. Base mode passes no job, analysis or posting; tailored mode needs all three."""
    errors, warnings = [], []
    sources = base.sources()
    allowed_numbers = set(_NUMBER.findall(f"{job.company} {job.role}")) if job else set()
    grams = _grams(posting_body(posting)) if job and posting is not None else set()
    for n, p in enumerate(letter.paragraphs, 1):
        where = f"p{n}"
        if not p.text:
            errors.append({"code": "invalid_text", "where": where, "detail": "is empty"})
            continue
        if len(p.text) > MAX_PARAGRAPH_CHARS:
            errors.append({"code": "invalid_text", "where": where,
                           "detail": f"is {len(p.text)} characters; at most {MAX_PARAGRAPH_CHARS}"})
        if _control(p.text):
            errors.append({"code": "invalid_text", "where": where, "detail": "contains a control character or line break"})
        elif "\\" in p.text:
            errors.append({"code": "invalid_text", "where": where, "detail": "contains a backslash; write plain text"})
        if p.role == "body" and not p.sources:
            errors.append({"code": "missing_source", "where": where,
                           "detail": "cite the jN.bK bullets or jN.fK facts this paragraph draws on"})
        cited = []
        for source in p.sources:
            if source in sources:
                cited.append(markup_to_plain(sources[source][1].text))
            else:
                errors.append({"code": "unknown_source", "where": where,
                               "detail": f"{source} is not a base bullet or a profile fact"})
        allowed = allowed_numbers | {num for text in cited for num in _NUMBER.findall(text)}
        extra = sorted(set(_NUMBER.findall(p.text)) - allowed, key=lambda x: float(x))
        if extra:
            errors.append({"code": "unsupported_number", "where": where,
                           "detail": f"{', '.join(extra)} not in its cited sources; keep numbers exactly as in the "
                                     "sources" + ("" if p.role == "body" else ", and put them in a body paragraph")})
        lowered = normalize(p.text)
        for phrase in FILLER:
            if phrase in lowered:
                warnings.append({"code": "filler_phrase", "where": where,
                                 "detail": f'"{phrase}" reads as a template; say something specific instead'})
        if grams:
            for phrase in _echoes(_masked(p.text, job), " ".join(cited), grams):
                errors.append({"code": "echoed_phrase", "where": where,
                               "detail": f'"{phrase}" is copied from the posting; describe the work in the '
                                         "owner's own words"})

    words = letter.words()
    if not WORDS_RANGE[0] <= words <= WORDS_RANGE[1]:
        errors.append({"code": "word_count", "detail": f"{words} words; write {WORDS_RANGE[0]} to {WORDS_RANGE[1]}"})

    if job:
        errors += _tailored(base, letter, profile_skills, job, analysis or {"keywords": [], "requirements": []})
    return errors, warnings


def _tailored(base: BaseResume, letter: Letter, profile_skills: list[str], job: Job, analysis: dict) -> list[dict]:
    errors = []
    opening = normalize(letter.paragraphs[0].text)
    if normalize(job.company) not in opening:
        errors.append({"code": "missing_company", "where": "p1", "detail": f"name the company as {job.company!r}"})
    if normalize(job.role) not in opening:
        errors.append({"code": "missing_role", "where": "p1", "detail": f"name the role as {job.role!r}"})

    owned = source_text(base, profile_skills)
    text = _masked(" ".join(p.text for p in letter.paragraphs), job)
    for kw in analysis["keywords"]:
        if keyword_present(text, kw) and not keyword_present(owned, kw):
            errors.append({"code": "unsupported_keyword", "where": kw["term"],
                           "detail": "neither the resume nor the profile states it; leave it out"})

    requirements = {r["id"]: r for r in analysis["requirements"]}
    addressed = set()
    for n, p in enumerate(letter.paragraphs, 1):
        if p.role != "body":
            continue
        if not p.requirements:
            errors.append({"code": "requirements_not_addressed", "where": f"p{n}",
                           "detail": "name the requirement IDs from out/analysis.json this paragraph shows"})
        for rid in p.requirements:
            if rid not in requirements:
                errors.append({"code": "unknown_requirement", "where": f"p{n}",
                               "detail": f"{rid} is not a requirement of out/analysis.json"})
            else:
                addressed.add(rid)
    required = {rid for rid, r in requirements.items() if r["importance"] == "required"}
    needed = min(MIN_REQUIRED_ADDRESSED, len(required))
    if len(addressed & required) < needed:
        errors.append({"code": "requirements_not_addressed",
                       "detail": f"the body paragraphs address {len(addressed & required)} required requirements; "
                                 f"address at least {needed}"})
    return errors


# --- rendering ---

_PREAMBLE_END = r"\begin{document}"
_NAME = re.compile(r"\\name\{([^{}]*)\}")


def owner_name(base_tex: str) -> str:
    m = _NAME.search(base_tex)
    if not m:
        raise ContentError("template_invalid", r"BASE.tex has no \name{...}")
    return " ".join(w.capitalize() for w in m.group(1).split())


def render_tex(base_tex: str, greeting: str, paragraphs: list[str], date: str) -> str:
    """The letter on the resume's header: BASE.tex up to \\begin{document}, then the letter in plain text."""
    head, sep, _ = base_tex.partition(_PREAMBLE_END)
    if not sep:
        raise ContentError("template_invalid", r"BASE.tex has no \begin{document}")
    body = [r"\vspace{1.5em}", r"{\fontsize{11pt}{15pt}\selectfont", "", plain_to_tex(date), "",
            plain_to_tex(greeting), ""]
    for text in paragraphs:
        body += [plain_to_tex(text), ""]
    body += [plain_to_tex(SIGN_OFF) + r" \\", plain_to_tex(owner_name(base_tex)), "}", r"\end{document}", ""]
    return head + sep + "\n" + "\n".join(body)


def plain_text(base_tex: str, greeting: str, paragraphs: list[str]) -> str:
    """The letter as the response's `text`: greeting, paragraphs and sign-off, a blank line between paragraphs."""
    return "\n\n".join([greeting, *paragraphs, f"{SIGN_OFF}\n{owner_name(base_tex)}"]) + "\n"


def pages(pdf: bytes) -> int:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return len(doc.pages)


def pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)
