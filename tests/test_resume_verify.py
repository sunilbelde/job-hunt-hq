import json
import shutil

import pdfplumber
import pytest

import resume_model
from app.rendering import TEMPLATE_DIR
from tests.tailoring_fixtures import (ANALYSIS, FACTS_PROFILE, PROFILE, content_json, prepare, run_tool, weak_analysis,
                                     write_out)

BASE = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
needs_tectonic = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")


def verify(work, pdf, *extra):
    r = run_tool("verify", "--template", str(TEMPLATE_DIR), "--work", str(work), "--pdf-out", str(pdf), *map(str, extra))
    return r.returncode, json.loads(r.stdout)


def ruling(tmp_path, approve_airflow=True):
    """The service's analysis copy and ruling for the weak match, as judge-input and judge-result write them."""
    gate = tmp_path / "gate"
    gate.mkdir(parents=True)
    (gate / "analysis.json").write_text(json.dumps(weak_analysis()))
    (tmp_path / "PROFILE.md").write_text(PROFILE)
    verdicts = {"verdicts": [{"term": "Airflow", "approved": approve_airflow, "profile": ["Airflow"]}]}
    (gate / "verdicts.json").write_text(json.dumps(verdicts))
    r = run_tool("judge-result", "--template", str(TEMPLATE_DIR), "--profile", str(tmp_path / "PROFILE.md"),
                 "--analysis", str(gate / "analysis.json"), "--verdicts", str(gate / "verdicts.json"),
                 "--out", str(gate / "terms.json"))
    assert r.returncode == 0, r.stdout + r.stderr
    return gate


def pdf_text(path) -> str:
    with pdfplumber.open(path) as pdf:
        return " ".join(" ".join(page.extract_text().split()) for page in pdf.pages)


def tailored_run(tmp_path, name="work", change=None):
    """A finished run for the weak match (base score 57): PyTorch moved to the front of its skills line."""
    work = prepare(tmp_path / name)
    write_out(work, "analysis.json", weak_analysis())
    content = content_json(BASE)
    items = content["skills"][1]["items"]
    items.insert(0, items.pop(items.index("PyTorch")))
    if change:
        change(content)
    write_out(work, "tailored.json", content)
    write_out(work, "assessment_tailored.json", ANALYSIS["assessment"])
    return work


def test_strong_match_keeps_the_base_resume(tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", ANALYSIS)
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 0
    base = out.pop("base")
    assert out == {"ok": True, "decision": "keep", "base_score": 77, "tailored_score": None, "failed": [], "warnings": [],
                   "added_terms": [], "tailored": None, "rejected_terms": []}
    assert (base["score"], [r["evidence"] for r in base["requirements"]]) == (
        77, [r["evidence"] for r in ANALYSIS["assessment"].values()])
    assert not (tmp_path / "resume.pdf").exists()


@needs_tectonic
def test_weak_match_gives_a_checked_one_page_pdf(tmp_path):
    work = tailored_run(tmp_path)
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 0, out
    assert (out["ok"], out["decision"], out["base_score"], out["tailored_score"]) == (True, "tailor", 57, 77)
    assert out["warnings"] == ["short_last_line"]  # the base's own j4.b1-b3, untouched here
    with pdfplumber.open(tmp_path / "resume.pdf") as pdf:
        assert len(pdf.pages) == 1
    assert "Machine Learning & GenAI: PyTorch, Transformers" in pdf_text(tmp_path / "resume.pdf")


@needs_tectonic
def test_changes_inside_the_work_folder_are_ignored(tmp_path):
    clean = tailored_run(tmp_path, "clean")
    tampered = tailored_run(tmp_path, "tampered")
    base_tex = tampered / "template" / "BASE.tex"
    base_tex.write_text(base_tex.read_text(encoding="utf-8").replace("Python, Java", "Python, Kafka, Java"), encoding="utf-8")
    (tampered / "template" / "resume.cls").write_text("\\ProvidesClass{resume}\n% broken\n")
    (tampered / "out" / "build").mkdir(parents=True, exist_ok=True)
    (tampered / "out" / "build" / "tailored.pdf").write_bytes(b"%PDF-1.5 a run's own file")

    first = verify(clean, tmp_path / "clean.pdf")
    second = verify(tampered, tmp_path / "tampered.pdf")
    assert first == second and first[0] == 0
    assert pdf_text(tmp_path / "clean.pdf") == pdf_text(tmp_path / "tampered.pdf")
    assert "Kafka" not in pdf_text(tmp_path / "tampered.pdf")


@pytest.mark.parametrize("missing", ["tailored.json", "assessment_tailored.json"])
def test_missing_output_fails(tmp_path, missing):
    work = tailored_run(tmp_path)
    (work / "out" / missing).unlink()
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 1
    assert (out["ok"], out["stage"], out["failed"], out["base_score"]) == (False, "output", ["missing_output"], 57)
    assert (out["base"]["score"], out["tailored"]) == (57, None)
    assert not (tmp_path / "resume.pdf").exists()


@needs_tectonic
def test_failing_content_lists_its_codes(tmp_path):
    work = tailored_run(tmp_path, change=lambda c: c["skills"][0]["items"].append("Kafka"))
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 1
    assert (out["stage"], out["failed"]) == ("content", ["unknown_skill", "unsupported_keyword"])
    assert not (tmp_path / "resume.pdf").exists()


def test_unrenderable_content_fails_without_compiling(tmp_path):
    work = tailored_run(tmp_path, change=lambda c: c["jobs"].pop())
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 1 and (out["stage"], out["failed"]) == ("content", ["structure_mismatch"])


def test_bad_analysis_fails(tmp_path):
    work = prepare(tmp_path / "work")
    write_out(work, "analysis.json", {"keywords": [], "requirements": [], "assessment": {}})
    code, out = verify(work, tmp_path / "resume.pdf")
    assert code == 1 and (out["stage"], out["failed"]) == ("analysis", ["analysis_invalid"])


@needs_tectonic
def test_approved_keyword_passes_and_is_reported(tmp_path):
    work = tailored_run(tmp_path, change=lambda c: c["skills"][2]["items"].append("Airflow"))
    gate = ruling(tmp_path)
    code, out = verify(work, tmp_path / "resume.pdf", "--analysis", gate / "analysis.json", "--terms", gate / "terms.json")
    assert code == 0, out
    assert (out["tailored_score"], out["added_terms"]) == (81, ["Airflow"])
    assert (out["base"]["score"], out["tailored"]["score"]) == (57, 81)
    assert [k["term"] for k in out["tailored"]["keywords"] if not k["present"]] == ["Kafka"]
    assert out["rejected_terms"] == [{"term": "Kafka", "reason": "no verdict"}]


@needs_tectonic
def test_without_a_ruling_no_new_keyword_passes(tmp_path):
    work = tailored_run(tmp_path, change=lambda c: c["skills"][2]["items"].append("Airflow"))
    gate = ruling(tmp_path, approve_airflow=False)
    for extra in ([], ["--terms", gate / "terms.json"]):
        code, out = verify(work, tmp_path / "resume.pdf", *extra)
        assert code == 1 and out["failed"] == ["unknown_skill", "unsupported_keyword"]


@needs_tectonic
def test_the_work_folders_ruling_and_analysis_are_not_trusted(tmp_path):
    work = tailored_run(tmp_path, change=lambda c: c["skills"][2]["items"].append("Airflow"))
    gate = ruling(tmp_path, approve_airflow=False)
    approving = ruling(tmp_path / "other")
    (work / "judge").mkdir()
    (work / "judge" / "terms.json").write_text((approving / "terms.json").read_text())  # the run's own copy says yes
    tampered = weak_analysis()
    tampered["keywords"] = [k for k in tampered["keywords"] if k["term"] != "Airflow"]
    write_out(work, "analysis.json", tampered)  # and it dropped Airflow from the keywords
    code, out = verify(work, tmp_path / "resume.pdf", "--analysis", gate / "analysis.json", "--terms", gate / "terms.json")
    assert code == 1 and out["failed"] == ["unknown_skill", "unsupported_keyword"]


FACT_BULLET = ("Evaluated the assistant on cross-domain benchmarks, achieving **75% source-field recall**, and "
               "tuned prompts against the benchmark after each model change.")


def add_fact_bullet(content):
    content["jobs"][0]["bullets"][2] = {"text": FACT_BULLET, "sources": ["j1.b3", "j1.f2"]}


@needs_tectonic
def test_a_bullet_from_a_profile_fact_passes_with_the_services_profile(tmp_path):
    work = tailored_run(tmp_path, change=add_fact_bullet)
    (tmp_path / "PROFILE.md").write_text(FACTS_PROFILE)
    code, out = verify(work, tmp_path / "resume.pdf", "--profile", tmp_path / "PROFILE.md")
    assert code == 0 and out["ok"], out
    assert "tuned prompts against the benchmark after each model change." in pdf_text(tmp_path / "resume.pdf")


def test_a_fact_the_run_adds_fails_at_the_gate(tmp_path):
    """The run writes a fact into its own out/base.json and cites it; the service's profile has no such fact."""
    work = tailored_run(tmp_path, change=add_fact_bullet)
    base = json.loads((work / "out" / "base.json").read_text())
    base["jobs"][0]["facts"] = [{"id": "j1.f2", "text": "Tuned prompts against the benchmark after each model change."}]
    write_out(work, "base.json", base)
    (tmp_path / "PROFILE.md").write_text(PROFILE)
    code, out = verify(work, tmp_path / "resume.pdf", "--profile", tmp_path / "PROFILE.md")
    assert (code, out["ok"], out["stage"], out["failed"]) == (1, False, "content", ["missing_source"])
    assert not (tmp_path / "resume.pdf").exists()
