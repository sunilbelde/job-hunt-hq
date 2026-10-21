"""Command line of the tailor-resume skill. Run it through the `run` launcher next to this file.

    run prepare --template <dir> --out <work folder> [--posting <file>] [--profile <file>]
    run score base|tailored [--work <work folder>]
    run terms [--work <work folder>]
    run build [--work <work folder>]
    run judge-input --template <dir> --profile <file> --work <work folder> --out <dir>
    run judge-result --template <dir> --profile <file> --analysis <file> [--verdicts <file>] --out <file>
    run verify --template <dir> --work <work folder> [--profile <file>] [--analysis <file>] [--terms <file>]
               --pdf-out <file>

Subcommands that read a work folder default to the current directory. `judge-input`, `judge-result` and
`verify` are the service's: they run from the repo's copy of this script, never inside a Claude run.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import resume_checks
import resume_model
import resume_score
import resume_terms

TEMPLATE_FILES = ("BASE.tex", "resume.cls")
TERMS = Path("judge") / "terms.json"  # in the work folder: the judge's ruling, written by the service
COVERAGE = Path("out") / "coverage.json"  # in the work folder: the run's plan for the weak requirements
PROFILE = "PROFILE.md"  # in the work folder's template/: prepare's copy of the owner's profile
PROFILE_INVALID_EXIT = 4  # prepare's exit code when the profile names an employer the resume lacks
JUDGE_PENDING = ("The judge has not ruled yet on the posting keywords the base resume lacks ({path} is missing). "
                 "Stop here and reply with one line: waiting for the judge. In the service it runs next and "
                 "this skill starts again; in an interactive session, the owner runs "
                 "`.venv/bin/python -m app.tailoring --judge <work folder>` first.")


class ToolError(Exception):
    """A missing or unreadable input file."""


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError(f"{path.name} is missing: write it first") from None
    except json.JSONDecodeError as exc:
        raise ToolError(f"{path.name} is not valid JSON: {exc}") from None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_base(template: Path, profile: Path | None = None) -> resume_model.BaseResume:
    """The base resume, each job carrying the facts `profile` lists for it (none without a profile)."""
    base = resume_model.parse_base((template / "BASE.tex").read_text(encoding="utf-8"))
    return resume_terms.attach_facts(base, resume_terms.parse_profile(_profile_text(profile)))


def load_work_base(work: Path) -> resume_model.BaseResume:
    return load_base(work / "template", work / "template" / PROFILE)


def load_analysis(work: Path, path: Path | None = None) -> dict:
    analysis = read_json(path or work / "out" / "analysis.json")
    resume_score.validate_analysis(analysis)
    return analysis


def load_terms(path: Path) -> resume_terms.Terms | None:
    """The judge's ruling, or None when the judge has not ruled."""
    if not path.is_file():
        return None
    try:
        return resume_terms.Terms.from_json(read_json(path))
    except (KeyError, TypeError) as exc:
        raise ToolError(f"{path.name} is not a ruling written by judge-result: {exc}") from None


def _profile_text(path: Path | None) -> str | None:
    return path.read_text(encoding="utf-8") if path is not None and path.is_file() else None


def read_profile(path: Path | None) -> list[str]:
    """The owner's profile skills. A missing file is an empty list: the judge then has only the resume."""
    return resume_terms.profile_entries(_profile_text(path))


def cmd_prepare(args) -> int:
    template, work = Path(args.template), Path(args.out)
    profile = Path(args.profile) if args.profile else None
    base = load_base(template, profile)
    (work / "template").mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_FILES:
        shutil.copyfile(template / name, work / "template" / name)
    if profile is not None and profile.is_file():
        shutil.copyfile(profile, work / "template" / PROFILE)
    if args.posting:
        shutil.copyfile(args.posting, work / "posting.md")
    write_json(work / "out" / "base.json", base.to_json())
    bullets = sum(len(job.bullets) for job in base.jobs)
    facts = sum(len(job.facts) for job in base.jobs)
    print(f"prepared {work}: {len(base.jobs)} jobs, {bullets} bullets, {facts} profile facts, "
          f"{len(base.skills)} skills lines -> out/base.json")
    return 0


def cmd_score(args) -> int:
    work = Path(args.work)
    base = load_work_base(work)
    analysis = load_analysis(work)
    if args.which == "base":
        assessment, content = analysis["assessment"], base.content()
    else:
        content = resume_model.content_from_json(read_json(work / "out" / "tailored.json"))
        assessment = read_json(work / "out" / "assessment_tailored.json")
        resume_score.validate_assessment(assessment, analysis["requirements"])
    result = resume_score.score(analysis["keywords"], analysis["requirements"], assessment,
                                resume_model.resume_text(base, content))
    write_json(work / "out" / f"score_{args.which}.json", result.to_json())
    print(result.summary(args.which))
    if args.which == "tailored" and (work / COVERAGE).is_file():
        for line in resume_checks.planned_not_met(read_json(work / COVERAGE), assessment):
            print(line)
    if args.which == "base":
        threshold = resume_score.THRESHOLD
        print(f"decision: {threshold} or more, keep the base resume and stop" if result.decision == "keep"
              else f"decision: below {threshold}, tailor the resume")
    return 0


def build_report(base, content, keywords: list[dict], cls: Path, build_dir: Path | None = None,
                 terms: resume_terms.Terms | None = None, posting: str | None = None) -> tuple[dict, bytes | None]:
    """Every check on `content`, compiling it unless it cannot be rendered. Returns the report and the PDF.
    `posting` enables the soft echoed phrase check; the gate leaves it out."""
    failed, warnings = resume_checks.check_content(base, content, keywords, terms, posting)
    layout, pdf = None, None
    if not any(item["code"] in resume_checks.UNRENDERABLE for item in failed):
        rendered = resume_model.render(base, content)
        try:
            compiled = resume_checks.compile_tex(rendered.tex, cls)
        except resume_checks.CompileError as exc:
            failed.append({"code": "compile_failed", "detail": str(exc)[:300]})
        else:
            refs = [ref for _, ref in sorted(rendered.line_map.items()) if "#" in ref]
            measured = resume_checks.measure(compiled, rendered.line_map, refs)
            failed += _annotate(measured.hard_failures(), content)
            warnings += _annotate(measured.soft_findings(), content)
            layout, pdf = measured.to_json(), compiled.pdf
            if build_dir is not None:
                build_dir.mkdir(parents=True, exist_ok=True)
                (build_dir / "tailored.tex").write_text(rendered.tex, encoding="utf-8")
                (build_dir / "tailored.pdf").write_bytes(compiled.pdf)
                (build_dir / "tailored.log").write_text(compiled.log, encoding="utf-8")
    return {"passed": not failed, "failed": failed, "warnings": warnings, "layout": layout}, pdf


def _annotate(findings: list[dict], content) -> list[dict]:
    """Name the base bullets behind a page position, e.g. "j4#1 (from j4.b1)"."""
    sources = {f"{job.id}#{n}": bullet.sources for job in content.jobs for n, bullet in enumerate(job.bullets, 1)}
    for item in findings:
        ref = item.get("where")
        if sources.get(ref):
            item["where"] = f"{ref} (from {', '.join(sources[ref])})"
    return findings


def format_report(report: dict) -> str:
    def line(item):
        return f"{item['code']} {item['where']}: {item['detail']}" if item.get("where") else f"{item['code']}: {item['detail']}"

    out = [f"build {report['build']}: " + ("passed every hard check" if report["passed"]
                                           else f"FAILED, {len(report['failed'])} to fix")]
    out += [f"  fix  {line(item)}" for item in report["failed"]]
    layout = report["layout"]
    if layout:
        out.append(f"layout: {layout['pages']} page(s), fill {layout['fill']:.1%} "
                   f"(target {resume_checks.FILL_TARGET:.0%}), about {layout['lines_free']} lines free")
    out += [f"  aim  {line(item)}" for item in report["warnings"]]
    if report["passed"] and not any(w["code"] in ("fill_target", "short_last_line") for w in report["warnings"]):
        out.append("layout targets met")
    return "\n".join(out)


def cmd_terms(args) -> int:
    work = Path(args.work)
    terms = load_terms(work / TERMS)
    print(JUDGE_PENDING.format(path=TERMS) if terms is None else resume_terms.format_terms(terms))
    return 0


def cmd_build(args) -> int:
    work = Path(args.work)
    terms = load_terms(work / TERMS)
    if terms is None:
        print("build refused. " + JUDGE_PENDING.format(path=TERMS))
        return 1
    base = load_work_base(work)
    analysis = load_analysis(work)
    counter = work / "out" / "build" / "count"
    number = int(counter.read_text()) + 1 if counter.is_file() else 1
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(number))
    try:
        content = resume_model.content_from_json(read_json(work / "out" / "tailored.json"))
    except resume_model.ContentError as exc:
        report = {"passed": False, "failed": [{"code": exc.code, "detail": exc.detail}], "warnings": [], "layout": None}
    else:
        posting = work / "posting.md"
        report, _ = build_report(base, content, analysis["keywords"], work / "template" / "resume.cls",
                                 work / "out" / "build", terms,
                                 posting.read_text(encoding="utf-8") if posting.is_file() else None)
        plan = read_json(work / COVERAGE) if (work / COVERAGE).is_file() else None
        report["failed"] += resume_checks.check_coverage(plan, analysis, base)
        report["passed"] = not report["failed"]
    report["build"] = number
    write_json(work / "out" / "check.json", report)
    print(format_report(report))
    return 0 if report["passed"] else 1


def _print_json(data: dict, ok: bool) -> int:
    print(json.dumps(data))
    return 0 if ok else 1


def cmd_judge_input(args) -> int:
    """The service's step between the analysis run and the judge, from the repo's copy of this script.

    It validates the run's analysis and keeps a copy in --out (the gate scores against that copy, so a
    later run cannot change the posting's keywords), decides keep or tailor, and when tailoring, writes
    the judge's input for the keywords the base resume lacks to --out/judge-input.md. It prints one JSON
    object with the decision, the base score, its breakdown and the number of keywords to judge.
    """
    base = load_base(Path(args.template), Path(args.profile))
    out = Path(args.out)
    try:
        analysis = load_analysis(Path(args.work))
    except (ToolError, resume_score.AnalysisError):
        return _print_json({"ok": False, "failed": ["analysis_invalid"]}, False)
    write_json(out / "analysis.json", analysis)
    requirements, assessment = analysis["requirements"], analysis["assessment"]
    score = resume_score.score(analysis["keywords"], requirements, assessment,
                               resume_model.resume_text(base, base.content()))
    keywords = resume_terms.candidates(base, analysis["keywords"]) if score.decision == "tailor" else []
    if keywords:
        (out / "judge-input.md").write_text(resume_terms.judge_input(base, read_profile(Path(args.profile)), keywords),
                                            encoding="utf-8")
    return _print_json({"ok": True, "decision": score.decision, "base_score": score.score,
                        "base": resume_score.breakdown(score, requirements, assessment),
                        "candidates": len(keywords)}, True)


def cmd_judge_result(args) -> int:
    """Check the judge's verdicts and write the ruling the tailoring run and the gate use.

    Keywords a profile fact states are approved for the bullets citing those facts, without the judge.
    Without --verdicts (the judge did not run, as when there is nothing to judge), every other keyword the
    base resume lacks is rejected. Prints {"ok", "approved", "rejected"}; a verdicts file that is missing or not
    a verdicts object fails with "judge_invalid".
    """
    base = load_base(Path(args.template), Path(args.profile))
    analysis = load_analysis(None, Path(args.analysis))
    keywords = resume_terms.candidates(base, analysis["keywords"])
    try:
        verdicts = read_json(Path(args.verdicts)) if args.verdicts else {"verdicts": []}
        terms = resume_terms.rule(verdicts, keywords, base, read_profile(Path(args.profile)))
    except (ToolError, resume_terms.VerdictError):
        return _print_json({"ok": False, "failed": ["judge_invalid"]}, False)
    terms.approved = resume_terms.from_facts(base, analysis["keywords"]) + terms.approved
    write_json(Path(args.out), terms.to_json())
    return _print_json({"ok": True, "approved": len(terms.approved), "rejected": len(terms.rejected)}, True)


def cmd_verify(args) -> int:
    """The service's final gate, run from the repo's own copy of this script.

    It reads only the run's JSON files from --work and builds everything else from --template and
    --profile, so nothing a run changed in its folder can reach the saved resume: a fact the run adds to
    its out/base.json is not a source here. --analysis and --terms name the service's own copies of the
    analysis and the judge's ruling; without --terms no posting keyword the base resume lacks is allowed. It prints one JSON object with scores and their breakdowns, check codes,
    the approved keywords used and the rejected ones, never file contents, and writes the PDF only when
    every check passes.
    """
    template, work = Path(args.template), Path(args.work)
    result = {"ok": False, "decision": None, "base_score": None, "tailored_score": None, "failed": [], "warnings": [],
              "added_terms": [], "base": None, "tailored": None, "rejected_terms": []}

    def finish(stage: str | None = None, failed: list[str] | None = None) -> int:
        if stage:
            result.update(stage=stage, failed=failed or [])
        print(json.dumps(result))
        return 0 if result["ok"] else 1

    try:
        base = load_base(template, Path(args.profile) if args.profile else None)
    except (OSError, resume_model.ModelError):
        return finish("template", ["template_invalid"])
    except resume_terms.ProfileError:
        return finish("template", ["profile_invalid"])
    try:
        analysis = load_analysis(work, Path(args.analysis) if args.analysis else None)
        terms = load_terms(Path(args.terms)) if args.terms else None
    except (ToolError, resume_score.AnalysisError):
        return finish("analysis", ["analysis_invalid"])
    keywords, requirements = analysis["keywords"], analysis["requirements"]
    base_score = resume_score.score(keywords, requirements, analysis["assessment"],
                                    resume_model.resume_text(base, base.content()))
    result.update(decision=base_score.decision, base_score=base_score.score,
                  base=resume_score.breakdown(base_score, requirements, analysis["assessment"]))
    if base_score.decision == "keep":
        result["ok"] = True
        return finish()

    try:
        content = resume_model.content_from_json(read_json(work / "out" / "tailored.json"))
        assessment = read_json(work / "out" / "assessment_tailored.json")
        resume_score.validate_assessment(assessment, requirements)
    except (ToolError, resume_score.AnalysisError):
        return finish("output", ["missing_output"])
    except resume_model.ContentError as exc:
        return finish("content", [exc.code])
    report, pdf = build_report(base, content, keywords, template / "resume.cls", terms=terms)
    result["warnings"] = sorted({item["code"] for item in report["warnings"]})
    if not report["passed"]:
        codes = sorted({item["code"] for item in report["failed"]})
        return finish("render" if "compile_failed" in codes else "content", codes)
    tailored_score = resume_score.score(keywords, requirements, assessment, resume_model.resume_text(base, content))
    result.update(ok=True, tailored_score=tailored_score.score,
                  tailored=resume_score.breakdown(tailored_score, requirements, assessment),
                  added_terms=resume_checks.added_keywords(base, content, terms) if terms else [],
                  rejected_terms=[dict(r) for r in terms.rejected] if terms else [])
    Path(args.pdf_out).write_bytes(pdf)
    return finish()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run", description="Scripts of the tailor-resume skill.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="make a work folder: template copy and out/base.json")
    prepare.add_argument("--template", required=True, help="folder holding BASE.tex and resume.cls")
    prepare.add_argument("--out", required=True, help="work folder to create or refresh")
    prepare.add_argument("--posting", help="posting text to copy to <work folder>/posting.md")
    prepare.add_argument("--profile", help="the owner's profile (data/PROFILE.md) to copy to template/; may be missing")
    prepare.set_defaults(func=cmd_prepare)

    score = sub.add_parser("score", help="score the base or the tailored resume against out/analysis.json")
    score.add_argument("which", choices=("base", "tailored"))
    score.add_argument("--work", default=".", help="work folder (default: current directory)")
    score.set_defaults(func=cmd_score)

    terms = sub.add_parser("terms", help="list the posting keywords the judge approved, and where each may go")
    terms.add_argument("--work", default=".", help="work folder (default: current directory)")
    terms.set_defaults(func=cmd_terms)

    build = sub.add_parser("build", help="check out/tailored.json, render and compile it, and measure the page")
    build.add_argument("--work", default=".", help="work folder (default: current directory)")
    build.set_defaults(func=cmd_build)

    judge_in = sub.add_parser("judge-input", help="the service's step after the analysis run: decide, and write the judge's input")
    judge_in.add_argument("--template", required=True, help="the service's own folder holding BASE.tex and resume.cls")
    judge_in.add_argument("--profile", required=True, help="the owner's profile list (data/PROFILE.md); may be missing")
    judge_in.add_argument("--work", required=True, help="the run's work folder; only out/analysis.json is read")
    judge_in.add_argument("--out", required=True, help="service folder for the analysis copy and judge-input.md")
    judge_in.set_defaults(func=cmd_judge_input)

    judge_out = sub.add_parser("judge-result", help="check the judge's verdicts and write the ruling")
    judge_out.add_argument("--template", required=True, help="the service's own folder holding BASE.tex and resume.cls")
    judge_out.add_argument("--profile", required=True, help="the owner's profile list (data/PROFILE.md); may be missing")
    judge_out.add_argument("--analysis", required=True, help="the analysis copy judge-input wrote")
    judge_out.add_argument("--verdicts", help="the judge's out/verdicts.json; without it nothing is approved")
    judge_out.add_argument("--out", required=True, help="where to write the ruling (terms.json)")
    judge_out.set_defaults(func=cmd_judge_result)

    verify = sub.add_parser("verify", help="the service's gate: recheck a finished run and write the PDF to save")
    verify.add_argument("--template", required=True, help="the service's own folder holding BASE.tex and resume.cls")
    verify.add_argument("--work", required=True, help="the run's work folder; only its out/*.json files are read")
    verify.add_argument("--profile", help="the service's own profile (data/PROFILE.md); without it no fact may be cited")
    verify.add_argument("--analysis", help="the analysis copy judge-input wrote (default: the work folder's)")
    verify.add_argument("--terms", help="the judge's ruling from judge-result (default: no keyword approved)")
    verify.add_argument("--pdf-out", required=True, help="where to write the PDF when every check passes")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except resume_terms.ProfileError as exc:
        print(f"{args.command} failed: profile_invalid: {exc}", file=sys.stderr)
        return PROFILE_INVALID_EXIT
    except (ToolError, resume_model.ModelError, resume_model.ContentError, resume_score.AnalysisError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
