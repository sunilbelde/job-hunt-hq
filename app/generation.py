from dataclasses import dataclass

from app import tailoring
from app.models import StoredApplication
from app.rendering import render_pdf
from app.settings import Settings
from app.tailoring import Match, RunStats


@dataclass(frozen=True)
class GeneratedFile:
    content: bytes
    content_type: str
    extension: str
    match: Match | None = None
    run: RunStats | None = None  # the Claude run's turns and estimated cost, when one ran


def generate_output(application: StoredApplication, settings: Settings) -> GeneratedFile:
    """The resume to save for an application.

    Without usable posting text the base resume is saved unscored. Otherwise the tailor-resume skill
    scores the base resume and, below the threshold, tailors it (app/tailoring.py). The base resume
    always comes from render_pdf. Raises RenderError or TailoringError, and then nothing may be saved.
    """
    if not tailoring.posting_usable(application.full_job_description):
        return GeneratedFile(render_pdf(), "application/pdf", "pdf", match=Match("no_job_description"))
    result = tailoring.run(application, settings)
    pdf = result.pdf if result.pdf is not None else render_pdf()
    return GeneratedFile(pdf, "application/pdf", "pdf", match=result.match, run=result.run)
