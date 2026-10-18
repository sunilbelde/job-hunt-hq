from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


ApplicationStatus = Literal["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]

# Example bodies shown in the API docs; tests send each one to check it is accepted.
APPLICATION_EXAMPLE = {
    "company": "Acme Corp",
    "role": "Senior Software Engineer",
    "job_link": "https://job-boards.greenhouse.io/acme/jobs/1234567",
    "posting_source_type": "recruiting_platform",
    "verification_method": "official_apply_match",
    "official_apply_url": "https://job-boards.greenhouse.io/acme/jobs/1234567",
    "location": "San Francisco, CA (Hybrid)",
    "work_type": "Hybrid",
    "salary": "$220,000 - $300,000",
    "date_posted": "2026-10-15",
    "company_careers_url": "https://www.acme.com/careers",
    "official_employer_domain": "acme.com",
}
UPDATE_EXAMPLE = {"status": "applied"}
RESUME_EXAMPLE = {"application_id": "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}

# Fixed once recorded: job_link is the dedupe key and the rest are its verification record.
IMMUTABLE_FIELDS = ("job_link", "posting_source_type", "verification_method", "official_apply_url")


class ApplicationRow(BaseModel):
    """A verified job posting to record. Free-form values are stored as sent."""

    model_config = ConfigDict(extra="ignore", json_schema_extra={"examples": [APPLICATION_EXAMPLE]})

    company: StrictStr = Field(min_length=1)
    role: StrictStr = Field(min_length=1)
    job_link: StrictStr = Field(min_length=1)
    posting_source_type: Literal["recruiting_platform", "employer_site"]
    verification_method: Literal["official_apply_match", "employer_site"]
    official_apply_url: StrictStr
    location: StrictStr | None = None
    work_type: StrictStr | None = None
    salary: StrictStr | None = None
    date_posted: StrictStr | None = None
    sponsorship: StrictStr | None = None
    why_it_fits: StrictStr | None = None
    company_careers_url: StrictStr | None = None
    official_employer_domain: StrictStr | None = None
    full_job_description: StrictStr | None = None

    # Messages name fields only; callers may show them to the client, so never include values.
    @model_validator(mode="after")
    def _verified_pairing(self) -> "ApplicationRow":
        if self.posting_source_type == "recruiting_platform":
            if self.verification_method != "official_apply_match":
                raise ValueError(
                    "verification_method must be official_apply_match when "
                    "posting_source_type is recruiting_platform"
                )
            if self.official_apply_url != self.job_link:
                raise ValueError(
                    "official_apply_url must equal job_link when "
                    "verification_method is official_apply_match"
                )
        else:
            if self.verification_method != "employer_site":
                raise ValueError(
                    "verification_method must be employer_site when posting_source_type is employer_site"
                )
            if self.official_apply_url != "":
                raise ValueError(
                    "official_apply_url must be empty when posting_source_type is employer_site"
                )
        return self


class ApplicationUpdate(BaseModel):
    """A partial update. Only fields present in the body are written: use exclude_unset."""

    model_config = ConfigDict(extra="ignore", json_schema_extra={"examples": [UPDATE_EXAMPLE]})

    # The defaults only mark a field as absent; an explicit null is still checked against the type,
    # so status, company and role cannot be cleared.
    status: ApplicationStatus = None
    company: StrictStr = Field(default=None, min_length=1)
    role: StrictStr = Field(default=None, min_length=1)
    location: StrictStr | None = None
    work_type: StrictStr | None = None
    salary: StrictStr | None = None
    date_posted: StrictStr | None = None
    sponsorship: StrictStr | None = None
    why_it_fits: StrictStr | None = None
    company_careers_url: StrictStr | None = None
    official_employer_domain: StrictStr | None = None
    full_job_description: StrictStr | None = None

    # Runs before extra="ignore" would drop them. Messages name fields only.
    @model_validator(mode="before")
    @classmethod
    def _no_immutable_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            present = [name for name in IMMUTABLE_FIELDS if name in data]
            if present:
                raise ValueError(f"cannot be changed: {', '.join(present)}")
        return data

    @model_validator(mode="after")
    def _something_to_update(self) -> "ApplicationUpdate":
        if not self.model_fields_set:
            raise ValueError("Request body has no updatable fields")
        return self


class ResumeRequest(BaseModel):
    """The POST /resume body: an application ID, as a JSON string. Everything else comes from the store."""

    model_config = ConfigDict(extra="ignore", json_schema_extra={"examples": [RESUME_EXAMPLE]})

    application_id: StrictStr


class StoredApplication(BaseModel):
    """An application as read back from the store. Rows were validated when recorded, so no rules here."""

    model_config = ConfigDict(extra="ignore")

    id: str
    company: str
    role: str
    job_link: str
    posting_source_type: str
    verification_method: str
    official_apply_url: str
    status: str
    location: str | None = None
    work_type: str | None = None
    salary: str | None = None
    date_posted: str | None = None
    sponsorship: str | None = None
    why_it_fits: str | None = None
    company_careers_url: str | None = None
    official_employer_domain: str | None = None
    full_job_description: str | None = None


# Response shapes, used only to describe responses in the API docs. Handlers build their
# responses directly, so these never filter or reshape what is sent.


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    message: str


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


class ApplicationRecorded(BaseModel):
    ok: Literal[True] = True
    application_id: str


class ApplicationUpdated(BaseModel):
    ok: Literal[True] = True
    application_id: str
    status: ApplicationStatus


class ResumeCreated(BaseModel):
    ok: Literal[True] = True
    application_id: str
    saved_path: str
