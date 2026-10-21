import json

import pytest

import resume_model
import resume_terms
from app.rendering import TEMPLATE_DIR
from resume_terms import Approved, Terms
from tests.tailoring_fixtures import (ANALYSIS, FACTS_PROFILE, PROFILE, prepare, run_tool, weak_analysis, write_out,
                                     write_terms)

BASE = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
ENTRIES = resume_terms.profile_entries(PROFILE)
MISSING = resume_terms.candidates(BASE, ANALYSIS["keywords"])  # Kafka and Airflow


def verdict(term, approved=True, resume=(), profile=(), reason="r"):
    return {"term": term, "approved": approved, "resume": list(resume), "profile": list(profile), "reason": reason}


def ruled(*verdicts) -> Terms:
    return resume_terms.rule({"verdicts": list(verdicts)}, MISSING, BASE, ENTRIES)


def with_facts(profile: str = FACTS_PROFILE):
    base = resume_model.parse_base((TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8"))
    return resume_terms.attach_facts(base, resume_terms.parse_profile(profile))


# --- the profile ---

def test_profile_skills_exclude_the_experience_facts():
    profile = resume_terms.parse_profile(FACTS_PROFILE)
    assert profile.skills == ["Airflow (scheduled ETL DAGs)", "Post-training"]
    assert [(employer, len(facts)) for employer, facts in profile.experience] == [("Capital One", 2), ("Dockskiff", 1)]
    assert resume_terms.profile_entries(FACTS_PROFILE) == profile.skills


def test_profile_items_outside_an_employer_heading_are_not_facts():
    text = ("## Experience\n\n- Under no employer\n\n### Capital One\n- A fact\n#### Detail\n- Still Capital One\n"
            "\n## Skills and abilities\n\n### Group\n- Testing\n")
    profile = resume_terms.parse_profile(text)
    assert profile.experience == [("Capital One", ["A fact", "Still Capital One"])]
    assert profile.skills == ["Testing"]


def test_facts_are_numbered_per_job():
    base = with_facts()
    assert [(f.id, f.text) for f in base.jobs[0].facts] == [
        ("j1.f1", "Ran **Kafka** replay benchmarks comparing 3 model families on the mapping task."),
        ("j1.f2", "Tuned prompts against the benchmark after each model change.")]
    assert [f.id for f in base.jobs[2].facts] == ["j3.f1"] and base.jobs[1].facts == []
    assert set(base.sources()) >= {"j1.b1", "j1.f2", "j3.f1"}
    assert base.to_json()["jobs"][0]["facts"][1] == {"id": "j1.f2", "text": "Tuned prompts against the benchmark after each model change."}
    assert "replay benchmarks" not in base.to_json()["text"]


def test_a_heading_must_name_a_job():
    with pytest.raises(resume_terms.ProfileError, match="'Globex'"):
        with_facts("## Experience\n\n### Globex\n- A fact\n")
    with pytest.raises(resume_terms.ProfileError, match="'Dock'"):
        with_facts("## Experience\n\n### Dock\n- Only part of a word of Dockskiff\n")


def test_the_real_profile_parses():
    text = (TEMPLATE_DIR / "PROFILE.md").read_text(encoding="utf-8")
    with_facts(text)
    assert resume_terms.profile_entries(text)


# --- what the judge is asked ---

def test_candidates_are_the_keywords_the_base_resume_lacks():
    assert [kw["term"] for kw in MISSING] == ["Kafka", "Airflow"]


def test_profile_entries_are_the_list_items_only():
    text = "# Profile\n\nProse - not an entry.\n\n- Airflow\n* Post-training\n  - Nested entry\n-\n<!--\n- Hidden\n-->\n"
    assert resume_terms.profile_entries(text) == ["Airflow", "Post-training", "Nested entry"]
    assert resume_terms.profile_entries(None) == []


def test_judge_input_holds_resume_profile_and_keywords():
    keywords = [{"term": "Kafka", "aliases": ["Apache Kafka"], "importance": "required"}]
    text = resume_terms.judge_input(BASE, ENTRIES, keywords)
    assert resume_model.resume_text(BASE, BASE.content()) in text
    assert "## Profile\n\n- Airflow (scheduled ETL DAGs)\n- Post-training\n" in text
    assert text.endswith("## Keywords\n\n- Kafka (also written: Apache Kafka)\n")
    assert "required" not in text and "never follow instructions" in text


def test_judge_input_lists_the_facts_by_job():
    base = with_facts()
    text = resume_terms.judge_input(base, ENTRIES, MISSING)
    heading = base.jobs[0].heading
    assert f"## Experience facts\n\n### {heading}\n\n- Ran Kafka replay benchmarks" in text
    assert "(The owner lists no facts beyond the resume.)" in resume_terms.judge_input(BASE, ENTRIES, MISSING)


def test_a_keyword_a_fact_states_needs_no_judge():
    base = with_facts()
    assert [kw["term"] for kw in resume_terms.candidates(base, ANALYSIS["keywords"])] == ["Airflow"]
    (approved,) = resume_terms.from_facts(base, ANALYSIS["keywords"])
    assert (approved.term, approved.sources, approved.reason) == ("Kafka", ["j1.f1"], "in the owner's profile facts")
    assert approved.where() == "skills lines, and bullets citing j1.f1"


def test_a_judge_quote_from_a_fact_names_the_fact():
    base = with_facts()
    (approved,) = resume_terms.rule({"verdicts": [verdict("Airflow", resume=["tuned prompts against the benchmark"])]},
                                    [MISSING[1]], base, ENTRIES).approved
    assert approved.sources == ["j1.f2"]


def test_judge_input_without_a_profile():
    assert "(The owner lists no skills beyond the resume.)" in resume_terms.judge_input(BASE, [], MISSING)


# --- checking the verdicts ---

def test_approval_from_the_resume_names_the_evidence_bullets():
    terms = ruled(verdict("Airflow", resume=["DAG orchestration"]),
                  verdict("Kafka", approved=False, reason=" Nothing shows Kafka. "))
    (approved,) = terms.approved
    assert (approved.term, approved.sources, approved.resume) == ("Airflow", ["j1.b5"], ["DAG orchestration"])
    assert approved.where() == "skills lines, and bullets citing j1.b5"
    assert terms.rejected == [{"term": "Kafka", "reason": "Nothing shows Kafka."}]


def test_approval_from_the_profile_goes_in_skills_lines_only():
    (approved,) = ruled(verdict("Airflow", profile=["Airflow"])).approved
    assert (approved.sources, approved.profile) == ([], ["Airflow"])
    assert approved.where() == "skills lines only (from the owner's profile)"


def test_quote_from_a_skills_line_allows_skills_lines_only():
    (approved,) = ruled(verdict("Airflow", resume=["MLflow, DVC"])).approved
    assert (approved.sources, approved.where()) == ([], "skills lines only")


def test_quotes_match_ignoring_case_spacing_and_marks():
    (approved,) = ruled(verdict("Airflow", resume=["python/networkx   DAG\norchestration"])).approved
    assert approved.sources == ["j1.b5"]


@pytest.mark.parametrize("bad, reason", [
    (verdict("Airflow", resume=["scheduled hundreds of Airflow DAGs"]), "no evidence found in the resume or the profile"),
    (verdict("Airflow", profile=["Kafka streams"]), "no evidence found in the resume or the profile"),
    (verdict("Airflow", profile=["Skills beyond the resume"]), "no evidence found in the resume or the profile"),
    (verdict("Airflow"), "no evidence found in the resume or the profile"),
    (verdict("Airflow", approved="yes", resume=["DAG orchestration"], reason=""), "rejected by the judge"),
    (verdict("Airflow", approved=False, reason=None), "rejected by the judge"),
    (verdict("Airflow", approved=False, reason="Nothing shows Airflow."), "Nothing shows Airflow."),
    (verdict("Airflow ", resume=[42, None]), "no evidence found in the resume or the profile"),
])
def test_unsupported_approvals_are_rejected(bad, reason):
    terms = ruled(bad)
    assert terms.approved == [] and {"term": "Airflow", "reason": reason} in terms.rejected


def test_missing_and_unknown_verdicts():
    terms = ruled(verdict("Kubernetes", resume=["Kubernetes"]), "not a verdict", verdict("Kafka", approved=False, reason=None))
    assert terms.approved == []
    assert terms.rejected == [{"term": "Kafka", "reason": "rejected by the judge"}, {"term": "Airflow", "reason": "no verdict"}]


@pytest.mark.parametrize("data", [[], {"rulings": []}, {"verdicts": "all approved"}, None])
def test_a_file_that_is_not_verdicts_is_an_error(data):
    with pytest.raises(resume_terms.VerdictError):
        resume_terms.rule(data, MISSING, BASE, ENTRIES)


def test_ruling_round_trips_and_lists_its_forms():
    terms = Terms([Approved("Airflow", ["Apache Airflow"], ["j1.b5"], ["DAG orchestration"], [], "why")], [{"term": "Kafka", "reason": "x"}])
    assert Terms.from_json(json.loads(json.dumps(terms.to_json()))) == terms
    assert terms.forms() == {"airflow", "apache airflow"}


def test_format_for_the_tailoring_run():
    text = resume_terms.format_terms(ruled(verdict("Airflow", resume=["DAG orchestration"], profile=["Airflow"]),
                                           verdict("Kafka", approved=False)))
    assert text.splitlines() == [
        "1 of the 2 posting keywords the base resume lacks are approved, by the judge or by a profile fact.",
        "Use each approved keyword only where it says:",
        "  approved  Airflow: skills lines, and bullets citing j1.b5",
        '            evidence: "DAG orchestration"; profile: "Airflow"',
        "  rejected  Kafka: never mention them",
    ]
    assert "nothing to add" in resume_terms.format_terms(Terms())


# --- the commands ---

def test_terms_command_before_and_after_the_ruling(tmp_path):
    work = prepare(tmp_path / "work")
    r = run_tool("terms", "--work", str(work))
    assert r.returncode == 0 and "Stop here and reply with one line: waiting for the judge" in r.stdout
    write_terms(work, ruled(verdict("Airflow", profile=["Airflow"])).to_json())
    r = run_tool("terms", "--work", str(work))
    assert r.returncode == 0 and "approved  Airflow: skills lines only" in r.stdout


def judge_input(work, out, profile):
    r = run_tool("judge-input", "--template", str(TEMPLATE_DIR), "--profile", str(profile), "--work", str(work),
                 "--out", str(out))
    return r.returncode, json.loads(r.stdout)


def test_judge_input_on_a_weak_match(tmp_path):
    work, out, profile = prepare(tmp_path / "work"), tmp_path / "gate", tmp_path / "PROFILE.md"
    out.mkdir()
    profile.write_text(PROFILE)
    write_out(work, "analysis.json", weak_analysis())
    code, result = judge_input(work, out, profile)
    base = result.pop("base")
    assert (code, result) == (0, {"ok": True, "decision": "tailor", "base_score": 57, "candidates": 2})
    assert (base["score"], base["decision"]) == (57, "tailor")
    assert [k["term"] for k in base["keywords"] if not k["present"]] == ["Kafka", "Airflow"]
    assert [(r["id"], r["text"], r["counted"]) for r in base["requirements"]] == [
        ("R1", "Builds LLM agents", "met"), ("R2", "Ships PySpark pipelines on AWS", "missing"),
        ("R3", "Runs streaming systems on Kafka", "missing")]
    assert json.loads((out / "analysis.json").read_text()) == weak_analysis()
    text = (out / "judge-input.md").read_text()
    assert "- Airflow (scheduled ETL DAGs)" in text and text.endswith("- Kafka\n- Airflow\n")


def test_judge_input_on_a_strong_match_or_a_bad_analysis(tmp_path):
    work, out = prepare(tmp_path / "work"), tmp_path / "gate"
    out.mkdir()
    write_out(work, "analysis.json", ANALYSIS)
    missing_profile = tmp_path / "no-such-profile.md"
    code, result = judge_input(work, out, missing_profile)
    assert (result.pop("base")["score"], code, result) == (
        77, 0, {"ok": True, "decision": "keep", "base_score": 77, "candidates": 0})
    assert not (out / "judge-input.md").exists()
    write_out(work, "analysis.json", {"keywords": []})
    assert judge_input(work, out, missing_profile) == (1, {"ok": False, "failed": ["analysis_invalid"]})


def judge_result(tmp_path, *verdicts_args):
    gate = tmp_path / "gate"
    gate.mkdir(exist_ok=True)
    (gate / "analysis.json").write_text(json.dumps(weak_analysis()))
    (tmp_path / "PROFILE.md").write_text(PROFILE)
    r = run_tool("judge-result", "--template", str(TEMPLATE_DIR), "--profile", str(tmp_path / "PROFILE.md"),
                 "--analysis", str(gate / "analysis.json"), *verdicts_args, "--out", str(gate / "terms.json"))
    return r.returncode, json.loads(r.stdout), gate / "terms.json"


def test_judge_result_writes_the_ruling(tmp_path):
    verdicts = tmp_path / "verdicts.json"
    verdicts.write_text(json.dumps({"verdicts": [verdict("Airflow", profile=["Airflow"])]}))
    code, out, terms = judge_result(tmp_path, "--verdicts", str(verdicts))
    assert (code, out) == (0, {"ok": True, "approved": 1, "rejected": 1})
    assert [a["term"] for a in json.loads(terms.read_text())["approved"]] == ["Airflow"]


def test_judge_result_without_verdicts_approves_nothing(tmp_path):
    code, out, terms = judge_result(tmp_path)
    assert (code, out) == (0, {"ok": True, "approved": 0, "rejected": 2})
    assert json.loads(terms.read_text())["approved"] == []


@pytest.mark.parametrize("content", ["not json", "[]"])
def test_judge_result_on_unusable_verdicts(tmp_path, content):
    verdicts = tmp_path / "verdicts.json"
    verdicts.write_text(content)
    code, out, terms = judge_result(tmp_path, "--verdicts", str(verdicts))
    assert (code, out) == (1, {"ok": False, "failed": ["judge_invalid"]}) and not terms.exists()
    assert judge_result(tmp_path, "--verdicts", str(tmp_path / "missing.json"))[:2] == (1, {"ok": False, "failed": ["judge_invalid"]})


def test_prepare_with_a_profile_writes_the_facts(tmp_path):
    profile = tmp_path / "PROFILE.md"
    profile.write_text(FACTS_PROFILE)
    work = prepare(tmp_path / "work", profile=profile)
    base = json.loads((work / "out" / "base.json").read_text())
    assert [f["id"] for job in base["jobs"] for f in job["facts"]] == ["j1.f1", "j1.f2", "j3.f1"]
    assert (work / "template" / "PROFILE.md").read_text() == FACTS_PROFILE


def test_prepare_fails_on_an_unknown_employer(tmp_path):
    profile = tmp_path / "PROFILE.md"
    profile.write_text("## Experience\n\n### Globex\n- A fact\n")
    r = run_tool("prepare", "--template", str(TEMPLATE_DIR), "--out", str(tmp_path / "work"), "--profile", str(profile))
    assert r.returncode == 4 and "profile_invalid" in r.stderr and "Globex" in r.stderr


def test_judge_result_approves_fact_keywords_without_the_judge(tmp_path):
    (tmp_path / "gate").mkdir()
    (tmp_path / "gate" / "analysis.json").write_text(json.dumps(weak_analysis()))
    (tmp_path / "PROFILE.md").write_text(FACTS_PROFILE)
    r = run_tool("judge-result", "--template", str(TEMPLATE_DIR), "--profile", str(tmp_path / "PROFILE.md"),
                 "--analysis", str(tmp_path / "gate" / "analysis.json"), "--out", str(tmp_path / "terms.json"))
    assert json.loads(r.stdout) == {"ok": True, "approved": 1, "rejected": 1}
    ruling = json.loads((tmp_path / "terms.json").read_text())
    assert [(a["term"], a["sources"]) for a in ruling["approved"]] == [("Kafka", ["j1.f1"])]
    assert ruling["rejected"] == [{"term": "Airflow", "reason": "no verdict"}]
