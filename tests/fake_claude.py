"""A stand-in for the Claude Code CLI: records how it was called, then plays one scenario.

`install()` copies this file into a test folder, with a config file beside it naming the scenario, and
returns the path to use as CLAUDE_BIN. app/tailoring.py hands the fake an environment built from scratch,
so the config travels next to the script rather than in an environment variable.

Each `-p` call plays the role of one of the service's runs:
    analysis   "/tailor-resume ." in a work folder without judge/terms.json
    judge      "/judge-resume-terms ."
    tailoring  "/tailor-resume ." once judge/terms.json is there

Scenarios:
    keep         the analysis scores the base resume 77
    tailor       the analysis scores 57 (Kafka and Airflow missing); the judge approves Airflow from the
                 profile and rejects Kafka; the tailoring adds Airflow to a skills line
    broken       like tailor, but the tailored content drops a job
    auth         a rejected token: is_error with subtype "success" and api_error_status 401
    max_turns    is_error with subtype "error_max_turns"
    budget       is_error with subtype "error_max_budget_usd"
    garbage      prints something that is not JSON and exits 2
    hang         starts a `sleep` in its own session, as Claude's Bash tool does, and waits

The failure scenarios play out in the run named by the `fail` option (default: the analysis; the other
runs then behave as in `tailor`). Other options: `analysis` and `verdicts` replace what those runs write
(`verdicts` may be a string, written as is), `cost` maps a role to its reported cost, `sleep` maps a role
to seconds to wait first, `add_skill` names the skills item the tailoring adds (None for none), and
`tamper_analysis` has the tailoring run rewrite out/analysis.json.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FAILURES = ("auth", "max_turns", "budget", "garbage", "hang")


def install(folder: Path, scenario: str, **options) -> Path:
    from tests.tailoring_fixtures import ANALYSIS, JUDGE_VERDICTS, weak_analysis

    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "claude"
    source = Path(__file__).read_text()
    script.write_text(f"#!{sys.executable}\n" + source)
    script.chmod(0o755)
    config = {"scenario": scenario, "record": str(folder / "calls.jsonl"), "strong_analysis": ANALYSIS,
              "analysis": weak_analysis(), "verdicts": JUDGE_VERDICTS, "pid_file": str(folder / "child.pid"),
              "fail": "analysis", "cost": {}, "sleep": {}, **options}
    if scenario == "keep" and "analysis" not in options:
        config["analysis"] = ANALYSIS
    (folder / "claude.json").write_text(json.dumps(config))
    return script


def calls(script: Path) -> list[dict]:
    record = script.parent / "calls.jsonl"
    return [json.loads(line) for line in record.read_text().splitlines()] if record.is_file() else []


def role(call: dict) -> str | None:
    """Which run a recorded call played: analysis, judge, tailoring, or None for other commands."""
    return call.get("role")


def _result(**fields) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 6,
                       "total_cost_usd": 0.12, "modelUsage": {"claude-opus-5-5": {}}, "result": "done", **fields})


def _write(name: str, data) -> None:
    Path("out", name).write_text(data if isinstance(data, str) else json.dumps(data))


def _tailor(config: dict, drop_job: bool) -> None:
    base = json.loads(Path("out", "base.json").read_text())
    skills = [dict(line, items=list(line["items"])) for line in base["skills"]]
    if config.get("add_skill", "Airflow"):
        skills[2]["items"].append(config.get("add_skill", "Airflow"))  # Data Engineering & Pipelines
    jobs = [{"id": job["id"], "bullets": [{"text": b["text"], "sources": [b["id"]]} for b in job["bullets"]]}
            for job in base["jobs"]]
    _write("tailored.json", {"skills": skills, "jobs": jobs[:-1] if drop_job else jobs})
    _write("assessment_tailored.json", config["strong_analysis"]["assessment"])
    if config.get("tamper_analysis"):
        # Drop the keywords the base lacks and mark every requirement met: a higher score if anyone trusted it.
        tampered = json.loads(Path("out", "analysis.json").read_text())
        tampered["keywords"] = [k for k in tampered["keywords"] if k["term"] not in ("Kafka", "Airflow")]
        _write("analysis.json", tampered)


def _role(args: list[str]) -> str | None:
    if "-p" not in args:
        return None
    prompt = args[args.index("-p") + 1]
    if prompt == "/judge-resume-terms .":
        return "judge"
    if prompt == "/tailor-resume .":
        return "tailoring" if Path("judge", "terms.json").is_file() else "analysis"
    return "live_check"


def main() -> int:
    config = json.loads(Path(__file__).with_name("claude.json").read_text())
    args = sys.argv[1:]
    run = _role(args)
    entry = {"argv": args, "cwd": os.getcwd(), "env": dict(os.environ), "cwd_entries": sorted(os.listdir(".")), "role": run}
    if run == "judge":
        entry["input"] = Path("input.md").read_text()
    with open(config["record"], "a") as record:
        record.write(json.dumps(entry) + "\n")
    scenario = config["scenario"]

    if args == ["--version"]:
        print("2.1.303 (Claude Code)")
        return 0
    if args[:2] == ["auth", "status"]:
        method = "api_key" if "ANTHROPIC_API_KEY" in os.environ else "oauth_token"
        print(json.dumps({"loggedIn": True, "authMethod": method}))
        return 0
    if scenario == "auth" and (run == config["fail"] or run == "live_check"):
        print(_result(is_error=True, api_error_status=401, result="Failed to authenticate."))
        return 1
    if run == "live_check":
        print(_result())  # the live check's one-line prompt
        return 0

    time.sleep(config["sleep"].get(run, 0))
    if scenario in FAILURES and run == config["fail"]:
        if scenario == "max_turns":
            print(_result(is_error=True, subtype="error_max_turns"))
            return 1
        if scenario == "budget":
            print(_result(is_error=True, subtype="error_max_budget_usd"))
            return 1
        if scenario == "garbage":
            print("this is not JSON")
            return 2
        if scenario == "hang":
            child = subprocess.Popen(["sleep", "60"], start_new_session=True)
            Path(config["pid_file"]).write_text(str(child.pid))
            time.sleep(60)
    elif run == "analysis":
        _write("analysis.json", config["analysis"])
    elif run == "judge":
        _write("verdicts.json", config["verdicts"])
    elif run == "tailoring":
        _tailor(config, drop_job=scenario == "broken")
    print(_result(total_cost_usd=config["cost"].get(run, 0.12)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
