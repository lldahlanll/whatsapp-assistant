"""Media Processing utilities (image compression, PDF text extraction)."""

import io

import structlog

logger = structlog.get_logger()


class MediaProcessor:
    """Helper service for processing media attachments."""

    @staticmethod
    def compress_image(
        image_bytes: bytes,
        max_dimension: int = 1280,
        quality: int = 85,
        output_format: str = "JPEG",
    ) -> bytes:
        """Resize and compress an image byte stream using Pillow.

        If Pillow is not installed or processing fails, returns the original bytes.
        """
        try:
            from PIL import Image

            img: Image.Image = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if saving as JPEG
            if img.mode in ("RGBA", "P") and output_format.upper() == "JPEG":
                img = img.convert("RGB")

            # Resize if dimensions exceed max_dimension while keeping aspect ratio
            width, height = img.size
            if width > max_dimension or height > max_dimension:
                if width > height:
                    new_w = max_dimension
                    new_h = int(height * (max_dimension / width))
                else:
                    new_h = max_dimension
                    new_w = int(width * (max_dimension / height))

                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                logger.debug(
                    "Resized image", old_size=(width, height), new_size=(new_w, new_h)
                )

            buf = io.BytesIO()
            img.save(buf, format=output_format, quality=quality, optimize=True)
            compressed_data = buf.getvalue()
            logger.info(
                "Compressed image",
                original_bytes=len(image_bytes),
                compressed_bytes=len(compressed_data),
            )
            return compressed_data
        except ImportError:
            logger.warning("Pillow not installed; returning raw image bytes")
            return image_bytes
        except Exception as exc:
            logger.error("Failed to compress image", error=str(exc), exc_info=True)
            return image_bytes

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 20) -> str:
        """Extract text from a PDF document using PyMuPDF (fitz) or PyPDF fallback.

        Args:
            pdf_bytes: Raw bytes of the PDF file.
            max_pages: Maximum number of pages to read.

        Returns:
            Extracted string content.
        """
        if not pdf_bytes:
            return ""

        # Try PyMuPDF (fitz)
        try:
            import fitz  # type: ignore[import-untyped]

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            extracted_text = []

            for page_idx in range(min(len(doc), max_pages)):
                page = doc.load_page(page_idx)
                extracted_text.append(page.get_text())

            full_text = "\n".join(extracted_text).strip()
            logger.info(
                "Extracted text from PDF using PyMuPDF",
                pages=min(len(doc), max_pages),
                text_len=len(full_text),
            )
            return full_text
        except ImportError:
            logger.debug("PyMuPDF (fitz) not available, attempting fallback")
        except Exception as exc:
            logger.error("Error reading PDF with PyMuPDF", error=str(exc), exc_info=True)

        # Fallback to PyPDF if available
        try:
            import pypdf  # type: ignore[import-not-found,import-untyped]

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            extracted_text = []
            for page_idx in range(min(len(reader.pages), max_pages)):
                extracted_text.append(reader.pages[page_idx].extract_text() or "")

            full_text = "\n".join(extracted_text).strip()
            logger.info("Extracted text from PDF using PyPDF", text_len=len(full_text))
            return full_text
        except ImportError:
            logger.warning("Neither PyMuPDF nor PyPDF installed for PDF extraction")
            return ""
        except Exception as exc:
            logger.error("Failed to extract PDF text", error=str(exc), exc_info=True)
            return ""
