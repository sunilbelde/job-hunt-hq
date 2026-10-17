import pytest
from pydantic import ValidationError

from app.models import JobRow

MINIMAL = {"company": "Acme", "role": "Engineer", "full_job_description": "Build things"}


def test_minimal_posting_accepted():
    job = JobRow.model_validate(MINIMAL)
    assert job.location is None and job.job_link is None


def test_free_form_optional_values_pass_through_unchanged():
    data = {**MINIMAL, "salary": "$120k-$150k + equity", "date_posted": "yesterday", "job_link": "not a url"}
    job = JobRow.model_validate(data)
    assert (job.salary, job.date_posted, job.job_link) == (
        "$120k-$150k + equity", "yesterday", "not a url")


def test_all_fields_accepted():
    data = {**MINIMAL, **{k: "x" for k in (
        "location", "work_type", "salary", "date_posted", "sponsorship", "why_it_fits", "job_link")}}
    assert JobRow.model_validate(data).why_it_fits == "x"


@pytest.mark.parametrize("field", ["company", "role", "full_job_description"])
def test_missing_required_field(field):
    data = {k: v for k, v in MINIMAL.items() if k != field}
    with pytest.raises(ValidationError) as exc:
        JobRow.model_validate(data)
    assert exc.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["company", "role", "full_job_description"])
def test_empty_required_field(field):
    with pytest.raises(ValidationError):
        JobRow.model_validate({**MINIMAL, field: ""})


@pytest.mark.parametrize("field,value", [("salary", 100), ("company", None), ("role", 5), ("job_link", ["x"])])
def test_wrong_type_rejected(field, value):
    with pytest.raises(ValidationError):
        JobRow.model_validate({**MINIMAL, field: value})


def test_unknown_fields_ignored():
    assert not hasattr(JobRow.model_validate({**MINIMAL, "extra": "x"}), "extra")
