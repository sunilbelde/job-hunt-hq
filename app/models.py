from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


ApplicationStatus = Literal["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]
MatchStatus = Literal["no_job_description", "base_meets_threshold", "tailored"]

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


class CoverLetterRequest(BaseModel):
    """The POST /cover-letter body: an application ID, as a JSON string. Everything else comes from the store."""

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


class ResumeMatch(BaseModel):
    status: MatchStatus = Field(
        description="How the saved resume was chosen. `no_job_description`: the application has no usable "
        "posting text (missing or under 50 words), so the base resume was saved unscored. "
        "`base_meets_threshold`: the base resume scored at or above `threshold` and was saved. "
        "`tailored`: the base resume scored below it, and a tailored resume was saved."
    )
    threshold: int = Field(description="The score at or above which the base resume is kept. Always 70.")
    base_score: int | None = Field(description="The base resume's match score from 0 to 100, or null when not scored.")
    tailored_score: int | None = Field(description="The tailored resume's match score from 0 to 100, or null unless tailored.")
    added_terms: list[str] = Field(
        description="Posting keywords the base resume lacks that the tailored resume adds. A separate Claude judge, "
        "which sees the resume and the owner's profile list but never the posting, approved each one with evidence. "
        "Empty unless `status` is `tailored`."
    )


JobStatus = Literal["running", "done", "failed"]


class GenerationAccepted(BaseModel):
    ok: Literal[True] = True
    application_id: str
    status: Literal["running"] = Field(description="Always `running`: the run continues after this response.")
    started_at: str = Field(
        description="When the running job started, as an ISO 8601 UTC timestamp. A request made while a job of the "
        "same kind is already running for the application returns that job's `started_at` and starts no second run."
    )


class JobState(BaseModel):
    ok: Literal[True] = True
    application_id: str
    status: JobStatus = Field(
        description="`running`: still generating. `done`: saved; `saved_path` and the result are set. `failed`: "
        "nothing new was saved; `error` says why. A job running when the service restarts becomes `failed` with "
        "`error` `Interrupted by a service restart`."
    )
    started_at: str = Field(description="When the job started, as an ISO 8601 UTC timestamp.")
    finished_at: str | None = Field(description="When the job finished, or null while it runs.")
    saved_path: str | None = Field(
        description="File name of the saved PDF, with no folder: `SUNIL BELDE.pdf` for a resume, `SUNIL BELDE - "
        "Cover Letter.pdf` for a cover letter. Null unless `done`."
    )
    error: str | None = Field(
        description="Why the job failed, or null unless `failed`: `Resume generation failed`, `Cover letter "
        "generation failed`, `Storage service unavailable` or `Interrupted by a service restart`. Never holds "
        "exception text, paths or posting text."
    )


class ResumeJobStatus(JobState):
    match: ResumeMatch | None = Field(description="How the saved resume was chosen, with the match scores; null unless `done`.")


class CoverLetterJobStatus(JobState):
    text: str | None = Field(
        description="The letter as plain text: the greeting, the paragraphs and the sign-off, separated by blank "
        "lines, with no markup. The same words as the PDF, for application forms that take pasted text. Null unless "
        "`done`."
    )


# The viewer's read endpoints. Like the models above, these only describe responses.


class KeywordRow(BaseModel):
    term: str
    importance: Literal["required", "preferred"]
    present: bool = Field(description="Whether this resume's text contains the keyword or one of its aliases.")


class RequirementRow(BaseModel):
    id: str
    text: str = Field(description="The requirement as read from the posting.")
    importance: Literal["required", "preferred"]
    status: Literal["met", "partial", "missing"] = Field(description="How Claude assessed this resume against it.")
    counted: Literal["met", "partial", "missing"] = Field(
        description="What the score counted: `missing` when the assessment's quotes are not in the resume."
    )
    unverified: bool
    reason: str | None = Field(description="Why the assessment was not counted, or null.")
    evidence: list[str] = Field(description="The assessment's quotes from this resume.")


class ScoreBreakdown(BaseModel):
    score: int = Field(description="The match score from 0 to 100.")
    decision: Literal["keep", "tailor"]
    threshold: int
    keyword_coverage: float = Field(description="Weighted share of the posting's keywords covered, from 0 to 1.")
    requirement_coverage: float = Field(description="Weighted share of the posting's requirements met, from 0 to 1.")
    keywords: list[KeywordRow]
    requirements: list[RequirementRow]


class RejectedTerm(BaseModel):
    term: str
    reason: str = Field(description="Why the judge did not approve the keyword.")


class ResumeReport(BaseModel):
    version: int = Field(description="The report's shape. Always 1.")
    status: MatchStatus
    threshold: int
    base_score: int | None
    tailored_score: int | None
    added_terms: list[str]
    base: ScoreBreakdown | None = Field(description="The base resume's breakdown, or null when not scored.")
    tailored: ScoreBreakdown | None = Field(description="The tailored resume's breakdown, or null unless tailored.")
    rejected_terms: list[RejectedTerm] = Field(description="Posting keywords the judge rejected. Empty unless tailored.")
    generated_at: str = Field(description="When the resume was generated, UTC, ISO 8601.")
    saved_path: str = Field(description="File name of the saved resume, `SUNIL BELDE.pdf`, with no folder.")


class ReportSummary(BaseModel):
    generated_at: str
    status: MatchStatus
    threshold: int
    base_score: int | None
    tailored_score: int | None


class ApplicationListItem(BaseModel):
    id: str
    company: str
    role: str
    status: ApplicationStatus
    created_at: str
    updated_at: str | None
    report: ReportSummary | None = Field(description="The latest generation's summary, or null if none is stored.")


class ApplicationList(BaseModel):
    ok: Literal[True] = True
    applications: list[ApplicationListItem] = Field(
        description="Every application, most recently generated first, then most recently recorded. No posting text."
    )


class ApplicationRecord(StoredApplication):
    created_at: str
    updated_at: str | None = None


class ApplicationDetail(BaseModel):
    ok: Literal[True] = True
    application: ApplicationRecord = Field(description="Every stored field of the application.")
    report: ResumeReport | None = Field(
        description="The latest generation report, or null when none is stored (never generated, or generated "
        "before reports existed)."
    )
