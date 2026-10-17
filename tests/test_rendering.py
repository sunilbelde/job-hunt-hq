import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app import rendering
from app.rendering import RenderError, render_pdf


@pytest.fixture
def templates(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "BASE.tex").write_text("\\documentclass{resume}")
    (d / "resume.cls").write_text("% class")
    (d / "BASE.pdf").write_bytes(b"%PDF-old")
    return d


def fake_run(returncode=0, write_pdf=True, record=None):
    def run(cmd, cwd, **kwargs):
        if record is not None:
            record.update(cmd=cmd, cwd=Path(cwd), kwargs=kwargs, files=sorted(p.name for p in Path(cwd).iterdir()))
        if write_pdf:
            (Path(cwd) / "BASE.pdf").write_bytes(b"%PDF-new")
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="boom /secret/path")
    return run


def test_success_returns_pdf_bytes_and_cleans_up(templates):
    seen = {}
    with patch("app.rendering.subprocess.run", fake_run(record=seen)):
        assert render_pdf(template_dir=templates) == b"%PDF-new"
    assert "--untrusted" in seen["cmd"] and seen["kwargs"]["timeout"] == rendering.RENDER_TIMEOUT_SECONDS
    assert seen["files"] == ["BASE.tex", "resume.cls"]  # old BASE.pdf not copied in
    assert not seen["cwd"].exists()


def test_bundled_sources_unchanged(templates):
    before = {p.name: p.read_bytes() for p in templates.iterdir()}
    with patch("app.rendering.subprocess.run", fake_run()):
        render_pdf(template_dir=templates)
    assert {p.name: p.read_bytes() for p in templates.iterdir()} == before


def test_nonzero_exit_raises_and_cleans_up(templates):
    seen = {}
    with patch("app.rendering.subprocess.run", fake_run(returncode=1, record=seen)):
        with pytest.raises(RenderError, match="exited with 1"):
            render_pdf(template_dir=templates)
    assert not seen["cwd"].exists()


def test_timeout_raises(templates):
    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
    with patch("app.rendering.subprocess.run", run):
        with pytest.raises(RenderError, match="timed out"):
            render_pdf(template_dir=templates)


def test_missing_binary_raises(templates):
    with patch("app.rendering.subprocess.run", side_effect=FileNotFoundError("tectonic")):
        with pytest.raises(RenderError, match="could not run"):
            render_pdf(template_dir=templates)


def test_missing_output_raises(templates):
    with patch("app.rendering.subprocess.run", fake_run(write_pdf=False)):
        with pytest.raises(RenderError, match="no PDF"):
            render_pdf(template_dir=templates)


def test_missing_template_raises(tmp_path):
    with pytest.raises(RenderError, match="template not found"):
        render_pdf(template_dir=tmp_path)


@pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")
def test_real_render_matches_baseline_content():
    pypdf = pytest.importorskip("pypdf")
    import io
    pdf = render_pdf()
    assert pdf.startswith(b"%PDF")
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    text = re.sub(r"\s+", " ", reader.pages[0].extract_text())
    assert "SUNIL BELDE" in text
