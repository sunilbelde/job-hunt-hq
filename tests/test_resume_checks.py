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

from resume_terms import Approved, Terms  # noqa: E402
from tests.tailoring_fixtures import ANALYSIS, content_json, prepare, run_tool, write_out, write_terms  # noqa: E402

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


@needs_tectonic
def test_build_on_the_base_content_passes_and_names_short_lines(base, tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    write_out(work, "tailored.json", content_json(base))
    write_terms(work)
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
