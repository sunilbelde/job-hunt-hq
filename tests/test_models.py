import pytest
from pydantic import ValidationError

from app.models import ResumeRequest, StoredApplication

ID = "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"


# --- ResumeRequest ---

def test_resume_request_ignores_extra_fields():
    request = ResumeRequest.model_validate({"application_id": ID, "x": 1})
    assert request.application_id == ID and not hasattr(request, "x")


def test_resume_request_takes_any_string():
    # Whether the string is a UUID is checked by the endpoint, which answers 404, not 422.
    assert ResumeRequest.model_validate({"application_id": "not-a-uuid"}).application_id == "not-a-uuid"


@pytest.mark.parametrize("body", [{"application_id": 7}, {"application_id": 7.5}, {"application_id": True},
                                  {"application_id": None}, {"application_id": {"id": ID}}, {}])
def test_resume_request_rejects_non_string_ids(body):
    with pytest.raises(ValidationError) as exc:
        ResumeRequest.model_validate(body)
    assert exc.value.errors()[0]["loc"] == ("application_id",)


# --- StoredApplication ---

def test_stored_application_with_null_optional_fields():
    row = {
        "id": ID, "company": "Acme", "role": "Engineer", "job_link": "https://example.com/1",
        "posting_source_type": "employer_site", "verification_method": "employer_site",
        "official_apply_url": "", "status": "verified", "location": None, "full_job_description": None,
        "created_at": "2026-10-17T00:00:00Z", "updated_at": None,
    }
    application = StoredApplication.model_validate(row)
    assert application.id == ID and application.full_job_description is None and application.salary is None


# --- ApplicationRow ---

from app.models import ApplicationRow  # noqa: E402
from tests.conftest import GH_LINK, VALID_APPLICATION  # noqa: E402

REQUIRED_APPLICATION = {
    k: VALID_APPLICATION[k]
    for k in ("company", "role", "job_link", "posting_source_type", "verification_method", "official_apply_url")
}
EMPLOYER_SITE = {
    **REQUIRED_APPLICATION, "job_link": "https://www.acme.com/careers/1",
    "posting_source_type": "employer_site", "verification_method": "employer_site", "official_apply_url": "",
}


def error_text(data):
    with pytest.raises(ValidationError) as exc:
        ApplicationRow.model_validate(data)
    return str(exc.value.errors(include_input=False))


def test_client_example_accepted():
    row = ApplicationRow.model_validate(VALID_APPLICATION)
    assert row.model_dump() == VALID_APPLICATION


def test_required_only_accepted():
    row = ApplicationRow.model_validate(REQUIRED_APPLICATION)
    assert row.full_job_description is None and row.company_careers_url is None


def test_employer_site_with_empty_apply_url_accepted():
    assert ApplicationRow.model_validate(EMPLOYER_SITE).official_apply_url == ""


@pytest.mark.parametrize("field", list(REQUIRED_APPLICATION))
def test_missing_required_application_field(field):
    data = {k: v for k, v in REQUIRED_APPLICATION.items() if k != field}
    assert field in error_text(data)


@pytest.mark.parametrize("field", ["company", "role", "job_link"])
def test_empty_required_application_field(field):
    assert field in error_text({**REQUIRED_APPLICATION, field: ""})


@pytest.mark.parametrize("field,value", [("salary", 100), ("company", None), ("official_apply_url", None)])
def test_application_wrong_type(field, value):
    assert field in error_text({**REQUIRED_APPLICATION, field: value})


@pytest.mark.parametrize("field,value", [
    ("posting_source_type", "linkedin"),
    ("posting_source_type", "Employer_Site"),
    ("verification_method", "Official_Apply_Match"),
    ("verification_method", "found"),
])
def test_enum_values_exact(field, value):
    assert field in error_text({**REQUIRED_APPLICATION, field: value})


@pytest.mark.parametrize("data,field", [
    ({**EMPLOYER_SITE, "official_apply_url": "https://www.acme.com/careers/1"}, "official_apply_url"),
    ({**REQUIRED_APPLICATION, "official_apply_url": ""}, "official_apply_url"),
    ({**REQUIRED_APPLICATION, "official_apply_url": GH_LINK + "/"}, "official_apply_url"),
    ({**REQUIRED_APPLICATION, "verification_method": "employer_site"}, "verification_method"),
    ({**EMPLOYER_SITE, "verification_method": "official_apply_match"}, "verification_method"),
])
def test_pairing_rules(data, field):
    assert field in error_text(data)


def test_unknown_application_fields_ignored():
    row = ApplicationRow.model_validate({**REQUIRED_APPLICATION, "found": True})
    assert "found" not in row.model_dump()


# --- ApplicationUpdate ---

from app.models import IMMUTABLE_FIELDS, ApplicationUpdate  # noqa: E402

STATUSES = ["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]


def update_error(data):
    with pytest.raises(ValidationError) as exc:
        ApplicationUpdate.model_validate(data)
    return str(exc.value.errors(include_input=False))


@pytest.mark.parametrize("status", STATUSES)
def test_each_status_accepted(status):
    assert ApplicationUpdate.model_validate({"status": status}).model_dump(exclude_unset=True) == {"status": status}


@pytest.mark.parametrize("status", ["ghosted", "Applied", None, 1])
def test_bad_status_rejected(status):
    assert "status" in update_error({"status": status})


@pytest.mark.parametrize("value", ["", None])
@pytest.mark.parametrize("field", ["company", "role"])
def test_required_fields_cannot_be_emptied(field, value):
    assert field in update_error({field: value})


def test_wrong_type_rejected_on_update():
    assert "salary" in update_error({"salary": 5})


def test_null_clears_optional_and_absent_fields_left_out():
    update = ApplicationUpdate.model_validate({"sponsorship": None, "salary": "$1"})
    assert update.model_dump(exclude_unset=True) == {"sponsorship": None, "salary": "$1"}


@pytest.mark.parametrize("field", IMMUTABLE_FIELDS)
def test_immutable_field_rejected(field):
    assert field in update_error({field: "anything"})
    assert field in update_error({field: "anything", "status": "applied"})


def test_all_immutable_fields_named():
    text = update_error({name: "x" for name in IMMUTABLE_FIELDS})
    assert all(name in text for name in IMMUTABLE_FIELDS)


@pytest.mark.parametrize("body", [{}, {"found": True}])
def test_nothing_to_update_rejected(body):
    assert "no updatable fields" in update_error(body)


def test_unknown_field_ignored_on_update():
    update = ApplicationUpdate.model_validate({"status": "applied", "found": True})
    assert update.model_dump(exclude_unset=True) == {"status": "applied"}


@pytest.mark.parametrize("body", [
    {"status": "secret-ish-value"},
    {"job_link": "secret-ish-value"},
    {"company": "", "salary": "secret-ish-value", "location": 5},
])
def test_update_errors_do_not_echo_values(body):
    assert "secret-ish-value" not in update_error(body)
