"""Command line of the write-cover-letter skill. Run it through the `run` launcher next to this file.

    run prepare --template <dir> --out <work folder> [--profile <file>] [--posting <file> --company <c> --role <r>]
    run analyze [--work <work folder>]
    run build [--work <work folder>]
    run verify --template <dir> --work <work folder> --profile <file> --posting <file> --job <file>
               [--analysis <file>] --pdf-out <file> --text-out <file>
    run publish-base [--work <work folder>] --data <dir>
    run render-base --data <dir>

A work folder with a posting.md is in tailored mode: the letter is for that posting. Without one it is in
base mode: the owner's generic letter. Subcommands that read a work folder default to the current
directory. `verify` is the service's gate and runs from the repo's own copy of this script, never inside
a Claude run; `publish-base` and `render-base` write to the repo's data folder, so only the owner runs them.

The scripts reuse the tailor-resume skill's modules (resume model, checks, scoring), found beside this
skill's folder.
"""
import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tailor-resume" / "scripts"))

import letter_checks  # noqa: E402
import resume_checks  # noqa: E402
import resume_model  # noqa: E402
import resume_score  # noqa: E402
import resume_terms  # noqa: E402
from resume_tool import PROFILE, TEMPLATE_FILES, ToolError, load_base, read_json, read_profile, write_json  # noqa: E402

PROFILE_INVALID_EXIT = 4  # as resume_tool: the profile names an employer the resume lacks
BASE_LETTER_MD = "COVER_LETTER.md"
BASE_LETTER_PDF = "COVER_LETTER.pdf"


def today() -> str:
    d = datetime.date.today()
    return f"{d:%B} {d.day}, {d.year}"


class Work:
    """The files of a work folder."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.template = folder / "template"
        self.out = folder / "out"
        self.posting = folder / "posting.md"
        self.job = folder / "job.json"

    @property
    def tailored(self) -> bool:
        return self.posting.is_file()

    def base(self) -> resume_model.BaseResume:
        return load_base(self.template, self.template / PROFILE)

    def profile_skills(self) -> list[str]:
        return read_profile(self.template / PROFILE)


def load_analysis(path: Path) -> dict:
    analysis = read_json(path)
    resume_score.validate_analysis(analysis, assessment=False)
    return analysis


def load_letter(path: Path) -> letter_checks.Letter:
    return letter_checks.letter_from_json(read_json(path))


def check_and_render(base_tex: str, base, letter, skills, cls: Path, job=None, analysis=None,
                     posting=None, date: str | None = None) -> tuple[dict, bytes | None, str | None]:
    """Every check on the letter, compiling it unless a hard text check failed. Returns the report, the
    PDF and the plain text, the last two only when every hard check passes."""
    failed, warnings = letter_checks.check_letter(base, letter, skills, job, analysis, posting)
    pages = None
    pdf = text = None
    if not any(item["code"] == "invalid_text" for item in failed):
        greeting = job.greeting() if job else letter_checks.GENERIC_GREETING
        paragraphs = [p.text for p in letter.paragraphs]
        try:
            compiled = resume_checks.compile_tex(letter_checks.render_tex(base_tex, greeting, paragraphs,
                                                                          date or today()), cls)
        except resume_checks.CompileError as exc:
            failed.append({"code": "compile_failed", "detail": str(exc)[:300]})
        else:
            pages = letter_checks.pages(compiled.pdf)
            if pages != 1:
                failed.append({"code": "one_page", "detail": f"{pages} pages; shorten the paragraphs to fit one"})
            pdf, text = compiled.pdf, letter_checks.plain_text(base_tex, greeting, paragraphs)
    report = {"passed": not failed, "failed": failed, "warnings": warnings, "words": letter.words(), "pages": pages}
    return report, (pdf if not failed else None), (text if not failed else None)


def format_report(report: dict) -> str:
    def line(item):
        return f"{item['code']} {item['where']}: {item['detail']}" if item.get("where") else f"{item['code']}: {item['detail']}"

    out = [f"build {report['build']}: " + ("passed every hard check" if report["passed"]
                                           else f"FAILED, {len(report['failed'])} to fix")]
    out += [f"  fix  {line(item)}" for item in report["failed"]]
    lo, hi = letter_checks.WORDS_RANGE
    out.append(f"letter: {report['words']} words (range {lo} to {hi}), "
               + (f"{report['pages']} page(s)" if report["pages"] else "not rendered"))
    out += [f"  aim  {line(item)}" for item in report["warnings"]]
    return "\n".join(out)


# --- commands ---

def cmd_prepare(args) -> int:
    template, work = Path(args.template), Work(Path(args.out))
    profile = Path(args.profile) if args.profile else None
    if args.posting and not (args.company and args.role):
        raise ToolError("a posting needs --company and --role")
    base = load_base(template, profile)
    work.template.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_FILES:
        shutil.copyfile(template / name, work.template / name)
    if profile is not None and profile.is_file():
        shutil.copyfile(profile, work.template / PROFILE)
    if args.posting:
        shutil.copyfile(args.posting, work.posting)
        write_json(work.job, {"company": args.company, "role": args.role})
    write_json(work.out / "base.json", base.to_json())
    facts = sum(len(job.facts) for job in base.jobs)
    mode = f"tailored to {args.role} at {args.company}" if args.posting else "base letter, no posting"
    print(f"prepared {work.folder} ({mode}): {len(base.jobs)} jobs, {facts} profile facts -> out/base.json")
    return 0


def cmd_analyze(args) -> int:
    work = Work(Path(args.work))
    if not work.tailored:
        print("analyze: base mode has no posting; there is nothing to analyze. Go on to the letter.")
        return 0
    try:
        analysis = load_analysis(work.out / "analysis.json")
    except resume_score.AnalysisError as exc:
        print(f"analysis FAILED, {len(exc.problems)} to fix")
        print("\n".join(f"  fix  {problem}" for problem in exc.problems))
        return 1
    required = [r["id"] for r in analysis["requirements"] if r["importance"] == "required"]
    needed = min(letter_checks.MIN_REQUIRED_ADDRESSED, len(required))
    print(f"analysis ok: {len(analysis['keywords'])} keywords, {len(analysis['requirements'])} requirements "
          f"({', '.join(required) or 'none'} required). The body paragraphs must address at least {needed} "
          "required requirements.")
    return 0


def cmd_build(args) -> int:
    work = Work(Path(args.work))
    base = work.base()
    job = analysis = posting = None
    if work.tailored:
        job = letter_checks.Job.from_json(read_json(work.job))
        try:
            analysis = load_analysis(work.out / "analysis.json")
        except (ToolError, resume_score.AnalysisError):
            print("build refused: out/analysis.json is missing or not valid yet; run `analyze` and fix it first")
            return 1
        posting = work.posting.read_text(encoding="utf-8")
    counter = work.out / "build" / "count"
    number = int(counter.read_text()) + 1 if counter.is_file() else 1
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(number))
    try:
        letter = load_letter(work.out / "letter.json")
    except resume_model.ContentError as exc:
        report = {"passed": False, "failed": [{"code": exc.code, "detail": exc.detail}], "warnings": [],
                  "words": 0, "pages": None}
    else:
        base_tex = (work.template / "BASE.tex").read_text(encoding="utf-8")
        report, pdf, text = check_and_render(base_tex, base, letter, work.profile_skills(),
                                             work.template / "resume.cls", job, analysis, posting)
        if pdf is not None:
            (work.out / "letter.pdf").write_bytes(pdf)
            (work.out / "letter.txt").write_text(text, encoding="utf-8")
    report["build"] = number
    write_json(work.out / "check.json", report)
    print(format_report(report))
    return 0 if report["passed"] else 1


def cmd_verify(args) -> int:
    """The service's final gate, run from the repo's own copy of this script.

    It reads only out/letter.json (and, without --analysis, out/analysis.json) from --work, and builds
    everything else from the service's own --template, --profile, --posting and --job, so nothing a run
    changed in its folder can reach the saved letter. It prints one JSON object with check codes, never
    file contents, and writes the PDF and the text only when every check passes.
    """
    template, work = Path(args.template), Work(Path(args.work))
    result = {"ok": False, "stage": None, "failed": [], "warnings": [], "words": None}

    def finish(stage: str | None = None, failed: list[str] | None = None) -> int:
        if stage:
            result.update(stage=stage, failed=failed or [])
        print(json.dumps(result))
        return 0 if result["ok"] else 1

    try:
        base_tex = (template / "BASE.tex").read_text(encoding="utf-8")
        base = load_base(template, Path(args.profile))
        job = letter_checks.Job.from_json(read_json(Path(args.job)))
        posting = Path(args.posting).read_text(encoding="utf-8")
    except (OSError, ToolError, resume_model.ModelError, resume_model.ContentError):
        return finish("template", ["template_invalid"])
    except resume_terms.ProfileError:
        return finish("template", ["profile_invalid"])
    try:
        analysis = load_analysis(Path(args.analysis) if args.analysis else work.out / "analysis.json")
    except (ToolError, resume_score.AnalysisError):
        return finish("analysis", ["analysis_invalid"])
    try:
        letter = load_letter(work.out / "letter.json")
    except ToolError:
        return finish("output", ["missing_output"])
    except resume_model.ContentError as exc:
        return finish("content", [exc.code])
    report, pdf, text = check_and_render(base_tex, base, letter, read_profile(Path(args.profile)),
                                         template / "resume.cls", job, analysis, posting)
    result.update(words=report["words"], warnings=sorted({item["code"] for item in report["warnings"]}))
    if not report["passed"]:
        codes = sorted({item["code"] for item in report["failed"]})
        return finish("render" if "compile_failed" in codes else "content", codes)
    Path(args.pdf_out).write_bytes(pdf)
    Path(args.text_out).write_text(text, encoding="utf-8")
    result["ok"] = True
    return finish()


def cmd_publish_base(args) -> int:
    """Check the base-mode letter against the repo's own data folder and write the owner's two files."""
    work, data = Work(Path(args.work)), Path(args.data)
    if work.tailored:
        raise ToolError("publish-base takes a base-mode work folder (one without posting.md)")
    base_tex = (data / "BASE.tex").read_text(encoding="utf-8")
    base = load_base(data, data / "PROFILE.md")
    letter = load_letter(work.out / "letter.json")
    report, pdf, text = check_and_render(base_tex, base, letter, read_profile(data / "PROFILE.md"), data / "resume.cls")
    if not report["passed"]:
        report["build"] = "publish-base"
        print(format_report(report))
        print("nothing written: fix the letter and build again")
        return 1
    (data / BASE_LETTER_MD).write_text(text, encoding="utf-8")
    (data / BASE_LETTER_PDF).write_bytes(pdf)
    print(f"wrote {data / BASE_LETTER_MD} and {data / BASE_LETTER_PDF} ({report['words']} words). Review and edit the "
          f"text, then run `render-base --data {data}`.")
    return 0


def parse_base_letter(text: str) -> tuple[str, list[str]]:
    """The greeting and paragraphs of COVER_LETTER.md: blocks split by blank lines, lines joined, and the
    sign-off block (the scripts write it) left out."""
    blocks = [" ".join(line.strip() for line in block.splitlines() if line.strip())
              for block in text.replace("\r\n", "\n").split("\n\n")]
    blocks = [b for b in blocks if b]
    if blocks and blocks[-1].startswith(letter_checks.SIGN_OFF):
        blocks.pop()
    if len(blocks) < 2:
        raise ToolError(f"{BASE_LETTER_MD} needs a greeting and at least one paragraph, separated by blank lines")
    return blocks[0], blocks[1:]


def cmd_render_base(args) -> int:
    """Re-render COVER_LETTER.pdf from the owner's edited COVER_LETTER.md. The owner's words are trusted, like
    PROFILE.md, so only TeX safety and the one page are checked."""
    data = Path(args.data)
    greeting, paragraphs = parse_base_letter((data / BASE_LETTER_MD).read_text(encoding="utf-8"))
    for n, text in enumerate([greeting, *paragraphs], 1):
        if letter_checks._control(text) or "\\" in text:
            raise ToolError(f"block {n} of {BASE_LETTER_MD} has a backslash or a control character")
    base_tex = (data / "BASE.tex").read_text(encoding="utf-8")
    try:
        compiled = resume_checks.compile_tex(letter_checks.render_tex(base_tex, greeting, paragraphs, today()),
                                             data / "resume.cls")
    except resume_checks.CompileError as exc:
        raise ToolError(f"render failed: {str(exc)[:300]}") from None
    pages = letter_checks.pages(compiled.pdf)
    if pages != 1:
        raise ToolError(f"the letter runs to {pages} pages; shorten it to one")
    (data / BASE_LETTER_PDF).write_bytes(compiled.pdf)
    print(f"wrote {data / BASE_LETTER_PDF}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run", description="Scripts of the write-cover-letter skill.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="make a work folder: template copy, out/base.json, and the posting")
    prepare.add_argument("--template", required=True, help="folder holding BASE.tex and resume.cls")
    prepare.add_argument("--out", required=True, help="work folder to create or refresh")
    prepare.add_argument("--profile", help="the owner's profile (data/PROFILE.md) to copy to template/; may be missing")
    prepare.add_argument("--posting", help="posting text to copy to posting.md; without it the folder is in base mode")
    prepare.add_argument("--company", help="with --posting: the company as recorded")
    prepare.add_argument("--role", help="with --posting: the role as recorded")
    prepare.set_defaults(func=cmd_prepare)

    analyze = sub.add_parser("analyze", help="check out/analysis.json: the posting's keywords and requirements")
    analyze.add_argument("--work", default=".", help="work folder (default: current directory)")
    analyze.set_defaults(func=cmd_analyze)

    build = sub.add_parser("build", help="check out/letter.json, render it and write out/letter.pdf and out/letter.txt")
    build.add_argument("--work", default=".", help="work folder (default: current directory)")
    build.set_defaults(func=cmd_build)

    verify = sub.add_parser("verify", help="the service's gate: recheck a finished run and write the letter to save")
    verify.add_argument("--template", required=True, help="the service's own folder holding BASE.tex and resume.cls")
    verify.add_argument("--work", required=True, help="the run's work folder; only its out/*.json files are read")
    verify.add_argument("--profile", required=True, help="the service's own profile (data/PROFILE.md); may be missing")
    verify.add_argument("--posting", required=True, help="the service's own posting.md")
    verify.add_argument("--job", required=True, help="the service's own job.json with the company and role")
    verify.add_argument("--analysis", help="the service's copy of the run's analysis (default: the work folder's)")
    verify.add_argument("--pdf-out", required=True, help="where to write the PDF when every check passes")
    verify.add_argument("--text-out", required=True, help="where to write the plain text when every check passes")
    verify.set_defaults(func=cmd_verify)

    publish = sub.add_parser("publish-base", help="owner only: check a base-mode letter and write data/COVER_LETTER.md and .pdf")
    publish.add_argument("--work", default=".", help="base-mode work folder (default: current directory)")
    publish.add_argument("--data", required=True, help="the repo's data folder")
    publish.set_defaults(func=cmd_publish_base)

    render_base = sub.add_parser("render-base", help="owner only: re-render data/COVER_LETTER.pdf from the edited .md")
    render_base.add_argument("--data", required=True, help="the repo's data folder")
    render_base.set_defaults(func=cmd_render_base)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except resume_terms.ProfileError as exc:
        print(f"{args.command} failed: profile_invalid: {exc}", file=sys.stderr)
        return PROFILE_INVALID_EXIT
    except (ToolError, OSError, resume_model.ModelError, resume_model.ContentError, resume_score.AnalysisError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
