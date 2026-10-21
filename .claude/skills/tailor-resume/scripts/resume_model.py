"""The editable model of the base resume (data/BASE.tex) and the renderer that splices content back in.

Claude never writes TeX. It edits plain text with **bold** and *italic* marks, which this module turns
into TeX, replacing only the TECHNICAL SKILLS lines and each job's \\item lines of BASE.tex. The preamble,
header, education, job headings, spacing commands and certifications stay the base file's own lines.
"""
import re
from dataclasses import dataclass, field

SECTIONS = ("EDUCATION", "TECHNICAL SKILLS", "EXPERIENCE", "CERTIFICATIONS")
TEX_SPECIALS = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
MARKS = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*")

_ESCAPED_OR_PLAIN = r"(?:[^{}\\]|\\[%&$#_])*"
_SECTION_BEGIN = re.compile(r"\\begin\{rSection\}\{([^}]*)\}")
_SKILL_LINE = re.compile(rf"^\s*\\textbf\{{(?P<label>{_ESCAPED_OR_PLAIN})\}}:\s*(?P<items>.*?)\s*(?:\\\\)?\s*$")
_HEADING = re.compile(r"^\s*\\textbf\{(?P<who>.*)\},\s*\\textit\{(?P<where>.*)\}\s*\\hfill\s*(?P<when>.*?)\s*$")
_ITEM = re.compile(r"^(?P<indent>\s*)\\item\s+(?P<text>.*?)\s*$")
_VSPACE = re.compile(r"^\\vspace\{[^}]*\}\s*(%.*)?$")


class ModelError(ValueError):
    """BASE.tex does not follow the conventions the parser relies on. The message names the line."""


class ContentError(ValueError):
    """Content that cannot be rendered: `code` is the check code, `detail` says what to change."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class SkillLine:
    label: str
    items: list[str]


@dataclass
class Bullet:
    id: str
    text: str  # markup


@dataclass
class Fact:
    id: str  # "j1.f1": a fact of job j1 from the owner's profile (data/PROFILE.md), never printed as is
    text: str  # markup


@dataclass
class Job:
    id: str
    heading: str  # plain text: "Company, Title | Location | Dates"
    bullets: list[Bullet]
    span: tuple[int, int]  # indexes of the first \item line and of the line after the last one
    indent: str
    spaced: bool  # BASE.tex leaves blank lines between this job's \item lines
    facts: list[Fact] = field(default_factory=list)


@dataclass
class ContentBullet:
    text: str
    sources: list[str]


@dataclass
class ContentJob:
    id: str
    bullets: list[ContentBullet]


@dataclass
class Content:
    """What Claude may change: the skills lines and each job's bullets."""

    skills: list[SkillLine]
    jobs: list[ContentJob]


@dataclass
class BaseResume:
    lines: list[str]
    skills: list[SkillLine]
    skills_span: tuple[int, int]
    jobs: list[Job]
    education: list[str]
    certifications: list[str]

    def bullets(self) -> dict[str, tuple[Job, Bullet]]:
        return {b.id: (job, b) for job in self.jobs for b in job.bullets}

    def sources(self) -> dict[str, tuple[Job, Bullet | Fact]]:
        """What a tailored bullet may cite: the base bullets and the profile facts, by ID."""
        return {s.id: (job, s) for job in self.jobs for s in [*job.bullets, *job.facts]}

    def content(self) -> Content:
        """The base resume as content, each bullet citing itself."""
        return Content(
            skills=[SkillLine(s.label, list(s.items)) for s in self.skills],
            jobs=[ContentJob(j.id, [ContentBullet(b.text, [b.id]) for b in j.bullets]) for j in self.jobs],
        )

    def to_json(self) -> dict:
        return {
            "skills": [{"label": s.label, "items": s.items} for s in self.skills],
            "jobs": [{"id": j.id, "heading": j.heading, "bullets": [{"id": b.id, "text": b.text} for b in j.bullets],
                      "facts": [{"id": f.id, "text": f.text} for f in j.facts]}
                     for j in self.jobs],
            "text": resume_text(self, self.content()),
        }


@dataclass
class Rendered:
    tex: str
    line_map: dict[int, str]  # 1-based TeX line -> "skills:<label>" or "<job id>#<position>"


# --- TeX <-> markup ---

def tex_to_markup(tex: str, where: str) -> str:
    """Convert a skills line or bullet from BASE.tex. Only \\textbf, \\textit and escaped specials are allowed."""
    text = re.sub(rf"\\textbf\{{({_ESCAPED_OR_PLAIN})\}}", r"**\1**", tex)
    text = re.sub(rf"\\textit\{{({_ESCAPED_OR_PLAIN})\}}", r"*\1*", text)
    text = re.sub(r"\\([%&$#_])", r"\1", text)
    if re.search(r"[\\{}]", text):
        raise ModelError(f"{where}: unsupported TeX in {tex.strip()[:70]!r}")
    return text.strip()


def tex_to_plain(tex: str) -> str:
    """Visible text of a fixed line (education, heading, certification) for scoring."""
    text = re.sub(r"\\vspace\{[^}]*\}", "", tex)
    text = re.sub(r"\\\\\s*$", "", text).replace(r"\hfill", "  ")
    text = re.sub(r"\{\\bf\s+([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\text(?:bf|it)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\([%&$#_])", r"\1", text).replace("~", " ")
    return " ".join(text.split())


def plain_to_tex(text: str) -> str:
    """Escape plain text (a skills label or item) for TeX."""
    _check_text(text)
    return "".join(TEX_SPECIALS.get(c, c) for c in text)


def markup_to_tex(text: str) -> str:
    """Turn bullet markup into TeX: **bold** and *italic*, every TeX special printed literally."""
    _check_text(text)
    parts, pos = [], 0
    for m in MARKS.finditer(text):
        parts.append(_escape_unmarked(text[pos:m.start()]))
        if m.group(1) is not None:
            parts.append(r"\textbf{" + _escape_unmarked(m.group(1)) + "}")
        else:
            parts.append(r"\textit{" + _escape_unmarked(m.group(2)) + "}")
        pos = m.end()
    parts.append(_escape_unmarked(text[pos:]))
    return "".join(parts)


def markup_to_plain(text: str) -> str:
    return MARKS.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)


def _check_text(text: str) -> None:
    if "\\" in text:
        raise ContentError("invalid_text", "contains a backslash; write plain text")
    if "\n" in text or "\r" in text:
        raise ContentError("invalid_text", "contains a line break")


def _escape_unmarked(text: str) -> str:
    if "*" in text:
        raise ContentError("invalid_text", "has a * that is not part of a **bold** or *italic* pair")
    return "".join(TEX_SPECIALS.get(c, c) for c in text)


def split_items(text: str) -> list[str]:
    """Split a skills list on commas outside parentheses: "AWS (EC2, S3), GCP" is two items."""
    items, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    items.append("".join(current).strip())
    return [item for item in items if item]


# --- parsing BASE.tex ---

def parse_base(tex: str) -> BaseResume:
    lines = tex.split("\n")
    sections = _find_sections(lines)
    skills, skills_span = _parse_skills(lines, *sections["TECHNICAL SKILLS"])
    return BaseResume(
        lines=lines,
        skills=skills,
        skills_span=skills_span,
        jobs=_parse_jobs(lines, *sections["EXPERIENCE"]),
        education=_plain_lines(lines, *sections["EDUCATION"]),
        certifications=_plain_lines(lines, *sections["CERTIFICATIONS"]),
    )


def _is_code(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("%")


def _find_sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    found, name, start = {}, None, 0
    for i, line in enumerate(lines):
        if not _is_code(line):
            continue
        m = _SECTION_BEGIN.search(line)
        if m:
            name, start = m.group(1).strip(), i
        elif line.strip().startswith(r"\end{rSection}") and name is not None:
            found[name] = (start, i)
            name = None
    order = [n for n in found if n in SECTIONS]
    if order != list(SECTIONS):
        raise ModelError(f"BASE.tex must have the sections {', '.join(SECTIONS)} in that order; found {', '.join(found)}")
    return found


def _parse_skills(lines: list[str], begin: int, end: int) -> tuple[list[SkillLine], tuple[int, int]]:
    code = [i for i in range(begin + 1, end) if _is_code(lines[i])]
    if not code:
        raise ModelError(f"BASE.tex line {begin + 1}: TECHNICAL SKILLS has no lines")
    first, last = code[0], code[-1]
    skills = []
    for i in range(first, last + 1):
        m = _SKILL_LINE.match(lines[i])
        if not m:
            raise ModelError(f"BASE.tex line {i + 1}: expected a skills line '\\textbf{{Label}}: item, item \\\\'")
        where = f"BASE.tex line {i + 1}"
        label = tex_to_markup(m.group("label"), where)
        items = [tex_to_markup(item, where) for item in split_items(m.group("items"))]
        skills.append(SkillLine(label, items))
    return skills, (first, last + 1)


def _parse_jobs(lines: list[str], begin: int, end: int) -> list[Job]:
    jobs: list[Job] = []
    heading, in_list, items = None, False, []
    for i in range(begin + 1, end):
        line, stripped = lines[i], lines[i].strip()
        if not _is_code(line):
            continue
        if in_list:
            if stripped.startswith(r"\itemsep"):
                continue
            if stripped == r"\end{itemize}":
                jobs.append(_make_job(len(jobs) + 1, heading, items, lines, i))
                heading, in_list, items = None, False, []
                continue
            m = _ITEM.match(line)
            if not m:
                raise ModelError(f"BASE.tex line {i + 1}: expected one \\item per line inside itemize")
            items.append((i, m.group("indent"), tex_to_markup(m.group("text"), f"BASE.tex line {i + 1}")))
        elif stripped == r"\begin{itemize}":
            if heading is None:
                raise ModelError(f"BASE.tex line {i + 1}: itemize without a job heading before it")
            in_list = True
        elif _VSPACE.match(stripped):
            continue
        elif (m := _HEADING.match(line)):
            heading = " | ".join(tex_to_plain(m.group(k)) for k in ("who", "where", "when"))
        else:
            raise ModelError(f"BASE.tex line {i + 1}: unexpected line in EXPERIENCE")
    if not jobs:
        raise ModelError("BASE.tex: EXPERIENCE has no jobs")
    return jobs


def _make_job(n: int, heading: str, items: list, lines: list[str], end_line: int) -> Job:
    if not items:
        raise ModelError(f"BASE.tex line {end_line + 1}: job without bullets")
    first, last = items[0][0], items[-1][0]
    job_id = f"j{n}"
    return Job(
        id=job_id,
        heading=heading,
        bullets=[Bullet(f"{job_id}.b{k}", text) for k, (_, _, text) in enumerate(items, 1)],
        span=(first, last + 1),
        indent=items[0][1],
        spaced=any(not lines[k].strip() for k in range(first, last + 1)),
    )


def _plain_lines(lines: list[str], begin: int, end: int) -> list[str]:
    plain = (tex_to_plain(lines[i]) for i in range(begin + 1, end) if _is_code(lines[i]))
    return [text for text in plain if text]


# --- content, rendering and text ---

def content_from_json(data) -> Content:
    """Read tailored.json. Shape problems are `structure_mismatch` errors."""
    def fail(detail: str):
        raise ContentError("structure_mismatch", detail)

    if not isinstance(data, dict) or not isinstance(data.get("skills"), list) or not isinstance(data.get("jobs"), list):
        fail('expected {"skills": [...], "jobs": [...]}')
    skills = []
    for n, line in enumerate(data["skills"], 1):
        if not (isinstance(line, dict) and isinstance(line.get("label"), str) and isinstance(line.get("items"), list)
                and all(isinstance(item, str) for item in line["items"])):
            fail(f'skills line {n}: expected {{"label": "...", "items": ["...", ...]}}')
        skills.append(SkillLine(line["label"].strip(), [item.strip() for item in line["items"]]))
    jobs = []
    for n, job in enumerate(data["jobs"], 1):
        if not (isinstance(job, dict) and isinstance(job.get("id"), str) and isinstance(job.get("bullets"), list)):
            fail(f'job {n}: expected {{"id": "jN", "bullets": [...]}}')
        bullets = []
        for k, bullet in enumerate(job["bullets"], 1):
            if not (isinstance(bullet, dict) and isinstance(bullet.get("text"), str)
                    and isinstance(bullet.get("sources"), list) and all(isinstance(s, str) for s in bullet["sources"])):
                fail(f'{job["id"]}#{k}: expected {{"text": "...", "sources": ["{job["id"]}.bN", ...]}}')
            bullets.append(ContentBullet(bullet["text"].strip(), list(bullet["sources"])))
        jobs.append(ContentJob(job["id"], bullets))
    return Content(skills, jobs)


def render(base: BaseResume, content: Content) -> Rendered:
    """BASE.tex with its skills lines and \\item lines replaced by `content`; every other line is kept."""
    replaced = {base.skills_span[0]: ("skills", base.skills_span[1])}
    replaced.update({job.span[0]: (job.id, job.span[1]) for job in base.jobs})
    jobs = {job.id: job for job in base.jobs}
    bullets = {job.id: job.bullets for job in content.jobs}
    out: list[str] = []
    line_map: dict[int, str] = {}
    i = 0
    while i < len(base.lines):
        if i not in replaced:
            out.append(base.lines[i])
            i += 1
            continue
        kind, end = replaced[i]
        if kind == "skills":
            for n, line in enumerate(content.skills):
                tex = r"\textbf{%s}: %s" % (plain_to_tex(line.label), ", ".join(plain_to_tex(x) for x in line.items))
                out.append(tex + (r" \\" if n < len(content.skills) - 1 else ""))
                line_map[len(out)] = f"skills:{line.label}"
        else:
            job = jobs[kind]
            for n, bullet in enumerate(bullets.get(kind, []), 1):
                if n > 1 and job.spaced:
                    out.append("")
                out.append(f"{job.indent}\\item {markup_to_tex(bullet.text)}")
                line_map[len(out)] = f"{kind}#{n}"
        i = end
    return Rendered("\n".join(out), line_map)


def resume_text(base: BaseResume, content: Content) -> str:
    """The resume's visible text (without the name and contact line), as scoring sees it."""
    lines = ["EDUCATION", *base.education, "TECHNICAL SKILLS"]
    lines += [f"{line.label}: {', '.join(line.items)}" for line in content.skills]
    lines.append("EXPERIENCE")
    bullets = {job.id: job.bullets for job in content.jobs}
    for job in base.jobs:
        lines.append(job.heading)
        lines += [f"- {markup_to_plain(b.text)}" for b in bullets.get(job.id, [])]
    lines += ["CERTIFICATIONS", *base.certifications]
    return "\n".join(lines)
