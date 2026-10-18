from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


ApplicationStatus = Literal["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]

# Fixed once recorded: job_link is the dedupe key and the rest are its verification record.
IMMUTABLE_FIELDS = ("job_link", "posting_source_type", "verification_method", "official_apply_url")


class ApplicationRow(BaseModel):
    """A verified job posting to record. Free-form values are stored as sent."""

    model_config = ConfigDict(extra="ignore")

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

    model_config = ConfigDict(extra="ignore")

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
    """The POST /resume body: an application ID, as a JSON integer. Everything else comes from the store."""

    model_config = ConfigDict(extra="ignore")

    application_id: StrictInt


class StoredApplication(BaseModel):
    """An application as read back from the store. Rows were validated when recorded, so no rules here."""

    model_config = ConfigDict(extra="ignore")

    id: int
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
