from unittest.mock import patch

from app.generation import generate_output
from app.models import JobRow

JOB = JobRow(company="Acme", role="Engineer", full_job_description="Build things")


def test_stub_returns_rendered_pdf():
    with patch("app.generation.render_pdf", return_value=b"%PDF-1.5 fake") as render:
        out = generate_output(JOB, job_id="job-1")
    render.assert_called_once_with()
    assert out.content == b"%PDF-1.5 fake"
    assert out.content_type == "application/pdf"
    assert out.extension == "pdf"
