"""The match score: how well a resume's text covers a posting's keywords and requirements.

Claude writes the keyword and requirement list and its assessment (out/analysis.json). Everything here is
arithmetic and string matching on that list, so the same inputs always give the same score.
"""
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from math import floor

THRESHOLD = 70  # a base score at or above this keeps the base resume
WEIGHTS = {"required": 2, "preferred": 1}
POINTS = {"met": Fraction(1), "partial": Fraction(1, 2), "missing": Fraction(0)}
KEYWORD_SHARE = Fraction(1, 2)  # the rest of the score is requirement coverage
KEYWORDS_RANGE = (5, 40)
REQUIREMENTS_RANGE = (3, 15)
MAX_TERM_CHARS = 60
MIN_QUOTE_WORDS = 3

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}


class AnalysisError(ValueError):
    """An analysis or assessment file breaks the rules. `problems` lists what to fix."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def normalize(text: str) -> str:
    """Lower case, one kind of dash and quote, no markup stars, single spaces."""
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES).replace("*", "")
    return " ".join(text.lower().split())


def _pattern(term: str) -> re.Pattern:
    # Whole words or phrases only: "Java" does not match "JavaScript", while "C++" and ".NET" still match.
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(word) for word in normalize(term).split()) + r"(?!\w)")


def keyword_present(normalized_text: str, keyword: dict) -> bool:
    terms = [keyword["term"], *keyword.get("aliases", [])]
    return any(_pattern(term).search(normalized_text) for term in terms if normalize(term))


def decide(score: int) -> str:
    return "keep" if score >= THRESHOLD else "tailor"


def validate_analysis(analysis) -> None:
    problems = []
    if not isinstance(analysis, dict):
        raise AnalysisError(['analysis.json must be an object with "keywords", "requirements" and "assessment"'])
    keywords, requirements = analysis.get("keywords"), analysis.get("requirements")

    if not isinstance(keywords, list) or not KEYWORDS_RANGE[0] <= len(keywords) <= KEYWORDS_RANGE[1]:
        problems.append(f"keywords: list {KEYWORDS_RANGE[0]} to {KEYWORDS_RANGE[1]} of the posting's skills, tools and terms")
        keywords = []
    seen = set()
    for n, kw in enumerate(keywords, 1):
        if not (isinstance(kw, dict) and isinstance(kw.get("term"), str) and normalize(kw["term"])):
            problems.append(f'keyword {n}: needs a "term"')
            continue
        term = normalize(kw["term"])
        if len(term) > MAX_TERM_CHARS:
            problems.append(f"keyword {n}: a term is at most {MAX_TERM_CHARS} characters")
        if term in seen:
            problems.append(f"keyword {n}: {kw['term']!r} is listed twice")
        seen.add(term)
        if kw.get("importance") not in WEIGHTS:
            problems.append(f'keyword {n}: "importance" must be "required" or "preferred"')
        aliases = kw.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            problems.append(f'keyword {n}: "aliases" must be a list of strings')
        elif any(len(normalize(a)) > MAX_TERM_CHARS for a in aliases):
            problems.append(f"keyword {n}: an alias is at most {MAX_TERM_CHARS} characters")

    if not isinstance(requirements, list) or not REQUIREMENTS_RANGE[0] <= len(requirements) <= REQUIREMENTS_RANGE[1]:
        problems.append(f"requirements: list {REQUIREMENTS_RANGE[0]} to {REQUIREMENTS_RANGE[1]} of the posting's requirements")
        requirements = []
    ids = set()
    for n, req in enumerate(requirements, 1):
        if not (isinstance(req, dict) and isinstance(req.get("id"), str) and req["id"].strip()):
            problems.append(f'requirement {n}: needs an "id"')
            continue
        if req["id"] in ids:
            problems.append(f"requirement {n}: id {req['id']!r} is used twice")
        ids.add(req["id"])
        if not (isinstance(req.get("text"), str) and req["text"].strip()):
            problems.append(f'requirement {req["id"]}: needs a "text"')
        if req.get("importance") not in WEIGHTS:
            problems.append(f'requirement {req["id"]}: "importance" must be "required" or "preferred"')
    problems += _assessment_problems(analysis.get("assessment"), ids)
    if problems:
        raise AnalysisError(problems)


def validate_assessment(assessment, requirements: list[dict]) -> None:
    problems = _assessment_problems(assessment, {req["id"] for req in requirements})
    if problems:
        raise AnalysisError(problems)


def _assessment_problems(assessment, ids: set[str]) -> list[str]:
    if not isinstance(assessment, dict):
        return ['assessment: an object mapping each requirement id to {"status", "evidence"}']
    problems = []
    for req_id in sorted(ids):
        entry = assessment.get(req_id)
        if not isinstance(entry, dict) or entry.get("status") not in POINTS:
            problems.append(f'assessment {req_id}: "status" must be "met", "partial" or "missing"')
        elif not isinstance(entry.get("evidence", []), list) or not all(isinstance(q, str) for q in entry.get("evidence", [])):
            problems.append(f'assessment {req_id}: "evidence" must be a list of quotes')
    return problems


@dataclass
class Score:
    score: int
    decision: str
    keyword_coverage: Fraction
    requirement_coverage: Fraction
    keywords: list[dict]
    requirements: list[dict]

    def to_json(self) -> dict:
        return {"score": self.score, "decision": self.decision, "threshold": THRESHOLD,
                "keyword_coverage": round(float(self.keyword_coverage), 4),
                "requirement_coverage": round(float(self.requirement_coverage), 4),
                "keywords": self.keywords, "requirements": self.requirements}

    def summary(self, label: str) -> str:
        lines = [f"{label} score {self.score}: keywords {float(self.keyword_coverage):.0%}, "
                 f"requirements {float(self.requirement_coverage):.0%}"]
        missing = [f"{k['term']} ({k['importance']})" for k in self.keywords if not k["present"]]
        if missing:
            lines.append(f"keywords not in this resume: {', '.join(missing)}")
        for req in self.requirements:
            if req["unverified"]:
                lines.append(f"unverified (counted as missing): {req['id']}: {req['reason']}")
        return "\n".join(lines)


def score(keywords: list[dict], requirements: list[dict], assessment: dict, resume_text: str) -> Score:
    text = normalize(resume_text)
    kw_rows = [{"term": kw["term"], "importance": kw["importance"], "present": keyword_present(text, kw)} for kw in keywords]
    kw_total = sum(WEIGHTS[row["importance"]] for row in kw_rows)
    kw_hit = sum(WEIGHTS[row["importance"]] for row in kw_rows if row["present"])

    req_rows, points, req_total = [], Fraction(0), 0
    for req in requirements:
        entry = assessment[req["id"]]
        status, counted, reason = entry["status"], entry["status"], None
        if status != "missing":
            quotes = entry.get("evidence") or []
            if not quotes:
                reason = "no quote from the resume"
            elif any(len(normalize(q).split()) < MIN_QUOTE_WORDS for q in quotes):
                reason = f"a quote is shorter than {MIN_QUOTE_WORDS} words"
            elif any(normalize(q) not in text for q in quotes):
                reason = "a quote is not in the resume"
            if reason:
                counted = "missing"
        weight = WEIGHTS[req["importance"]]
        req_total += weight
        points += weight * POINTS[counted]
        req_rows.append({"id": req["id"], "importance": req["importance"], "status": status, "counted": counted,
                         "unverified": reason is not None, "reason": reason})

    k = Fraction(kw_hit, kw_total) if kw_total else Fraction(0)
    r = points / req_total if req_total else Fraction(0)
    total = floor(100 * (KEYWORD_SHARE * k + (1 - KEYWORD_SHARE) * r))
    return Score(total, decide(total), k, r, kw_rows, req_rows)


def breakdown(result: Score, requirements: list[dict], assessment: dict) -> dict:
    """The score as JSON, each requirement row also carrying its text and the assessment's quotes."""
    texts = {req["id"]: req["text"] for req in requirements}
    out = result.to_json()
    out["requirements"] = [dict(row, text=texts[row["id"]], evidence=list(assessment[row["id"]].get("evidence") or []))
                           for row in result.requirements]
    return out
