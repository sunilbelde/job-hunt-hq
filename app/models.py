from pydantic import BaseModel, ConfigDict, Field, StrictStr


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
