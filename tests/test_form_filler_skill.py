import re
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent / ".claude" / "skills" / "job-application-form-filler"
         / "SKILL.md").read_text(encoding="utf-8")
TEXT = " ".join(SKILL.split())


def section(title: str) -> str:
    start = TEXT.index(f"## {title}")
    end = TEXT.find("## Step", start + 3)
    return TEXT[start:end if end != -1 else None]


def test_attached_documents_are_checked_against_the_profile_email():
    step = section("Step 1")
    assert "compare each with the profile document's `Email` row" in step
    assert "any document whose email can't be read" in step


def test_email_fields_always_get_the_profile_email():
    assert ("Every email field gets the profile document's `Email` row, even when an attached document shows "
            "another address") in TEXT


def test_contact_email_mismatch_is_a_red_flag():
    step = section("Step 6")
    assert "shows a contact email other than the profile document's" in step
    assert "suggest generating it again from the viewer before submitting" in step
    assert "if no email could be read from it" in step


def test_no_email_address_in_the_skill():
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", SKILL)


def test_submitting_is_the_default_with_a_review_opt_out():
    assert "**Submitting is the default.**" in TEXT
    assert "No submit word is needed" in TEXT
    assert "`/job-application-form-filler <id> review`" in TEXT and "**review mode**" in TEXT
    assert "only after the user has reviewed the form" not in TEXT


def test_agreement_boxes_are_ticked_except_opt_ins_and_extra_terms():
    row = TEXT[TEXT.index("| Consent, privacy, GDPR"):]
    row = row[:900]
    assert "tick each one the form needs" in row
    for opt_in in ("job alerts", "newsletters", "SMS", "talent community", "sharing with other employers"):
        assert opt_in in row
    assert "anything that costs money, an employment contract, a non-compete" in row


def test_self_review_before_submitting():
    assert "**Self-review.**" in TEXT
    assert "this check is the review" in TEXT


def test_guardrails_stop_and_ask():
    step = section("Step 5")
    assert "do not submit" in step and "AskUserQuestion" in step
    for g in ("A required answer the sources do not give", "a required salary question", "A Step 6 red flag",
              "pay floor, sponsorship refused, not the company site or its ATS, wrong company or role",
              "contact email mismatch", "a cover letter field with no letter",
              "Files not attached for this application ID", "A sign-in, CAPTCHA or bot check",
              "A validation error that does not clear",
              "An agreement beyond the standard application terms"):
        assert g in step, g
    for gone in ("No acknowledgments", "**Simple:**", "only when this run asked for it"):
        assert gone not in step


def test_drafts_listed_in_full_in_the_report():
    step = section("Step 6")
    assert "Each drafted open-ended answer, in full" in step
    assert "the final report must list every one" in step


def test_questions_only_in_review_mode():
    step = section("Step 7")
    assert "Default mode: Step 5 submits and confirms" in step
    assert "review mode" in step


def slack_mode() -> str:
    start = TEXT.index("## Slack mode")
    return TEXT[start:TEXT.index("## Step 1", start)]


def test_slack_mode_asks_through_the_relay_not_ask_user_question():
    mode = slack_mode()
    assert "Questions go to the thread, never to AskUserQuestion" in mode
    assert "python3 scripts/ask_slack.py post <id> -" in mode and 'python3 scripts/ask_slack.py wait <id> "$QID"' in mode
    assert "Exit code 3 means no answer yet: run the same `wait` again" in mode


def test_slack_mode_marks_approvals_and_keeps_every_other_rule():
    mode = slack_mode()
    assert '`"kind": "approval"`' in mode and "agree and submit" in mode and "mark it applied anyway" in mode
    assert "Everything in this skill applies unchanged" in mode


def test_slack_mode_posts_reports_and_cancels_on_takeover():
    mode = slack_mode()
    assert "/application/<id>/slack-update" in mode
    assert 'python3 scripts/ask_slack.py cancel <id> "$QID"' in mode
