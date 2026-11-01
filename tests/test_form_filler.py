import json
from pathlib import Path

import pytest

from app import form_filler
from app.form_filler import FormFillLauncher, HerdrUnavailable, fill_command, tab_label

ID = "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"
REPO = Path("/repo with space")
# conftest replaces run_herdr in every test so none reaches the real session; these tests run the original
# against a stub script.
REAL_RUN_HERDR = form_filler.run_herdr


def reply(result: dict) -> str:
    return json.dumps({"id": "cli:x", "result": result})


class FakeHerdr:
    """Answers like the real CLI (shapes taken from herdr's own replies) and records every call."""

    def __init__(self, workspaces=None, tabs=None, fail_on=None):
        self.calls = []
        self.workspaces = workspaces if workspaces is not None else [{"workspace_id": "wK", "label": "Claude-Jobs-Automation"}]
        self.tabs = tabs or [{"tab_id": "wK:t1", "label": "1"}]
        self.fail_on = fail_on

    def __call__(self, args):
        self.calls.append(args)
        if self.fail_on and args[:2] == self.fail_on:
            raise HerdrUnavailable(f"herdr {args[0]} {args[1]} exited 1")
        match args[:2]:
            case ["workspace", "list"]:
                return reply({"workspaces": self.workspaces})
            case ["workspace", "create"]:
                return reply({"workspace": {"workspace_id": "wN"}, "tab": {"tab_id": "wN:t1"},
                              "root_pane": {"pane_id": "wN:p1"}})
            case ["tab", "list"]:
                return reply({"tabs": self.tabs})
            case ["tab", "create"]:
                return reply({"tab": {"tab_id": "wK:t2", "label": args[args.index("--label") + 1]},
                              "root_pane": {"pane_id": "wK:p2"}})
            case ["tab", "rename"]:
                return reply({"tab": {"tab_id": args[2], "label": args[3]}})
            case ["pane", "run"]:
                return ""
        raise AssertionError(f"unexpected call {args}")


def launcher(fake, claude_bin="/Users/me/.local/bin/claude"):
    return FormFillLauncher("herdr", claude_bin, "Claude-Jobs-Automation", cwd=REPO, runner=fake)


def test_opens_a_labelled_tab_in_the_workspace_and_runs_the_skill():
    fake = FakeHerdr()
    started = launcher(fake).start("Rula", "Staff Forward Deployed Engineer", ID)
    assert started == form_filler.FillStarted("wK:t2", f"Rula-Staff Forward Deployed Engineer-{ID}", "wK", False)
    assert fake.calls == [
        ["workspace", "list"],
        ["tab", "list", "--workspace", "wK"],
        ["tab", "create", "--workspace", "wK", "--cwd", str(REPO), "--label",
         f"Rula-Staff Forward Deployed Engineer-{ID}", "--no-focus"],
        ["pane", "run", "wK:p2", f"/Users/me/.local/bin/claude --chrome '/job-application-form-filler {ID}'"],
    ]


def test_an_open_tab_for_the_application_is_reused():
    fake = FakeHerdr(tabs=[{"tab_id": "wK:t1", "label": "1"}, {"tab_id": "wK:t4", "label": f"Old Name-Role-{ID}"}])
    started = launcher(fake).start("New Name", "Role", ID)
    assert started == form_filler.FillStarted("wK:t4", f"Old Name-Role-{ID}", "wK", True)
    assert [c[:2] for c in fake.calls] == [["workspace", "list"], ["tab", "list"]]


def test_missing_workspace_is_created_and_its_first_tab_used():
    fake = FakeHerdr(workspaces=[{"workspace_id": "w1", "label": "job-hunt-hq"}])
    started = launcher(fake).start("Acme", "Data Engineer", ID)
    assert started.tab_id == "wN:t1" and started.workspace_id == "wN" and not started.already_open
    assert fake.calls[1] == ["workspace", "create", "--cwd", str(REPO), "--label", "Claude-Jobs-Automation", "--no-focus"]
    assert fake.calls[2] == ["tab", "rename", "wN:t1", f"Acme-Data Engineer-{ID}"]
    assert fake.calls[3][:3] == ["pane", "run", "wN:p1"]


@pytest.mark.parametrize("step", [["workspace", "list"], ["tab", "list"], ["tab", "create"], ["pane", "run"]])
def test_a_failing_step_raises(step):
    with pytest.raises(HerdrUnavailable):
        launcher(FakeHerdr(fail_on=step)).start("Acme", "Role", ID)


@pytest.mark.parametrize("output", ["", "not json", "[]", '{"result": {}}', '{"no": "result"}'])
def test_unexpected_replies_raise(output):
    with pytest.raises(HerdrUnavailable):
        launcher(lambda args: output).start("Acme", "Role", ID)


def test_label_drops_control_characters_and_caps_parts():
    assert tab_label("Ac\x1b[31mme\n Corp", "  Data\tEngineer ", ID) == f"Ac[31mme Corp-Data Engineer-{ID}"
    long = tab_label("C" * 200, "R" * 200, ID)
    assert long == "C" * 60 + "-" + "R" * 60 + "-" + ID
    assert tab_label("", "", ID) == ID


def test_command_quotes_the_claude_path():
    assert fill_command("/path with space/claude", ID) == \
        f"'/path with space/claude' --chrome '/job-application-form-filler {ID}'"


def test_company_and_role_never_reach_the_command():
    fake = FakeHerdr()
    launcher(fake).start("Acme'; rm -rf ~; '", "$(whoami)", ID)
    run = fake.calls[-1]
    assert run[:3] == ["pane", "run", "wK:p2"] and "rm -rf" not in run[3] and "whoami" not in run[3]


def test_real_runner_passes_arguments_without_a_shell(tmp_path):
    log = tmp_path / "argv"
    herdr = tmp_path / "herdr"
    herdr.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\necho \'{{"result": {{}}}}\'\n')
    herdr.chmod(0o755)
    assert REAL_RUN_HERDR(str(herdr))(["tab", "rename", "wK:t1", "A B-$(x)"]) == '{"result": {}}\n'
    assert log.read_text().splitlines() == ["tab", "rename", "wK:t1", "A B-$(x)"]


def test_real_runner_failures(tmp_path):
    with pytest.raises(HerdrUnavailable, match="FileNotFoundError"):
        REAL_RUN_HERDR(str(tmp_path / "missing"))(["workspace", "list"])
    failing = tmp_path / "herdr"
    failing.write_text("#!/bin/sh\necho secret-detail >&2\nexit 3\n")
    failing.chmod(0o755)
    with pytest.raises(HerdrUnavailable) as raised:
        REAL_RUN_HERDR(str(failing))(["tab", "create"])
    assert str(raised.value) == "herdr tab create exited 3"
