"""Photo clean-up before a model reads handwriting.

Measured on a real register page shot with a phone (scripts/handwriting_eval.py): the cleaned page
reads as well as the raw photo, gets the written date right more often, and is a smaller upload.
"""

import io

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

LONG_SIDE = 2000


def prepare_for_reading(data: bytes, long_side: int = LONG_SIDE) -> tuple[bytes, str]:
    """Upright (EXIF), grey, auto-contrast, longest side `long_side`, lightly sharpened, as JPEG.
    Returns the original bytes and their type when the image cannot be opened."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except (UnidentifiedImageError, OSError):
        return data, "image/jpeg"
    img = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    scale = long_side / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=3))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue(), "image/jpeg"
