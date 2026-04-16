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

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def file_to_images(file_path: str) -> List[Image.Image]:
    """
    Convert any supported file to a list of PIL Images (one per page/frame).
    Raises ValueError for unsupported types, RuntimeError on conversion failure.
    """
    from app.core.config import settings

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in {".jpg", ".jpeg", ".png"}:
        images = _image_file_to_images(path)
    elif suffix == ".pdf":
        images = _pdf_to_images(path, dpi=settings.PDF_DPI)
    elif suffix in {".doc", ".docx"}:
        images = _word_to_images(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    if settings.PREPROCESS_IMAGES:
        images = [_preprocess_image(img) for img in images]

    return images


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------


def _image_file_to_images(path: Path) -> List[Image.Image]:
    img = Image.open(path).convert("RGB")
    return [img]


def _pdf_to_images(path: Path, dpi: int = 200) -> List[Image.Image]:
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
    Uses the writer_pdf_Export filter for higher-fidelity output.
    """
    from app.core.config import settings

    _check_libreoffice()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Copy source file into temp dir so LibreOffice can write next to it
        tmp_source = Path(tmp_dir) / path.name
        shutil.copy2(path, tmp_source)

        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf:writer_pdf_Export",
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
        return _pdf_to_images(pdf_path, dpi=settings.PDF_DPI)


def _check_libreoffice() -> None:
    if shutil.which("libreoffice") is None:
        raise RuntimeError(
            "LibreOffice is not installed or not in PATH. "
            "Install with: apt install libreoffice  (or brew install libreoffice on macOS)"
        )


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------


def _preprocess_image(img: Image.Image) -> Image.Image:
    """Deskew, enhance contrast, and sharpen an RGB image before OCR."""
    img = _deskew(img)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    return img


def _deskew(img: Image.Image) -> Image.Image:
    """
    Detect and correct skew angle via projection profile variance.
    Downsamples for speed; applies correction to the full-resolution image.
    Falls back to no-op if numpy is unavailable.
    """
    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy not available — skipping deskew")
        return img

    # Downsample to at most 800px on the long side for fast angle search
    scale = min(1.0, 800.0 / max(img.width, img.height))
    small = img.convert("L").resize(
        (int(img.width * scale), int(img.height * scale)),
        Image.LANCZOS,
    )

    best_angle = 0.0
    best_score = -1.0

    for angle in np.arange(-5.0, 5.1, 0.5):
        rotated = small.rotate(float(angle), expand=False, fillcolor=255)
        arr = np.array(rotated, dtype=np.float32)
        binary = (arr < 128).astype(np.float32)
        score = float(np.var(binary.sum(axis=1)))
        if score > best_score:
            best_score = score
            best_angle = float(angle)

    if abs(best_angle) > 0.3:
        logger.debug("Deskewing image by %.1f°", best_angle)
        return img.rotate(best_angle, expand=True, fillcolor=(255, 255, 255))
    return img
