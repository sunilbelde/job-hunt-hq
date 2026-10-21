import copy
import json
from fractions import Fraction

import pytest

import resume_model
import resume_score
from app.rendering import TEMPLATE_DIR
from resume_score import AnalysisError, score, validate_analysis
from tests.tailoring_fixtures import ANALYSIS, content_json, prepare, run_tool, weak_analysis, write_out


def kw(term, importance="required", aliases=()):
    return {"term": term, "importance": importance, "aliases": list(aliases)}


def req(req_id, importance="required"):
    return {"id": req_id, "text": f"requirement {req_id}", "importance": importance}


MISSING = {"status": "missing", "evidence": []}


# --- the arithmetic (spec scenarios) ---

def test_keyword_coverage_weighs_required_double():
    result = score([kw("Python"), kw("Kafka"), kw("Docker", "preferred")], [req("R1")], {"R1": MISSING},
                   "Python services in Docker")
    assert result.keyword_coverage == Fraction(3, 5)


def test_requirement_coverage_counts_partial_as_half():
    text = "shipped the billing service on time with zero downtime"
    assessment = {"R1": {"status": "met", "evidence": ["shipped the billing service"]},
                  "R2": {"status": "partial", "evidence": ["with zero downtime"]},
                  "R3": MISSING}
    result = score([kw("x")], [req("R1"), req("R2"), req("R3", "preferred")], assessment, text)
    assert result.requirement_coverage == Fraction(3, 5)


def test_combined_score_is_half_each_rounded_down():
    keywords = [kw("alpha"), kw("beta"), kw("gamma"), kw("delta")]
    text = "alpha beta gamma, reducing engineering effort by over 70%"
    assessment = {"R1": {"status": "met", "evidence": ["reducing engineering effort by over 70%"]}, "R2": MISSING}
    result = score(keywords, [req("R1"), req("R2")], assessment, text)
    assert (result.keyword_coverage, result.requirement_coverage, result.score) == (Fraction(3, 4), Fraction(1, 2), 62)


def test_same_inputs_give_the_same_score():
    args = (ANALYSIS["keywords"], ANALYSIS["requirements"], ANALYSIS["assessment"], "Python and PyTorch with RAG")
    assert score(*args).to_json() == score(*args).to_json()


def test_threshold_keeps_70_and_tailors_69():
    assert resume_score.decide(70) == "keep" and resume_score.decide(69) == "tailor"
    # Every keyword present, requirements 2 of 5: exactly 70.
    assessment = {"R1": {"status": "met", "evidence": ["led the platform migration"]}, "R2": MISSING, "R3": MISSING}
    result = score([kw("Go")], [req("R1"), req("R2"), req("R3", "preferred")], assessment, "Go; led the platform migration")
    assert (result.score, result.decision) == (70, "keep")


# --- matching ---

def test_alias_counts_as_the_keyword():
    result = score([kw("Kubernetes", aliases=["k8s"])], [req("R1")], {"R1": MISSING}, "deployed on k8s clusters")
    assert result.keywords[0]["present"] is True


@pytest.mark.parametrize("term, text, present", [
    ("Java", "built JavaScript front ends", False),
    ("Java", "Java and Spring Boot", True),
    ("C++", "written in C++ and Python", True),
    ("REST APIs", "designed REST   APIs", True),
    ("LLM", "LLMs (Llama, Mistral)", False),  # inflections must be listed as aliases
])
def test_keywords_match_whole_words_ignoring_case(term, text, present):
    assert resume_score.keyword_present(resume_score.normalize(text), kw(term)) is present


def test_quote_not_in_the_resume_is_unverified():
    assessment = {"R1": {"status": "met", "evidence": ["led a team of fifty engineers"]}}
    row = score([kw("x")], [req("R1")], assessment, "built internal tools").requirements[0]
    assert (row["counted"], row["unverified"], row["reason"]) == ("missing", True, "a quote is not in the resume")


def test_short_or_absent_quotes_are_unverified():
    result = score([kw("x")], [req("R1"), req("R2")],
                   {"R1": {"status": "met", "evidence": ["Python"]}, "R2": {"status": "partial", "evidence": []}},
                   "Python everywhere")
    assert [row["counted"] for row in result.requirements] == ["missing", "missing"]


def test_quotes_ignore_case_whitespace_and_markup():
    assessment = {"R1": {"status": "met", "evidence": ["**reducing   engineering** effort"]}}
    row = score([kw("x")], [req("R1")], assessment, "Reducing engineering\neffort by 70%").requirements[0]
    assert row["counted"] == "met"


# --- validation ---

def test_fixture_analysis_is_valid():
    validate_analysis(ANALYSIS)


def _broken(change):
    analysis = copy.deepcopy(ANALYSIS)
    change(analysis)
    return analysis


@pytest.mark.parametrize("analysis, message", [
    (_broken(lambda a: a.update(keywords=a["keywords"][:2])), "keywords: list 5 to 40"),
    (_broken(lambda a: a["requirements"][0].pop("importance")), 'requirement R1: "importance"'),
    (_broken(lambda a: a["keywords"].append(dict(a["keywords"][0]))), "listed twice"),
    (_broken(lambda a: a["assessment"].pop("R3")), "assessment R3"),
    (_broken(lambda a: a.update(requirements=a["requirements"] * 6)), "requirements: list 3 to 15"),
    ([], "analysis.json must be an object"),
])
def test_bad_analysis_is_rejected(analysis, message):
    with pytest.raises(AnalysisError, match=message):
        validate_analysis(analysis)


# --- the score subcommand ---

def test_score_base_on_the_real_resume(tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    r = run_tool("score", "base", "--work", str(work))
    assert r.returncode == 0, r.stderr
    data = json.loads((work / "out" / "score_base.json").read_text())
    assert (data["score"], data["decision"], data["threshold"]) == (77, "keep", 70)
    assert "keywords not in this resume: Kafka (required), Airflow (preferred)" in r.stdout
    assert "keep the base resume and stop" in r.stdout


def test_score_base_runs_from_the_work_folder(tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", weak_analysis())
    r = run_tool("score", "base", cwd=work)
    assert r.returncode == 0, r.stderr
    assert "base score 57" in r.stdout and "below 70, tailor the resume" in r.stdout


def test_score_base_rejects_a_bad_analysis(tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", _broken(lambda a: a.update(keywords=a["keywords"][:2])))
    r = run_tool("score", "base", "--work", str(work))
    assert r.returncode == 1 and "score failed" in r.stderr and "keywords" in r.stderr


def test_score_tailored(tmp_path):
    work = prepare(tmp_path / "work")
    base = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
    write_out(work, "analysis.json", weak_analysis())
    write_out(work, "tailored.json", content_json(base))
    write_out(work, "assessment_tailored.json", ANALYSIS["assessment"])
    r = run_tool("score", "tailored", "--work", str(work))
    assert r.returncode == 0, r.stderr
    assert json.loads((work / "out" / "score_tailored.json").read_text())["score"] == 77


def test_score_tailored_needs_its_assessment(tmp_path):
    work = prepare(tmp_path / "work")
    base = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
    write_out(work, "analysis.json", ANALYSIS)
    write_out(work, "tailored.json", content_json(base))
    r = run_tool("score", "tailored", "--work", str(work))
    assert r.returncode == 1 and "assessment_tailored.json is missing" in r.stderr
