from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from PIL import Image, ImageDraw

router = APIRouter(prefix="/api/background", tags=["background"])


def _clamp(v: int, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, v))


def _gradient(draw: ImageDraw.ImageDraw, width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    for y in range(height):
        ratio = y / height
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _sun(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 204, 102), outline=(255, 186, 73), width=2)


def _cloud(draw: ImageDraw.ImageDraw, x: int, y: int, scale: int = 40) -> None:
    base = scale
    draw.ellipse((x, y, x + base, y + base), fill=(255, 255, 255, 230))
    draw.ellipse((x + base // 2, y - base // 3, x + base * 2, y + base), fill=(255, 255, 255, 230))
    draw.ellipse((x + base, y, x + base * 3, y + base), fill=(255, 255, 255, 230))


def _mountain(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple[int, int, int]) -> None:
    h = height // 2
    draw.polygon([(width * 0.1, height), (width * 0.35, h), (width * 0.6, height)], fill=color)
    draw.polygon([(width * 0.5, height), (width * 0.75, h * 0.9), (width * 0.95, height)], fill=tuple(_clamp(c - 15) for c in color))


def _foreground(draw: ImageDraw.ImageDraw, width: int, height: int, theme: str) -> None:
    if theme == "night":
        draw.rectangle((0, height * 0.65, width, height), fill=(40, 60, 50))
    else:
        draw.rectangle((0, height * 0.65, width, height), fill=(104, 179, 95))


def build_background(width: int, height: int, theme: Literal["sunny", "dusk", "night"]) -> bytes:
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    if theme == "night":
        _gradient(draw, width, height, (15, 24, 48), (4, 7, 16))
        _mountain(draw, width, int(height * 0.7), (60, 80, 90))
    elif theme == "dusk":
        _gradient(draw, width, height, (255, 184, 138), (38, 62, 100))
        _mountain(draw, width, int(height * 0.7), (90, 110, 120))
    else:
        _gradient(draw, width, height, (135, 206, 250), (207, 236, 255))
        _mountain(draw, width, int(height * 0.7), (120, 160, 150))

    _foreground(draw, width, height, theme)

    if theme != "night":
        _sun(draw, int(width * 0.15), int(height * 0.18), int(min(width, height) * 0.06))
        _cloud(draw, int(width * 0.3), int(height * 0.15), int(min(width, height) * 0.08))
        _cloud(draw, int(width * 0.55), int(height * 0.22), int(min(width, height) * 0.07))
    else:
        # moon
        _sun(draw, int(width * 0.82), int(height * 0.18), int(min(width, height) * 0.05))
        for i in range(5):
            draw.ellipse(
                (width * (0.1 + 0.15 * i), height * 0.1, width * (0.12 + 0.15 * i), height * 0.12),
                fill=(255, 255, 255, 180),
            )

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("")
async def generate_background(
    width: int = Query(960, ge=100, le=2400),
    height: int = Query(600, ge=100, le=1600),
    theme: Literal["sunny", "dusk", "night"] = "sunny",
) -> Response:
    png_bytes = await _build_async(width, height, theme)
    return Response(content=png_bytes, media_type="image/png")


async def _build_async(width: int, height: int, theme: str) -> bytes:
    # Pillow 是 CPU 操作，放在线程池可选，这里直接同步生成
    return build_background(width, height, theme)
