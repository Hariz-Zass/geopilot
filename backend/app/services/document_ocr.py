from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz


OCR_ENGINE = "tesseract"
OCR_ENGINE_VERSION = "5"
OCR_LANGUAGES = "msa+eng"
OCR_DPI = 400
OCR_PSM = 11
OCR_TIMEOUT_SECONDS = 240


class DocumentOcrError(Exception):
    pass


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    text: str
    char_count: int
    engine: str
    engine_version: str
    languages: str
    dpi: int
    psm: int


def ocr_pdf_page(
    pdf_path: Path,
    *,
    page_number: int,
    dpi: int = OCR_DPI,
    psm: int = OCR_PSM,
    languages: str = OCR_LANGUAGES,
) -> OcrPageResult:
    pdf_path = Path(pdf_path).expanduser().resolve()

    if not pdf_path.is_file():
        raise DocumentOcrError(
            f"PDF source does not exist: {pdf_path}"
        )

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise DocumentOcrError(
            "PDF source could not be opened"
        ) from exc

    try:
        if page_number < 1 or page_number > document.page_count:
            raise DocumentOcrError(
                f"page_number must be between 1 and {document.page_count}"
            )

        page = document.load_page(page_number - 1)

        pixmap = page.get_pixmap(
            dpi=dpi,
            alpha=False,
        )

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "page.png"
            pixmap.save(image_path)

            try:
                result = subprocess.run(
                    [
                        OCR_ENGINE,
                        str(image_path),
                        "stdout",
                        "-l",
                        languages,
                        "--psm",
                        str(psm),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=OCR_TIMEOUT_SECONDS,
                    check=False,
                )
            except (
                OSError,
                subprocess.SubprocessError,
            ) as exc:
                raise DocumentOcrError(
                    "OCR engine execution failed"
                ) from exc

            if result.returncode != 0:
                detail = result.stderr.strip()

                raise DocumentOcrError(
                    "OCR engine returned a failure"
                    + (f": {detail}" if detail else "")
                )

            text = result.stdout.strip()

            return OcrPageResult(
                page_number=page_number,
                text=text,
                char_count=len(text),
                engine=OCR_ENGINE,
                engine_version=OCR_ENGINE_VERSION,
                languages=languages,
                dpi=dpi,
                psm=psm,
            )

    finally:
        document.close()
