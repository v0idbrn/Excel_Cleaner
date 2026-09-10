"""Genera assets/icono.ico — icono comercial de Excel Cleaner (multi-tamaño).

Uso: python demo_scripts/make_icon.py
Requiere Pillow (solo para generar el asset; el icono es un recurso estático
que se empaqueta en el .exe, no una dependencia en runtime).
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ASSETS / "icono.ico"

# Paleta comercial (coherente con demo_scripts/make_demo.py)
GREEN = (27, 133, 90, 255)       # verde Excel moderno
DARK = (26, 34, 47, 255)         # pizarra
WHITE = (245, 247, 250, 255)
GRID = (70, 84, 105, 255)
RIM = (163, 210, 184, 255)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _font(px: int):
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = size
    r = max(2, size // 5)

    # Tile redondeado oscuro con borde claro
    d.rounded_rectangle([0, 0, w - 1, w - 1], radius=r, fill=DARK)
    d.rounded_rectangle(
        [0, 0, w - 1, w - 1], radius=r, outline=RIM, width=max(1, size // 32)
    )

    # Rejilla sutil (sugerencia de hoja de cálculo)
    if size >= 32:
        step = size // 4
        for i in range(1, 4):
            coord = i * step
            d.line([(coord, size // 4), (coord, w - size // 5)], fill=GRID, width=1)
            d.line([(size // 5, coord), (w - size // 4, coord)], fill=GRID, width=1)

    # Check verde = "limpio"
    lw = max(2, size // 10)
    pts = [int(size * f) for f in (0.28, 0.55, 0.44, 0.70, 0.74, 0.34)]
    d.line([(pts[0], pts[1]), (pts[2], pts[3])], fill=GREEN, width=lw)
    d.line([(pts[2], pts[3]), (pts[4], pts[5])], fill=GREEN, width=lw)

    # Letra "X" blanca (identidad del producto)
    try:
        f = _font(int(size * 0.5))
        d.text((size / 2, size * 0.27), "X", font=f, fill=WHITE, anchor="mm")
    except Exception:
        pass  # decorativo: si falla la fuente, el icono sigue siendo válido

    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    # Un solo master 256px + lista `sizes`: Pillow genera cada frame escalado.
    # (append_images no compone multi-frame ICO de forma fiable en Pillow 12)
    master = render(256)
    master.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    main()
