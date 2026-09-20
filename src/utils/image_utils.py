"""Image processing utilities for vision multimodal pipelines."""

import base64
import io

from PIL import Image


def optimize_image_for_vision(
    image: Image.Image,
    max_dimension: int = 2048,
) -> Image.Image:
    """Optimiza una imagen para inferencia visual multimodal.

    - Convierte modos con canal alfa (RGBA, LA, P) a RGB.
    - Reduce proporcionalmente la escala si excede max_dimension (estándar OpenAI detail:high).
    """
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    if max(width, height) > max_dimension:
        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    return image


def pil_to_base64_data_uri(
    image: Image.Image,
    image_format: str = "JPEG",
    quality: int = 85,
) -> str:
    """Codifica una imagen PIL a un Data URI base64 en memoria (data:image/jpeg;base64,...).

    No genera archivos temporales en disco.
    """
    optimized = optimize_image_for_vision(image)
    buffer = io.BytesIO()
    optimized.save(buffer, format=image_format, quality=quality, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    mime_type = "image/jpeg" if image_format.upper() in ("JPEG", "JPG") else f"image/{image_format.lower()}"
    return f"data:{mime_type};base64,{encoded}"


def base64_data_uri_to_pil(data_uri: str) -> Image.Image:
    """Decodifica un Data URI base64 de vuelta a un objeto PIL.Image."""
    if "," in data_uri:
        _, encoded = data_uri.split(",", 1)
    else:
        encoded = data_uri

    image_bytes = base64.b64decode(encoded)
    return Image.open(io.BytesIO(image_bytes))
