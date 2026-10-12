import io
import os
import base64
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
DOCX_EXTENSIONS = {".docx"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".xml", ".log"}

MAX_EXTRACTED_CHARS = 50000  # Cap document context to ~12k tokens safely

class DocumentParserService:
    @staticmethod
    def parse_document(file_bytes: bytes, file_name: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses document attachments:
        - For images: does NOT run OCR; preserves image for direct multimodal LLM processing.
        - For PDFs: extracts text page-by-page via pypdf.
        - For Word docs: extracts text paragraphs and tables via python-docx.
        - For text files: decodes UTF-8 string content.
        """
        ext = os.path.splitext(file_name)[1].lower()
        file_size = len(file_bytes)
        
        is_image = (
            ext in IMAGE_EXTENSIONS or 
            (content_type and content_type.startswith("image/"))
        )

        if is_image:
            return DocumentParserService._process_image(file_bytes, file_name, ext, content_type)
        elif ext in PDF_EXTENSIONS or content_type == "application/pdf":
            return DocumentParserService._process_pdf(file_bytes, file_name, file_size)
        elif ext in DOCX_EXTENSIONS or (content_type and "wordprocessingml" in content_type):
            return DocumentParserService._process_docx(file_bytes, file_name, file_size)
        else:
            return DocumentParserService._process_text(file_bytes, file_name, ext, file_size)

    @staticmethod
    def _process_image(file_bytes: bytes, file_name: str, ext: str, content_type: Optional[str]) -> Dict[str, Any]:
        dimensions = ""
        mime_type = content_type
        if not mime_type:
            ext_clean = ext.lower().lstrip(".")
            if ext_clean in ("jpg", "jpeg"):
                mime_type = "image/jpeg"
            else:
                mime_type = f"image/{ext_clean}"
        elif mime_type == "image/jpg":
            mime_type = "image/jpeg"

        try:
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            img_format = (img.format or "PNG").lower()
            if not content_type:
                mime_type = f"image/{img_format}"
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"
            dimensions = f" ({img.width}x{img.height})"
        except ImportError:
            logger.warning("PIL (Pillow) is not installed; processing image with basic metadata.")
        except Exception as e:
            logger.warning(f"Could not inspect image dimensions for {file_name}: {e}")

        b64_str = base64.b64encode(file_bytes).decode("utf-8")
        base64_data = f"data:{mime_type};base64,{b64_str}"

        return {
            "file_name": file_name,
            "file_type": mime_type,
            "file_size": len(file_bytes),
            "is_image": True,
            "extracted_text": None,
            "preview_text": f"Image: {file_name}{dimensions}",
            "base64_data": base64_data
        }

    @staticmethod
    def _process_pdf(file_bytes: bytes, file_name: str, file_size: int) -> Dict[str, Any]:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            total_chars = 0
            
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                clean_text = text.strip()
                if clean_text:
                    pages_text.append(f"--- [Page {i + 1}] ---\n{clean_text}")
                    total_chars += len(clean_text)
                    if total_chars >= MAX_EXTRACTED_CHARS:
                        pages_text.append(f"\n[... Document truncated at {MAX_EXTRACTED_CHARS} characters ...]")
                        break

            full_text = "\n\n".join(pages_text) if pages_text else "[Empty PDF document]"
            return {
                "file_name": file_name,
                "file_type": "application/pdf",
                "file_size": file_size,
                "is_image": False,
                "extracted_text": full_text,
                "preview_text": full_text[:200] + "..." if len(full_text) > 200 else full_text,
                "base64_data": None
            }
        except Exception as e:
            logger.error(f"Error parsing PDF {file_name}: {e}")
            raise ValueError(f"Could not parse PDF document: {str(e)}")

    @staticmethod
    def _process_docx(file_bytes: bytes, file_name: str, file_size: int) -> Dict[str, Any]:
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            parts = []
            total_chars = 0
            
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    parts.append(text)
                    total_chars += len(text)
                    if total_chars >= MAX_EXTRACTED_CHARS:
                        parts.append(f"\n[... Document truncated at {MAX_EXTRACTED_CHARS} characters ...]")
                        break
            
            # Also extract tables if within budget
            if total_chars < MAX_EXTRACTED_CHARS:
                for table in doc.tables:
                    for row in table.rows:
                        row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                        if row_text:
                            parts.append(row_text)
                            total_chars += len(row_text)
                            if total_chars >= MAX_EXTRACTED_CHARS:
                                break

            full_text = "\n\n".join(parts) if parts else "[Empty Word document]"
            return {
                "file_name": file_name,
                "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "file_size": file_size,
                "is_image": False,
                "extracted_text": full_text,
                "preview_text": full_text[:200] + "..." if len(full_text) > 200 else full_text,
                "base64_data": None
            }
        except Exception as e:
            logger.error(f"Error parsing Word document {file_name}: {e}")
            raise ValueError(f"Could not parse Word document: {str(e)}")

    @staticmethod
    def _process_text(file_bytes: bytes, file_name: str, ext: str, file_size: int) -> Dict[str, Any]:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception:
                text = file_bytes.decode("utf-8", errors="replace")

        clean_text = text.strip()
        if len(clean_text) > MAX_EXTRACTED_CHARS:
            clean_text = clean_text[:MAX_EXTRACTED_CHARS] + f"\n\n[... Text truncated at {MAX_EXTRACTED_CHARS} characters ...]"

        mime_type = "text/plain"
        if ext == ".md":
            mime_type = "text/markdown"
        elif ext == ".json":
            mime_type = "application/json"
        elif ext == ".csv":
            mime_type = "text/csv"

        return {
            "file_name": file_name,
            "file_type": mime_type,
            "file_size": file_size,
            "is_image": False,
            "extracted_text": clean_text or "[Empty text document]",
            "preview_text": clean_text[:200] + "..." if len(clean_text) > 200 else clean_text,
            "base64_data": None
        }
