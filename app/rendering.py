import shutil
import subprocess
import tempfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data"
RENDER_TIMEOUT_SECONDS = 120
TEMPLATE_SUFFIXES = {".tex", ".cls", ".sty", ".png", ".jpg", ".jpeg"}


class RenderError(Exception):
    """Raised when TeX compilation fails; the message is for server-side logs only."""


def render_pdf(main_tex: str = "BASE.tex", template_dir: Path | None = None) -> bytes:
    """Compile a TeX file from the template directory to PDF bytes.

    Compilation happens in a throwaway copy of the template files, so the bundled
    sources are never modified and concurrent renders cannot interfere.
    """
    source_dir = Path(template_dir or TEMPLATE_DIR)
    if not (source_dir / main_tex).is_file():
        raise RenderError(f"template not found: {main_tex}")

    with tempfile.TemporaryDirectory(prefix="render-") as tmp:
        workdir = Path(tmp)
        for path in source_dir.iterdir():
            if path.is_file() and path.suffix.lower() in TEMPLATE_SUFFIXES:
                shutil.copy2(path, workdir / path.name)

        # --untrusted disables shell-escape, which matters once the TeX is generated.
        cmd = ["tectonic", "-X", "compile", "--untrusted", "--outdir", str(workdir), main_tex]
        try:
            result = subprocess.run(
                cmd, cwd=workdir, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"render timed out after {RENDER_TIMEOUT_SECONDS}s") from exc
        except OSError as exc:
            raise RenderError(f"could not run tectonic: {exc}") from exc

        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-2000:]
            raise RenderError(f"tectonic exited with {result.returncode}: {tail}")

        pdf_path = workdir / (Path(main_tex).stem + ".pdf")
        if not pdf_path.is_file():
            raise RenderError("tectonic reported success but produced no PDF")
        return pdf_path.read_bytes()
