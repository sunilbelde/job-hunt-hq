import hashlib
import io
import shutil
import subprocess
import tempfile

import pdfplumber
import pytest

import resume_checks
import resume_model
from app.rendering import TEMPLATE_DIR, render_pdf

CLS = TEMPLATE_DIR / "resume.cls"
needs_tectonic = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")


@pytest.fixture(scope="module")
def base():
    return resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))


def build(base, content):
    rendered = resume_model.render(base, content)
    compiled = resume_checks.compile_tex(rendered.tex, CLS)
    refs = [ref for _, ref in sorted(rendered.line_map.items()) if "#" in ref]
    return compiled, resume_checks.measure(compiled, rendered.line_map, refs)


@pytest.fixture(scope="module")
def base_build(base):
    return build(base, base.content())


def pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return " ".join(" ".join(page.extract_text().split()) for page in doc.pages)


# --- compiling and measuring ---

@needs_tectonic
def test_base_content_fills_one_page(base_build):
    _, layout = base_build
    assert layout.pages == 1
    assert layout.fill == pytest.approx(0.987, abs=0.005)
    assert layout.hard_failures() == []  # the header's own overfull contact line is not content's fault
    # Base bullets j4.b1-j4.b3 end with 2-3 words on their last line.
    assert {item["where"] for item in layout.short_lines} == {"j4#1", "j4#2", "j4#3"}
    assert {f["code"] for f in layout.soft_findings()} == {"short_last_line"}


@needs_tectonic
def test_rendered_base_reads_like_base_tex(base_build):
    compiled, _ = base_build
    assert pdf_text(compiled.pdf) == pdf_text(render_pdf())


@needs_tectonic
def test_content_spilling_onto_a_second_page_fails(base):
    content = base.content()
    content.jobs[0].bullets *= 3
    _, layout = build(base, content)
    assert layout.pages == 2 and layout.overflow_lines > 0
    assert [f["code"] for f in layout.hard_failures()] == ["one_page"]


@needs_tectonic
def test_half_empty_page_fails_the_floor(base):
    content = base.content()
    for job in content.jobs:
        job.bullets = job.bullets[:1]
    _, layout = build(base, content)
    assert layout.pages == 1 and layout.fill < resume_checks.FILL_FLOOR
    assert [f["code"] for f in layout.hard_failures()] == ["fill_floor"]
    assert "fill_target" in {f["code"] for f in layout.soft_findings()}


@needs_tectonic
def test_unbreakable_token_runs_into_the_margin(base):
    content = base.content()
    content.jobs[1].bullets[0].text += " " + "x" * 80
    _, layout = build(base, content)
    failures = layout.hard_failures()
    assert [f["code"] for f in failures] == ["overfull_line"]
    assert failures[0]["where"] == "j2#1"


@needs_tectonic
def test_compile_cleans_up_and_leaves_the_template_alone(base, tmp_path, monkeypatch):
    def digests():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in TEMPLATE_DIR.iterdir() if p.is_file()}

    before = digests()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    resume_checks.compile_tex(resume_model.render(base, base.content()).tex, CLS)
    assert list(tmp_path.iterdir()) == []
    assert digests() == before


def test_compile_reports_a_missing_compiler(monkeypatch):
    monkeypatch.setattr(resume_checks.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("tectonic")))
    with pytest.raises(resume_checks.CompileError, match="could not run tectonic"):
        resume_checks.compile_tex("x", CLS)


def test_compile_reports_a_timeout(monkeypatch):
    def hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(resume_checks.subprocess, "run", hang)
    with pytest.raises(resume_checks.CompileError, match="timed out"):
        resume_checks.compile_tex("x", CLS)


# --- the no-fabrication guards ---

import resume_terms  # noqa: E402
from resume_terms import Approved, Terms  # noqa: E402
from tests.tailoring_fixtures import (ANALYSIS, FACTS_PROFILE, content_json, prepare, run_tool,  # noqa: E402
                                     weak_analysis, write_coverage, write_out, write_terms)

KEYWORDS = ANALYSIS["keywords"]
# Airflow approved with resume evidence from j1.b5 ("DAG orchestration"); Kafka rejected.
FROM_RESUME = Terms([Approved("Airflow", [], ["j1.b5"], ["DAG orchestration"], [])], [{"term": "Kafka", "reason": "x"}])
FROM_PROFILE = Terms([Approved("Airflow", [], [], [], ["Airflow"])], [])


def codes(base, content, terms=None):
    errors, _ = resume_checks.check_content(base, content, KEYWORDS, terms)
    return [e["code"] for e in errors]


def edited(base, change):
    content = base.content()
    change(content)
    return content


@pytest.mark.parametrize("change, code", [
    (lambda c: c.jobs.pop(), "structure_mismatch"),
    (lambda c: c.skills.append(resume_model.SkillLine("Streaming", ["Python"])), "unknown_label"),
    (lambda c: c.skills[0].items.append("Kafka"), "unknown_skill"),
    (lambda c: setattr(c.jobs[0].bullets[0], "sources", []), "missing_source"),
    (lambda c: setattr(c.jobs[0].bullets[0], "sources", ["j1.b9"]), "missing_source"),
    (lambda c: setattr(c.jobs[0].bullets[0], "sources", ["j3.b1"]), "foreign_source"),
    (lambda c: setattr(c.jobs[0].bullets[2], "text", c.jobs[0].bullets[2].text.replace("75%", "80%")), "unsupported_number"),
    (lambda c: setattr(c.jobs[1].bullets[0], "text", c.jobs[1].bullets[0].text + " Streamed with Kafka."), "unsupported_keyword"),
    (lambda c: setattr(c.jobs[0].bullets[0], "text", r"Did \input{x}."), "invalid_text"),
])
def test_each_guard_rejects_its_case(base, change, code):
    assert code in codes(base, edited(base, change))


def test_dropping_every_kubernetes_mention_loses_a_keyword(base):
    def change(c):
        c.jobs[3].bullets = c.jobs[3].bullets[:3]  # j4.b4 is the Kubernetes migration
        for line in c.skills:
            line.items = [item for item in line.items if item != "Kubernetes"]
    assert codes(base, edited(base, change)) == ["lost_keyword"]


def test_honest_edits_are_accepted(base):
    def change(c):
        tools = c.skills[1]
        tools.items.remove("PyTorch")
        tools.items.insert(0, "PyTorch")
        c.skills[6].items.remove("Tableau")
        merged = resume_model.ContentBullet(
            "Increased classification throughput by **30%** through document segmentation using **Faster-RCNN**, "
            "and enhanced OCR quality with custom **image preprocessing** (denoising, deskewing).",
            ["j3.b2", "j3.b3"])
        c.jobs[2].bullets[1:3] = [merged]
    assert codes(base, edited(base, change)) == []


def test_overlong_bullet_is_rejected(base):
    def change(c):
        b4, b5 = c.jobs[0].bullets[3], c.jobs[0].bullets[4]
        c.jobs[0].bullets[3:5] = [resume_model.ContentBullet(b4.text + " " + b5.text, b4.sources + b5.sources)]
    errors, _ = resume_checks.check_content(base, edited(base, change), KEYWORDS)
    assert [(e["code"], e["where"]) for e in errors] == [("invalid_text", "j1#4")]
    assert "at most 400" in errors[0]["detail"]


def add_to_bullet(job: int, n: int, text: str):
    def change(c):
        c.jobs[job].bullets[n].text = c.jobs[job].bullets[n].text.removesuffix(".") + text
    return change


def test_approved_keyword_goes_where_its_evidence_is(base):
    in_skills = edited(base, lambda c: c.skills[2].items.append("Airflow"))
    in_its_bullet = edited(base, add_to_bullet(0, 4, ", in the style of Airflow."))  # j1#5 cites j1.b5
    assert codes(base, in_skills, FROM_RESUME) == codes(base, in_its_bullet, FROM_RESUME) == []
    assert codes(base, in_skills) == ["unknown_skill", "unsupported_keyword"]  # no ruling: not allowed


def test_approved_keyword_in_another_bullet_is_misplaced(base):
    elsewhere = edited(base, add_to_bullet(3, 1, ", scheduled with Airflow."))  # j4#2 cites j4.b2
    errors, _ = resume_checks.check_content(base, elsewhere, KEYWORDS, FROM_RESUME)
    assert [(e["code"], e["where"]) for e in errors] == [("misplaced_keyword", "j4#2")]
    assert "skills lines, and bullets citing j1.b5" in errors[0]["detail"]


def test_keyword_approved_from_the_profile_stays_in_skills_lines(base):
    assert codes(base, edited(base, lambda c: c.skills[2].items.append("Airflow")), FROM_PROFILE) == []
    errors, _ = resume_checks.check_content(base, edited(base, add_to_bullet(0, 4, ", in Airflow.")), KEYWORDS, FROM_PROFILE)
    assert [e["code"] for e in errors] == ["misplaced_keyword"] and "skills lines only" in errors[0]["detail"]


def test_rejected_keyword_is_still_unsupported(base):
    assert codes(base, edited(base, add_to_bullet(1, 0, " with Kafka.")), FROM_RESUME) == ["unsupported_keyword"]


def test_bold_approved_keyword_is_no_new_phrase(base):
    _, warnings = resume_checks.check_content(base, edited(base, add_to_bullet(0, 4, ", like **Airflow**.")), KEYWORDS,
                                              FROM_RESUME)
    assert warnings == []


def test_added_keywords_lists_what_the_content_uses(base):
    assert resume_checks.added_keywords(base, base.content(), FROM_RESUME) == []
    content = edited(base, lambda c: c.skills[2].items.append("Airflow"))
    assert resume_checks.added_keywords(base, content, FROM_RESUME) == ["Airflow"]


def test_soft_warnings(base):
    def change(c):
        c.jobs[1].bullets[0].text = "Built **document AI pipelines** on 10M+ tweets"
    _, warnings = resume_checks.check_content(base, edited(base, change), KEYWORDS)
    assert {w["code"] for w in warnings} == {"new_bold_phrase", "no_final_period"}


# --- echoed posting phrasing ---

POSTING = ("Work with research to develop and run evals to measure agent performance, regressions, failure modes, "
           "and edge cases. You turn natural-language mapping instructions into PySpark code deployable as AWS Glue jobs.")


def echoes(base, content):
    errors, warnings = resume_checks.check_content(base, content, KEYWORDS, posting=POSTING)
    return errors, [(w["where"], w["detail"].split('"')[1]) for w in warnings if w["code"] == "echoed_phrase"]


def test_a_phrase_copied_from_the_posting_is_flagged(base):
    content = edited(base, add_to_bullet(0, 2, ", measuring regressions, failure modes and edge cases."))
    errors, found = echoes(base, content)
    assert errors == [] and found == [("j1#3", "regressions failure modes and edge cases")]


def test_a_phrase_the_sources_already_use_is_not_flagged(base):
    assert echoes(base, base.content()) == ([], [])  # j1.b4 says "PySpark code deployable as AWS Glue jobs" too


def test_short_or_stopword_runs_are_not_flagged(base):
    content = edited(base, add_to_bullet(0, 2, ", with failure modes in mind."))  # "failure modes" alone: 2 words
    assert echoes(base, content) == ([], [])


def test_without_the_posting_nothing_is_flagged(base):
    content = edited(base, add_to_bullet(0, 2, ", measuring regressions, failure modes and edge cases."))
    _, warnings = resume_checks.check_content(base, content, KEYWORDS)
    assert warnings == []


@needs_tectonic
def test_build_reads_the_posting_and_reports_echoes_as_aims(base, tmp_path):
    work = prepare(tmp_path / "work")
    (work / "posting.md").write_text(POSTING)
    write_out(work, "analysis.json", ANALYSIS)
    data = content_json(base)
    data["jobs"][0]["bullets"][2]["text"] = data["jobs"][0]["bullets"][2]["text"].removesuffix(".") + \
        ", measuring failure modes and edge cases."
    write_out(work, "tailored.json", data)
    write_terms(work)
    write_coverage(work, ANALYSIS)
    r = run_tool("build", "--work", str(work))
    assert r.returncode == 0 and 'aim  echoed_phrase j1#3: "failure modes and edge cases"' in r.stdout


# --- profile facts as sources ---

@pytest.fixture(scope="module")
def base_facts():
    base = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
    return resume_terms.attach_facts(base, resume_terms.parse_profile(FACTS_PROFILE))


def from_fact(text: str, sources=("j1.f1",), job: int = 0):
    def change(c):
        c.jobs[job].bullets.insert(0, resume_model.ContentBullet(text, list(sources)))
    return change


def test_a_bullet_may_come_from_a_profile_fact(base_facts):
    content = edited(base_facts, from_fact("Ran replay benchmarks comparing **3 model families** on the mapping task."))
    errors, warnings = resume_checks.check_content(base_facts, content, KEYWORDS)
    assert (errors, warnings) == ([], [])


def test_a_fact_stays_under_its_own_job(base_facts):
    content = edited(base_facts, from_fact("Ran replay benchmarks on the mapping task.", job=2))
    assert codes(base_facts, content) == ["foreign_source"]


def test_numbers_may_come_from_a_cited_fact(base_facts):
    assert codes(base_facts, edited(base_facts, from_fact("Compared 4 model families."))) == ["unsupported_number"]
    merged = from_fact("Compared 3 model families, reaching 75% source-field recall.", sources=("j1.f1", "j1.b3"))
    assert codes(base_facts, edited(base_facts, merged)) == []


def test_a_keyword_a_fact_states_goes_where_the_fact_is(base_facts):
    terms = Terms(resume_terms.from_facts(base_facts, KEYWORDS), [])
    cited = edited(base_facts, from_fact("Ran Kafka replay benchmarks on the mapping task."))
    assert codes(base_facts, cited, terms) == []
    elsewhere = edited(base_facts, from_fact("Ran Kafka replay benchmarks on the mapping task.", sources=("j1.b3",)))
    assert codes(base_facts, elsewhere, terms) == ["misplaced_keyword"]


def test_a_fact_the_profile_lacks_is_no_source(base):
    assert codes(base, edited(base, from_fact("Ran replay benchmarks on the mapping task."))) == ["missing_source"]


@needs_tectonic
def test_build_on_the_base_content_passes_and_names_short_lines(base, tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    write_out(work, "tailored.json", content_json(base))
    write_terms(work)
    write_coverage(work, ANALYSIS)
    r = run_tool("build", "--work", str(work))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "build 1: passed every hard check" in r.stdout
    assert "short_last_line j4#1 (from j4.b1)" in r.stdout
    report = __import__("json").loads((work / "out" / "check.json").read_text())
    assert report["passed"] and report["layout"]["pages"] == 1
    assert (work / "out" / "build" / "tailored.pdf").is_file()


@needs_tectonic
def test_build_reports_failures_and_counts_builds(base, tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    data = content_json(base)
    data["skills"][0]["items"].append("Kafka")
    write_out(work, "tailored.json", data)
    write_terms(work)
    run_tool("build", "--work", str(work))
    r = run_tool("build", "--work", str(work))
    assert r.returncode == 1 and "build 2: FAILED" in r.stdout and "unknown_skill" in r.stdout


def test_build_waits_for_the_judge(base, tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    write_out(work, "tailored.json", content_json(base))
    r = run_tool("build", "--work", str(work))
    assert r.returncode == 1 and "build refused" in r.stdout and "waiting for the judge" in r.stdout
    assert not (work / "out" / "check.json").exists()


# --- the coverage plan ---

def plan_findings(base, plan, analysis=None):
    return [(e.get("where"), e["detail"]) for e in resume_checks.check_coverage(plan, analysis or weak_analysis(), base)]


def test_a_complete_plan_passes(base_facts):
    plan = {"R2": {"sources": ["j1.b4", "j1.f1"], "note": "the Glue platform"}, "R3": {"sources": []}}
    assert plan_findings(base_facts, plan) == []


def test_plan_problems_are_named(base):
    assert plan_findings(base, None)[0][0] is None
    assert plan_findings(base, {"R2": {"sources": ["j1.b9"]}, "R7": {"sources": []}}) == [
        ("R3", "the base resume does not meet it; plan it"),
        ("R2", "j1.b9 is not a base bullet or a profile fact"),
        ("R7", "not a requirement of out/analysis.json")]
    assert plan_findings(base, {"R2": {"sources": "j1.b4"}, "R3": {}})[0][0] == "R2"


def test_planned_requirements_still_not_met_are_listed():
    plan = {"R2": {"sources": ["j1.b4"]}, "R3": {"sources": []}}
    assessment = {"R2": {"status": "partial", "evidence": []}, "R3": {"status": "missing", "evidence": []}}
    assert resume_checks.planned_not_met(plan, assessment) == ["planned, not met: R2 (j1.b4); assessed partial"]
    assert resume_checks.planned_not_met(plan, {"R2": {"status": "met"}}) == []


@needs_tectonic
def test_build_needs_the_plan_and_score_reports_it(base, tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", weak_analysis())
    write_out(work, "tailored.json", content_json(base))
    write_terms(work)
    r = run_tool("build", "--work", str(work))
    assert r.returncode == 1 and "fix  coverage_plan: write out/coverage.json first" in r.stdout
    write_coverage(work, weak_analysis(), {"R2": ["j1.b4"]})
    assert run_tool("build", "--work", str(work)).returncode == 0
    write_out(work, "assessment_tailored.json", weak_analysis()["assessment"])
    r = run_tool("score", "tailored", "--work", str(work))
    assert r.returncode == 0 and "planned, not met: R2 (j1.b4); assessed missing" in r.stdout
