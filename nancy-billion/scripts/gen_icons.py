#!/usr/bin/env python3
"""Draw the Billion reactor mark and write every icon the apps need.

One source of truth: the reactor is drawn procedurally here, so any size can be
regenerated without hunting for a master file. Everything is rendered at 4x and
downsampled, which is what gives the ring edges their softness.

    python scripts/gen_icons.py

Writes desktop/build/icon.png, frontend/public/icons/*, frontend/app/icon.png,
and mobile/resources/{icon,splash}.png.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent

BG = (5, 8, 14, 255)          # #05080e -- the control room's background
CYAN = (64, 224, 255)         # #40e0ff -- reactor cyan
GOLD = (245, 195, 90)         # accent, used sparingly on the core
SS = 4                        # supersample factor


def _reactor(size: int, *, bleed: float = 1.0, rounded: bool = True,
             transparent: bool = False) -> Image.Image:
    """Render the mark at `size` px.

    bleed < 1 shrinks the artwork inside the canvas, which is what maskable
    icons need so the ring survives being cropped to a circle by the launcher.
    """
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0) if transparent else BG)
    d = ImageDraw.Draw(img)
    c = s / 2
    r = (s / 2) * 0.82 * bleed

    if not transparent and rounded:
        # Rounded-square plate so the icon reads well undecorated on desktop.
        plate = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rounded_rectangle(
            [0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)
        img = plate
        d = ImageDraw.Draw(img)

    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    # Outer ring.
    lw = max(2, int(r * 0.085))
    gd.ellipse([c - r, c - r, c + r, c + r], outline=CYAN + (255,), width=lw)

    # Tick ring: 24 segments, evenly spaced, sitting just inside the outer ring.
    r_in, r_out = r * 0.66, r * 0.80
    for i in range(24):
        a = math.radians(i * 15)
        gd.line(
            [c + r_in * math.cos(a), c + r_in * math.sin(a),
             c + r_out * math.cos(a), c + r_out * math.sin(a)],
            fill=CYAN + (215,), width=max(2, int(r * 0.045)),
        )

    # Inner containment ring.
    ri = r * 0.52
    gd.ellipse([c - ri, c - ri, c + ri, c + ri],
               outline=CYAN + (255,), width=max(2, int(r * 0.055)))

    # Core: a hot cyan disc with a warm centre, so it reads as lit rather than flat.
    rc = r * 0.30
    gd.ellipse([c - rc, c - rc, c + rc, c + rc], fill=CYAN + (255,))
    rg = rc * 0.52
    gd.ellipse([c - rg, c - rg, c + rg, c + rg], fill=GOLD + (235,))

    # Bloom pass -- duplicate the artwork, blur it, lay it underneath.
    bloom = glow.filter(ImageFilter.GaussianBlur(radius=r * 0.14))
    img.alpha_composite(bloom)
    img.alpha_composite(bloom)   # twice: cheap way to get a brighter halo
    img.alpha_composite(glow)

    return img.resize((size, size), Image.LANCZOS)


def _splash(size: int = 2732) -> Image.Image:
    """Centred mark on the app background, sized for Capacitor's splash."""
    img = Image.new("RGBA", (size, size), BG)
    mark = _reactor(int(size * 0.22), rounded=False, transparent=True)
    off = (size - mark.width) // 2
    img.alpha_composite(mark, (off, off))
    return img


def write(img: Image.Image, rel: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    print(f"  {img.width:>4}x{img.height:<4} {rel}")


def main() -> None:
    print("Billion icons")

    # Desktop: electron-builder wants >=512 and derives .ico/.icns from it.
    write(_reactor(1024), "desktop/build/icon.png")

    # Web / PWA install.
    write(_reactor(192), "frontend/public/icons/billion-192.png")
    write(_reactor(512), "frontend/public/icons/billion-512.png")
    # Maskable: extra padding so launcher cropping never clips the ring.
    write(_reactor(512, bleed=0.72), "frontend/public/icons/billion-maskable-512.png")
    write(_reactor(64), "frontend/app/icon.png")

    # Mobile: @capacitor/assets reads these and generates every density.
    write(_reactor(1024, rounded=False), "mobile/resources/icon.png")
    write(_splash(), "mobile/resources/splash.png")

    print("done.")


if __name__ == "__main__":
    main()
