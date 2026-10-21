import json
import subprocess
import sys

import pytest

import resume_model
from app.rendering import TEMPLATE_DIR
from resume_model import ContentError, ModelError, markup_to_tex, parse_base, render
from tests.conftest import SKILL_DIR

BASE_TEX = (TEMPLATE_DIR / "BASE.tex").read_text(encoding="utf-8")
TOOL = SKILL_DIR / "scripts" / "resume_tool.py"


@pytest.fixture(scope="module")
def base():
    return parse_base(BASE_TEX)


def run_tool(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=60)


def test_parses_the_real_base_resume(base):
    assert [job.id for job in base.jobs] == ["j1", "j2", "j3", "j4"]
    assert [len(job.bullets) for job in base.jobs] == [6, 2, 4, 4]
    assert len(base.skills) == 7
    assert base.skills[1].label == "Machine Learning & GenAI"
    assert "LLMs (Llama, Mistral)" in base.skills[1].items
    assert base.jobs[0].heading == "Capital One, ML Engineer – GenAI/LLM Automation | Chicago, IL | Jul 2024 – Present"
    assert base.jobs[3].bullets[0].id == "j4.b1"
    assert "**75% source-field recall**" in base.jobs[0].bullets[2].text


def test_base_content_renders_back_to_base_tex(base):
    def normalized(tex):
        return [" ".join(line.split()) for line in tex.split("\n")]

    # Only whitespace differs: one \item in BASE.tex has an extra space of indentation.
    assert normalized(render(base, base.content()).tex) == normalized(BASE_TEX)


def test_only_skills_and_bullet_lines_change(base):
    content = base.content()
    content.skills.reverse()
    content.jobs[0].bullets = content.jobs[0].bullets[:2]
    content.jobs[3].bullets[0].text = "Rewritten **bullet** that saved 15% of infra cost."
    rendered = render(base, content)

    replaced = set()
    for start, end in [base.skills_span] + [job.span for job in base.jobs]:
        replaced.update(range(start + 1, end + 1))
    kept = [line for n, line in enumerate(BASE_TEX.split("\n"), 1) if n not in replaced and line.strip()]
    others = [line for n, line in enumerate(rendered.tex.split("\n"), 1) if n not in rendered.line_map and line.strip()]
    assert others == kept

    refs = set(rendered.line_map.values())
    assert {"skills:Tools & Platforms", "j1#1", "j1#2", "j4#1"} <= refs and "j1#3" not in refs
    assert r"\item Rewritten \textbf{bullet} that saved 15\% of infra cost." in rendered.tex


def test_markup_escapes_tex_specials():
    assert markup_to_tex("R&D up 30% for $5 #1 a_b {x} ~ ^") == (
        r"R\&D up 30\% for \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{}")
    assert markup_to_tex("**bold** and *italic*") == r"\textbf{bold} and \textit{italic}"


@pytest.mark.parametrize("text", [r"\input{../.env}", "two\nlines", "a * b", "**unclosed"])
def test_unsafe_text_is_rejected(text):
    with pytest.raises(ContentError) as exc:
        markup_to_tex(text)
    assert exc.value.code == "invalid_text"


def test_unknown_command_names_its_line():
    lines = BASE_TEX.split("\n")
    n = next(i for i, line in enumerate(lines) if line.startswith(r"\textbf{Tools"))
    lines[n] = lines[n].replace("Tableau", r"\emph{Tableau}")
    with pytest.raises(ModelError, match=f"line {n + 1}:"):
        parse_base("\n".join(lines))


def test_bullet_continued_on_a_second_line_is_rejected():
    lines = BASE_TEX.split("\n")
    n = next(i for i, line in enumerate(lines) if r"\item Migrated legacy systems" in line)
    lines.insert(n + 1, "    and more text on the next line")
    with pytest.raises(ModelError, match=r"one \\item per line"):
        parse_base("\n".join(lines))


def test_split_items_keeps_parentheses_together():
    assert resume_model.split_items("AWS (EC2, S3), GCP,  Docker") == ["AWS (EC2, S3)", "GCP", "Docker"]


def test_resume_text_has_fixed_parts_and_plain_bullets(base):
    text = resume_model.resume_text(base, base.content())
    assert "University of Illinois Chicago" in text
    assert "AWS Solutions Architect – Associate" in text
    assert "75% source-field recall" in text and "**" not in text
    assert "SUNIL BELDE" not in text  # the name and contact line are not scored


def test_content_from_json_reads_tailored_content(base):
    data = {"skills": [{"label": " Cloud & DevOps ", "items": ["Docker ", "AWS (EC2, S3)"]}],
            "jobs": [{"id": "j1", "bullets": [{"text": "Did **this**.", "sources": ["j1.b1", "j1.b2"]}]}]}
    content = resume_model.content_from_json(data)
    assert content.skills[0].label == "Cloud & DevOps" and content.skills[0].items == ["Docker", "AWS (EC2, S3)"]
    assert content.jobs[0].bullets[0].sources == ["j1.b1", "j1.b2"]


@pytest.mark.parametrize("data", [
    [],
    {"skills": []},
    {"skills": [{"label": "x"}], "jobs": []},
    {"skills": [], "jobs": [{"id": "j1", "bullets": [{"text": "x"}]}]},
    {"skills": [], "jobs": [{"id": "j1", "bullets": [{"text": "x", "sources": "j1.b1"}]}]},
])
def test_content_shape_errors_are_structure_mismatch(data):
    with pytest.raises(ContentError) as exc:
        resume_model.content_from_json(data)
    assert exc.value.code == "structure_mismatch"


def test_prepare_makes_a_work_folder(tmp_path):
    posting = tmp_path / "posting.txt"
    posting.write_text("We need Python.")
    work = tmp_path / "work"
    r = run_tool("prepare", "--template", str(TEMPLATE_DIR), "--out", str(work), "--posting", str(posting))
    assert r.returncode == 0, r.stderr
    assert "4 jobs, 16 bullets, 0 profile facts, 7 skills lines" in r.stdout
    assert (work / "template" / "BASE.tex").read_text(encoding="utf-8") == BASE_TEX
    assert (work / "template" / "resume.cls").is_file()
    assert (work / "posting.md").read_text() == "We need Python."
    data = json.loads((work / "out" / "base.json").read_text(encoding="utf-8"))
    assert [job["id"] for job in data["jobs"]] == ["j1", "j2", "j3", "j4"]
    assert data["jobs"][3]["bullets"][0]["id"] == "j4.b1" and "Kubernetes" in data["text"]


def test_prepare_help_documents_its_arguments():
    r = run_tool("prepare", "--help")
    assert r.returncode == 0 and all(flag in r.stdout for flag in ("--template", "--out", "--posting"))


def test_prepare_reports_a_broken_template(tmp_path):
    (tmp_path / "BASE.tex").write_text("\\documentclass{resume}\n")
    (tmp_path / "resume.cls").write_text("% class")
    r = run_tool("prepare", "--template", str(tmp_path), "--out", str(tmp_path / "work"))
    assert r.returncode == 1 and "prepare failed" in r.stderr
