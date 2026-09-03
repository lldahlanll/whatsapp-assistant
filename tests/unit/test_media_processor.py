"""Unit tests for MediaProcessor."""

import io

from PIL import Image

from whatsapp_platform.shared.utils.media_processor import MediaProcessor


def test_compress_image_resizes_oversized_image():
    # Create an in-memory oversized image (2000x2000)
    img = Image.new("RGB", (2000, 2000), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    compressed = MediaProcessor.compress_image(raw_bytes, max_dimension=1000)

    # Verify compressed image is smaller and within max dimension
    result_img = Image.open(io.BytesIO(compressed))
    assert result_img.width <= 1000
    assert result_img.height <= 1000


def test_compress_image_handles_invalid_bytes_gracefully():
    invalid_bytes = b"not-a-valid-image-bytes"
    res = MediaProcessor.compress_image(invalid_bytes)
    assert res == invalid_bytes


def test_extract_text_from_pdf_returns_empty_on_invalid_data():
    res = MediaProcessor.extract_text_from_pdf(b"invalid-pdf")
    assert res == ""
