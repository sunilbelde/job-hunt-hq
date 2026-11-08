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
