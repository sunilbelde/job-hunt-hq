import json
import shutil

from tests.letter_fixtures import (ANALYSIS, BASE_LETTER, JOB, LETTER, LETTER_SKILL_DIR, POSTING_MD, PROFILE_PATH,
                                   TEMPLATE_DIR, letter, prepare_letter, run_letter_tool, write_letter_out)

import letter_checks  # noqa: E402
import letter_tool  # noqa: E402


def built(work, data=LETTER, analysis=ANALYSIS):
    if analysis is not None:
        write_letter_out(work, "analysis.json", analysis)
    write_letter_out(work, "letter.json", data)
    return run_letter_tool("build", "--work", str(work))


# --- prepare and analyze ---

def test_prepare_tailored(tmp_path):
    work = prepare_letter(tmp_path / "w")
    assert (work / "posting.md").read_text() == POSTING_MD
    assert json.loads((work / "job.json").read_text()) == JOB
    assert {p.name for p in (work / "template").iterdir()} == {"BASE.tex", "resume.cls", "PROFILE.md"}
    base = json.loads((work / "out" / "base.json").read_text())
    assert base["jobs"][0]["facts"] and base["jobs"][0]["bullets"][0]["id"] == "j1.b1"


def test_prepare_base_mode(tmp_path):
    work = prepare_letter(tmp_path / "w", tailored=False)
    assert not (work / "posting.md").exists() and not (work / "job.json").exists()
    assert (work / "out" / "base.json").is_file()


def test_prepare_posting_needs_company_and_role(tmp_path):
    posting = tmp_path / "p.md"
    posting.write_text(POSTING_MD)
    r = run_letter_tool("prepare", "--template", str(TEMPLATE_DIR), "--out", str(tmp_path / "w"), "--posting", str(posting))
    assert r.returncode == 1 and "--company and --role" in r.stderr


def test_analyze(tmp_path):
    work = prepare_letter(tmp_path / "w")
    write_letter_out(work, "analysis.json", {"keywords": [], "requirements": []})
    r = run_letter_tool("analyze", "--work", str(work))
    assert r.returncode == 1 and "  fix  keywords" in r.stdout
    write_letter_out(work, "analysis.json", ANALYSIS)
    r = run_letter_tool("analyze", "--work", str(work))
    assert r.returncode == 0 and "(R1, R2, R3 required)" in r.stdout and "at least 2" in r.stdout


def test_analyze_base_mode(tmp_path):
    r = run_letter_tool("analyze", "--work", str(prepare_letter(tmp_path / "w", tailored=False)))
    assert r.returncode == 0 and "nothing to analyze" in r.stdout


# --- build and rendering ---

def test_build_tailored(tmp_path):
    work = prepare_letter(tmp_path / "w")
    r = built(work)
    assert r.returncode == 0, r.stdout
    assert "build 1: passed every hard check" in r.stdout and "1 page(s)" in r.stdout
    pdf = (work / "out" / "letter.pdf").read_bytes()
    text = (work / "out" / "letter.txt").read_text()
    assert letter_checks.pages(pdf) == 1
    assert text.startswith("Dear Acme Corp Hiring Team,\n\nI am applying for the Applied AI Engineer role")
    assert text.endswith("Sincerely,\nSunil Belde\n")
    # The PDF holds the same words as the text, after the header and the date.
    page = " ".join(letter_checks.pdf_text(pdf).split())
    for paragraph in text.split("\n\n"):
        assert " ".join(paragraph.split())[:60] in page
    assert page.startswith("SUNIL BELDE") and "sunil.belde102@gmail.com" in page


def test_build_base_mode_greets_the_hiring_manager(tmp_path):
    work = prepare_letter(tmp_path / "w", tailored=False)
    assert built(work, BASE_LETTER, analysis=None).returncode == 0
    assert (work / "out" / "letter.txt").read_text().startswith("Dear Hiring Manager,\n\n")


def test_build_refuses_without_analysis(tmp_path):
    work = prepare_letter(tmp_path / "w")
    write_letter_out(work, "letter.json", LETTER)
    r = run_letter_tool("build", "--work", str(work))
    assert r.returncode == 1 and "build refused" in r.stdout


def test_build_reports_fix_lines_and_counts(tmp_path):
    work = prepare_letter(tmp_path / "w")
    r = built(work, letter(p3={"text": LETTER["paragraphs"][3]["text"].replace("60%", "65%")}))
    assert r.returncode == 1 and "  fix  unsupported_number p4:" in r.stdout
    assert not (work / "out" / "letter.pdf").exists()
    assert json.loads((work / "out" / "check.json").read_text())["build"] == 1
    assert "build 2:" in built(work).stdout


def test_tex_specials_render_literally(tmp_path):
    tex = letter_checks.render_tex((TEMPLATE_DIR / "BASE.tex").read_text(), "Dear Hiring Manager,",
                                   ["Costs 5% & $3 for R&D_team #1 {braces} ~tilde ^caret."], "October 21, 2026")
    assert r"5\% \& \$3 for R\&D\_team \#1 \{braces\} \textasciitilde{}tilde \textasciicircum{}caret." in tex


def test_backslash_never_reaches_tex(tmp_path):
    work = prepare_letter(tmp_path / "w")
    r = built(work, letter(p4={"text": r"\input{/etc/passwd} " + LETTER["paragraphs"][4]["text"]}))
    assert r.returncode == 1 and "invalid_text" in r.stdout and "not rendered" in r.stdout
    assert not (work / "out" / "letter.pdf").exists()


def test_two_pages_rejected():
    # Five paragraphs at the length limit: too many words too, but the page check still runs and reports.
    text = ("I built agents and data pipelines that real teams depend on every day. " * 20)[:1190].strip()
    data = {"paragraphs": [{"role": "opening", "text": text},
                           *[{"role": "body", "text": text, "sources": ["j1.b1"]} for _ in range(3)],
                           {"role": "closing", "text": text}]}
    base = letter_tool.load_base(TEMPLATE_DIR, PROFILE_PATH)
    report, pdf, text_out = letter_tool.check_and_render(
        (TEMPLATE_DIR / "BASE.tex").read_text(), base, letter_checks.letter_from_json(data), [],
        TEMPLATE_DIR / "resume.cls")
    assert {"one_page", "word_count"} <= {item["code"] for item in report["failed"]}
    assert report["pages"] > 1 and pdf is None and text_out is None


# --- the gate ---

def gate_args(tmp_path, work, template=TEMPLATE_DIR):
    (tmp_path / "gate").mkdir(exist_ok=True)
    (tmp_path / "gate" / "posting.md").write_text(POSTING_MD)
    (tmp_path / "gate" / "job.json").write_text(json.dumps(JOB))
    return ["verify", "--template", str(template), "--work", str(work), "--profile", str(PROFILE_PATH),
            "--posting", str(tmp_path / "gate" / "posting.md"), "--job", str(tmp_path / "gate" / "job.json"),
            "--pdf-out", str(tmp_path / "gate" / "letter.pdf"), "--text-out", str(tmp_path / "gate" / "letter.txt")]


def test_verify_passes_and_writes(tmp_path):
    work = prepare_letter(tmp_path / "w")
    built(work)
    r = run_letter_tool(*gate_args(tmp_path, work))
    verdict = json.loads(r.stdout)
    assert r.returncode == 0 and verdict["ok"] and verdict["failed"] == [] and verdict["words"] > 250
    assert (tmp_path / "gate" / "letter.txt").read_text() == (work / "out" / "letter.txt").read_text()
    assert letter_checks.pages((tmp_path / "gate" / "letter.pdf").read_bytes()) == 1


def test_verify_ignores_the_runs_own_scripts_and_files(tmp_path):
    work = prepare_letter(tmp_path / "w")
    built(work)
    # The run rewrites its copy of the checks to pass everything, adds a fact, and swaps the posting.
    write_letter_out(work, "letter.json", letter(p3={"text": LETTER["paragraphs"][3]["text"].replace("60%", "65%")}))
    (work / "template" / "PROFILE.md").write_text("## Experience\n\n### Dockskiff\n- Cut effort by 65%.\n")
    (work / "posting.md").write_text("nothing")
    r = run_letter_tool(*gate_args(tmp_path, work))
    verdict = json.loads(r.stdout)
    assert r.returncode == 1 and verdict == {**verdict, "ok": False, "stage": "content", "failed": ["unsupported_number"]}
    assert not (tmp_path / "gate" / "letter.pdf").exists()


def test_verify_missing_output(tmp_path):
    work = prepare_letter(tmp_path / "w")
    write_letter_out(work, "analysis.json", ANALYSIS)
    verdict = json.loads(run_letter_tool(*gate_args(tmp_path, work)).stdout)
    assert (verdict["stage"], verdict["failed"]) == ("output", ["missing_output"])


def test_verify_bad_analysis(tmp_path):
    work = prepare_letter(tmp_path / "w")
    built(work, analysis={"keywords": []})
    verdict = json.loads(run_letter_tool(*gate_args(tmp_path, work)).stdout)
    assert (verdict["stage"], verdict["failed"]) == ("analysis", ["analysis_invalid"])


def test_verify_never_prints_letter_text(tmp_path):
    work = prepare_letter(tmp_path / "w")
    built(work)
    out = run_letter_tool(*gate_args(tmp_path, work)).stdout
    assert "Capital One" not in out and "Acme" not in out


# --- the base letter ---

def data_copy(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("BASE.tex", "resume.cls", "PROFILE.md"):
        shutil.copyfile(TEMPLATE_DIR / name, data / name)
    return data


def test_publish_base_writes_both_files(tmp_path):
    data, work = data_copy(tmp_path), prepare_letter(tmp_path / "w", tailored=False)
    built(work, BASE_LETTER, analysis=None)
    r = run_letter_tool("publish-base", "--work", str(work), "--data", str(data))
    assert r.returncode == 0, r.stdout + r.stderr
    md = (data / "COVER_LETTER.md").read_text()
    assert md.startswith("Dear Hiring Manager,\n\n") and md.endswith("Sincerely,\nSunil Belde\n")
    page = " ".join(letter_checks.pdf_text((data / "COVER_LETTER.pdf").read_bytes()).split())
    assert BASE_LETTER["paragraphs"][0]["text"][:50] in page


def test_publish_base_rejects_an_invented_number(tmp_path):
    data, work = data_copy(tmp_path), prepare_letter(tmp_path / "w", tailored=False)
    bad = {"paragraphs": [dict(p) for p in BASE_LETTER["paragraphs"]]}
    bad["paragraphs"][3]["text"] = bad["paragraphs"][3]["text"].replace("60%", "65%")
    write_letter_out(work, "letter.json", bad)
    r = run_letter_tool("publish-base", "--work", str(work), "--data", str(data))
    assert r.returncode == 1 and "unsupported_number" in r.stdout and "nothing written" in r.stdout
    assert not (data / "COVER_LETTER.md").exists() and not (data / "COVER_LETTER.pdf").exists()


def test_publish_base_refuses_a_tailored_folder(tmp_path):
    data, work = data_copy(tmp_path), prepare_letter(tmp_path / "w")
    built(work)
    r = run_letter_tool("publish-base", "--work", str(work), "--data", str(data))
    assert r.returncode == 1 and "base-mode" in r.stderr


def test_render_base_after_an_edit(tmp_path):
    data, work = data_copy(tmp_path), prepare_letter(tmp_path / "w", tailored=False)
    built(work, BASE_LETTER, analysis=None)
    run_letter_tool("publish-base", "--work", str(work), "--data", str(data))
    md = data / "COVER_LETTER.md"
    # The owner rewrites a paragraph, wrapping it over two lines, with a number no source states.
    md.write_text(md.read_text().replace(BASE_LETTER["paragraphs"][4]["text"],
                                         "I edited this closing myself, and it mentions 12 projects\nacross two lines."))
    r = run_letter_tool("render-base", "--data", str(data))
    assert r.returncode == 0, r.stderr
    page = " ".join(letter_checks.pdf_text((data / "COVER_LETTER.pdf").read_bytes()).split())
    assert "I edited this closing myself, and it mentions 12 projects across two lines." in page
    assert page.count("Sincerely,") == 1


def test_render_base_rejects_tex(tmp_path):
    data = data_copy(tmp_path)
    (data / "COVER_LETTER.md").write_text("Dear Hiring Manager,\n\nA \\input{x} paragraph.\n")
    r = run_letter_tool("render-base", "--data", str(data))
    assert r.returncode == 1 and "backslash" in r.stderr and not (data / "COVER_LETTER.pdf").exists()


def test_parse_base_letter():
    greeting, paragraphs = letter_tool.parse_base_letter("Dear X,\n\nOne\ntwo.\n\n\nThree.\n\nSincerely,\nSunil Belde\n")
    assert (greeting, paragraphs) == ("Dear X,", ["One two.", "Three."])


def test_skill_folder_layout():
    assert (LETTER_SKILL_DIR / "scripts" / "letter_tool.py").is_file()
    assert (LETTER_SKILL_DIR / "scripts" / "letter_checks.py").is_file()
