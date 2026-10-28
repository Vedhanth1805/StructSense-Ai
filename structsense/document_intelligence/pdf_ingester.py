import os
import logging
from typing import List, Dict, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFIngester:
    """
    Extracts clean text from government project PDFs.
    Handles searchable PDFs via PyMuPDF and scanned PDFs via Tesseract OCR.
    """

    def __init__(self, tesseract_lang: str = "eng", ocr_psm: int = 6):
        """
        :param tesseract_lang: Language code for Tesseract OCR (default 'eng')
        :param ocr_psm: Page segmentation mode for Tesseract (default 6 – uniform block of text)
        """
        self.tesseract_lang = tesseract_lang
        self.ocr_psm = ocr_psm
        self.last_ocr_status = "not_attempted"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _ocr_page(self, page: fitz.Page, dpi: int = 300) -> str:
        """
        Run Tesseract OCR on a single PDF page.
        """
        self.last_ocr_status = "running"
        try:
            pix = page.get_pixmap(dpi=dpi)
            mode = "RGB" if pix.n < 4 else "CMYK"
            image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            config = f"--psm {self.ocr_psm}"
            text = pytesseract.image_to_string(
                image, lang=self.tesseract_lang, config=config
            )
            self.last_ocr_status = "succeeded" if text.strip() else "no_text"
            return text.strip()
        except pytesseract.pytesseract.TesseractNotFoundError as e:
            self.last_ocr_status = "unavailable"
            logger.warning("Tesseract OCR is unavailable for page %s: %s", page.number + 1, e)
            return ""
        except Exception as e:
            self.last_ocr_status = "failed"
            logger.warning(f"OCR failed for page {page.number + 1}: {e}")
            return ""

    def _extract_page_tables(self, page: fitz.Page) -> List[List[List[str]]]:
        """Extract visible table cells when supported by the installed PyMuPDF."""
        try:
            finder = page.find_tables()
            return [table.extract() for table in finder.tables]
        except (AttributeError, Exception) as exc:
            logger.debug("Table extraction unavailable on page %s: %s", page.number + 1, exc)
            return []

    def _extract_page_text(self, page: fitz.Page) -> Tuple[str, str, List[List[List[str]]]]:
        """
        Try to extract text via PyMuPDF first. If the extracted text is short
        (< 50 characters) we consider it a scanned page and fallback to OCR.
        Returns (text, method) where method is 'pymupdf' or 'tesseract'.
        """
        text = page.get_text().strip()
        tables = self._extract_page_tables(page)
        table_text = "\n".join(" | ".join(str(cell or "") for cell in row) for table in tables for row in table)
        if table_text:
            text = "\n".join(part for part in (text, table_text) if part)
        if len(text) >= 50 or tables:
            return text, "pymupdf", tables
        # Fallback to OCR
        self.last_ocr_status = "not_attempted"
        ocr_text = self._ocr_page(page)
        if ocr_text:
            text = ocr_text
            return text, "tesseract", tables
        # Keep any machine-readable text if OCR is unavailable or fails.
        if text:
            return text, "pymupdf", tables
        if self.last_ocr_status == "unavailable":
            return text, "tesseract_unavailable", tables
        return text, "tesseract_failed", tables

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract_text_from_pdf(self, pdf_path: str) -> Dict:
        """
        Extract text from a single PDF file.

        Returns a dictionary with detailed information or an error message.
        """
        filename = os.path.basename(pdf_path)
        try:
            doc = fitz.open(pdf_path)
        except fitz.fitz.PdfPasswordError:
            logger.error(f"Password protected PDF: {filename}")
            return {"filename": filename, "error": "Password protected PDF"}
        except Exception as e:
            logger.warning(f"Failed to open PDF '{filename}': {e}")
            return {"filename": filename, "error": str(e)}

        try:
            total_pages = doc.page_count
            if total_pages == 0:
                logger.warning(f"Empty PDF: {filename}")
                return {"filename": filename, "error": "Empty PDF"}

            pages_info = []
            full_text_parts = []
            all_pymupdf = True
            all_tesseract = True

            for i in range(total_pages):
                page = doc[i]
                text, method, tables = self._extract_page_text(page)
                char_count = len(text)
                page_dict = {
                    "page_num": i + 1,
                    "text": text,
                    "tables": tables,
                    "method": method,
                    "char_count": char_count,
                }
                if method.startswith("tesseract_"):
                    page_dict["ocr_status"] = "unavailable" if method == "tesseract_unavailable" else "failed"
                pages_info.append(page_dict)
                full_text_parts.append(text)
                if method != "pymupdf":
                    all_pymupdf = False
                if method != "tesseract":
                    all_tesseract = False

            full_text = "\n".join(full_text_parts)

            methods = [page["method"] for page in pages_info]
            if methods and all(method == "tesseract_unavailable" for method in methods):
                quality = "ocr_unavailable"
            elif methods and all(method == "tesseract_failed" for method in methods):
                quality = "ocr_failed"
            elif all_pymupdf:
                quality = "high"
            elif all_tesseract:
                quality = "ocr_only"
            else:
                quality = "mixed"

            result = {
                "filename": filename,
                "total_pages": total_pages,
                "pages": pages_info,
                "full_text": full_text,
                "extraction_quality": quality,
            }
            return result

        except Exception as e:
            logger.warning(f"Error processing PDF '{filename}': {e}")
            return {"filename": filename, "error": str(e)}

    def ingest_multiple(self, pdf_paths: List[str]) -> Dict:
        """
        Process multiple PDF files and combine the results into a unified corpus.
        """
        documents = []
        combined_text_parts = []
        total_pages = 0
        document_map = {}
        current_page_index = 1

        for path in pdf_paths:
            doc_result = self.extract_text_from_pdf(path)
            if "error" in doc_result:
                # Skip documents that could not be processed
                logger.warning(f"Skipping document '{doc_result['filename']}' due to error: {doc_result['error']}")
                continue

            documents.append(doc_result)
            combined_text_parts.append(doc_result.get("full_text", ""))

            doc_total = doc_result.get("total_pages", 0)
            if doc_total > 0:
                start_page = current_page_index
                end_page = current_page_index + doc_total - 1
                key = f"page_{start_page}_to_{end_page}"
                document_map[key] = doc_result["filename"]
                current_page_index = end_page + 1
                total_pages += doc_total

        combined_text = "\n".join(combined_text_parts)

        return {
            "documents": documents,
            "combined_text": combined_text,
            "total_pages": total_pages,
            "document_map": document_map,
        }

# ----------------------------------------------------------------------
# Standalone test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    ingester = PDFIngester()
    # This is a simple sanity check; no real PDFs are processed here.
    print("PDFIngester ready")
    # Example usage (uncomment when you have PDFs):
    # results = ingester.ingest_multiple(["/path/to/file1.pdf", "/path/to/file2.pdf"])
    # print(results)
