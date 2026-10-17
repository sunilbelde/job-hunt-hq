from dataclasses import dataclass

from app.models import JobRow
from app.rendering import render_pdf


@dataclass(frozen=True)
class GeneratedFile:
    content: bytes
    content_type: str
    extension: str


def generate_output(job: JobRow, *, job_id: str | None = None) -> GeneratedFile:
    """Stub generator: renders the baseline resume, ignoring the job details.

    Replaced by the tailoring pipeline in a later change, which will render generated
    TeX through the same render_pdf path. Callers depend only on this signature and
    on GeneratedFile. Raises RenderError if compilation fails.
    """
    return GeneratedFile(content=render_pdf(), content_type="application/pdf", extension="pdf")
