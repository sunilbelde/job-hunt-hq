from unittest.mock import patch

from app.generation import generate_output
from app.models import StoredApplication

APPLICATION = StoredApplication(
    id="3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13", company="Acme", role="Engineer", job_link="https://example.com/1",
    posting_source_type="employer_site", verification_method="employer_site",
    official_apply_url="", status="verified",
)


def test_stub_returns_rendered_pdf():
    with patch("app.generation.render_pdf", return_value=b"%PDF-1.5 fake") as render:
        out = generate_output(APPLICATION)
    render.assert_called_once_with()
    assert out.content == b"%PDF-1.5 fake"
    assert out.content_type == "application/pdf"
    assert out.extension == "pdf"
