from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class JobRow(BaseModel):
    """A job posting. Values are free-form strings and are never parsed or normalized."""

    model_config = ConfigDict(extra="ignore")

    company: StrictStr = Field(min_length=1)
    role: StrictStr = Field(min_length=1)
    full_job_description: StrictStr = Field(min_length=1)
    location: StrictStr | None = None
    work_type: StrictStr | None = None
    salary: StrictStr | None = None
    date_posted: StrictStr | None = None
    sponsorship: StrictStr | None = None
    why_it_fits: StrictStr | None = None
    job_link: StrictStr | None = None


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
