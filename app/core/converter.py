"""
File conversion pipeline.

Supported input formats → intermediate representation (list of PIL Images):
  .pdf            → pypdfium2 renders each page
  .jpg/.jpeg/.png → opened directly with Pillow
  .docx           → converted to PDF via LibreOffice, then rendered
  .doc            → same as .docx (LibreOffice handles both)
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def file_to_images(file_path: str) -> List[Image.Image]:
    """
    Convert any supported file to a list of PIL Images (one per page/frame).
    Raises ValueError for unsupported types, RuntimeError on conversion failure.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in {".jpg", ".jpeg", ".png"}:
        return _image_file_to_images(path)
    elif suffix == ".pdf":
        return _pdf_to_images(path)
    elif suffix in {".doc", ".docx"}:
        return _word_to_images(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------


def _image_file_to_images(path: Path) -> List[Image.Image]:
    img = Image.open(path).convert("RGB")
    return [img]


def _pdf_to_images(path: Path, dpi: int = 150) -> List[Image.Image]:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError(
            "pypdfium2 is required for PDF support. "
            "Install with: pip install pypdfium2"
        )

    images: List[Image.Image] = []
    doc = pdfium.PdfDocument(str(path))
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            scale = dpi / 72  # pdfium uses 72 dpi base
            bitmap = page.render(scale=scale, rotation=0)
            pil_img = bitmap.to_pil().convert("RGB")
            images.append(pil_img)
    finally:
        doc.close()

    logger.debug("Rendered %d page(s) from PDF: %s", len(images), path.name)
    return images


def _word_to_images(path: Path) -> List[Image.Image]:
    """
    Convert .doc / .docx → PDF via LibreOffice headless, then render pages.
    LibreOffice must be installed on the system (apt install libreoffice).
    """
    _check_libreoffice()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Copy source file into temp dir so LibreOffice can write next to it
        tmp_source = Path(tmp_dir) / path.name
        shutil.copy2(path, tmp_source)

        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmp_dir,
                str(tmp_source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice conversion failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        pdf_path = Path(tmp_dir) / (tmp_source.stem + ".pdf")
        if not pdf_path.exists():
            raise RuntimeError(
                f"LibreOffice did not produce a PDF for {path.name}. "
                f"stdout: {result.stdout.strip()}"
            )

        logger.debug("LibreOffice converted %s → %s", path.name, pdf_path.name)
        # Render while still inside the temp dir context
        return _pdf_to_images(pdf_path)


def _check_libreoffice() -> None:
    if shutil.which("libreoffice") is None:
        raise RuntimeError(
            "LibreOffice is not installed or not in PATH. "
            "Install with: apt install libreoffice  (or brew install libreoffice on macOS)"
        )
