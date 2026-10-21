"""Shared inputs for the tailor-resume tests: an analysis of a made-up posting against the real base resume."""
import copy
import json
import subprocess
import sys
from pathlib import Path

from app.rendering import TEMPLATE_DIR
from tests.conftest import SKILL_DIR

TOOL = SKILL_DIR / "scripts" / "resume_tool.py"

# Against data/BASE.tex: keywords 9 of 12 (Kafka and Airflow are missing), requirements 4 of 5, score 77.
ANALYSIS = {
    "keywords": [
        {"term": "Python", "aliases": [], "importance": "required"},
        {"term": "PyTorch", "aliases": [], "importance": "required"},
        {"term": "Kubernetes", "aliases": ["k8s"], "importance": "required"},
        {"term": "LangChain", "aliases": [], "importance": "preferred"},
        {"term": "retrieval-augmented generation", "aliases": ["RAG"], "importance": "required"},
        {"term": "Kafka", "aliases": [], "importance": "required"},
        {"term": "Airflow", "aliases": [], "importance": "preferred"},
    ],
    "requirements": [
        {"id": "R1", "text": "Builds LLM agents", "importance": "required"},
        {"id": "R2", "text": "Ships PySpark pipelines on AWS", "importance": "required"},
        {"id": "R3", "text": "Runs streaming systems on Kafka", "importance": "preferred"},
    ],
    "assessment": {
        "R1": {"status": "met", "evidence": ["ReAct agentic AI pattern to propose, critique, and refine"]},
        "R2": {"status": "met", "evidence": ["PySpark code deployable as AWS Glue jobs"]},
        "R3": {"status": "missing", "evidence": []},
    },
}


# The judge's verdicts on the two keywords the base resume lacks, given PROFILE below.
JUDGE_VERDICTS = {"verdicts": [
    {"term": "Kafka", "approved": False, "resume": [], "profile": [], "reason": "Nothing shows Kafka."},
    {"term": "Airflow", "approved": True, "resume": [], "profile": ["Airflow"], "reason": "The profile lists it."},
]}

PROFILE = """# Profile

Skills beyond the resume. Only the list below counts.

- Airflow (scheduled ETL DAGs)
- Post-training
"""


def weak_analysis() -> dict:
    """The same posting judged more strictly: requirements 2 of 5, score 57, so the resume gets tailored."""
    analysis = copy.deepcopy(ANALYSIS)
    analysis["assessment"]["R2"] = {"status": "missing", "evidence": []}
    return analysis


def run_tool(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=180, cwd=cwd)


def prepare(work: Path, template: Path = TEMPLATE_DIR) -> Path:
    result = run_tool("prepare", "--template", str(template), "--out", str(work))
    assert result.returncode == 0, result.stderr
    return work


def write_out(work: Path, name: str, data) -> None:
    (work / "out" / name).write_text(json.dumps(data), encoding="utf-8")


def write_terms(work: Path, terms: dict | None = None) -> None:
    """judge/terms.json, as the service writes it once the judge has ruled. Default: nothing approved."""
    (work / "judge").mkdir(exist_ok=True)
    (work / "judge" / "terms.json").write_text(json.dumps(terms or {"approved": [], "rejected": []}), encoding="utf-8")


def content_json(base) -> dict:
    """The base resume written as tailored.json: same skills, every bullet citing itself. Fresh lists, so
    editing the result never changes `base`."""
    return {
        "skills": [{"label": line.label, "items": list(line.items)} for line in base.skills],
        "jobs": [{"id": job.id, "bullets": [{"text": b.text, "sources": [b.id]} for b in job.bullets]}
                 for job in base.jobs],
    }
