"""Generate the sofa artwork from code (no image libraries needed).

Outputs:

* ``addon/WoWVoice/sofa.tga``  - 64x64 grayscale sofa for the minimap button.
  It is drawn in light greys on purpose: the addon tints it green/amber with
  ``SetVertexColor`` to show whether the desktop tool is running.
* ``assets/sofa.ico``          - Windows shortcut / window icon (warm colours).
* ``assets/sofa.png``          - the same warm icon, used by the README.

Run it with the project virtualenv:  .venv\\Scripts\\python.exe tools\\make_art.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRID = 64.0

# Shapes on a 64x64 grid: (x0, y0, x1, y1, corner radius)
BODY = (8, 26, 56, 46, 6)
BACK = (14, 13, 50, 31, 6)
ARM_LEFT = (4, 21, 15, 46, 6)
ARM_RIGHT = (49, 21, 60, 46, 6)
SEAT_LEFT = (15, 30, 32, 42, 4)
SEAT_RIGHT = (32, 30, 49, 42, 4)
LEG_LEFT = (10, 44, 16, 53, 2)
LEG_RIGHT = (48, 44, 54, 53, 2)

SILHOUETTE = (BODY, BACK, ARM_LEFT, ARM_RIGHT, SEAT_LEFT, SEAT_RIGHT, LEG_LEFT, LEG_RIGHT)

WARM = {
    "outline": (61, 42, 26),
    "body": (176, 123, 79),
    "back": (201, 149, 102),
    "seat": (227, 181, 131),
    "arm": (160, 107, 66),
    "leg": (90, 62, 40),
}

GREY = {
    "outline": (56, 56, 56),
    "body": (184, 184, 184),
    "back": (214, 214, 214),
    "seat": (242, 242, 242),
    "arm": (168, 168, 168),
    "leg": (82, 82, 82),
}

OUTLINE_WIDTH = 1.4


def in_round_rect(u: float, v: float, shape, pad: float = 0.0) -> bool:
    x0, y0, x1, y1, radius = shape
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    radius = max(radius + pad, 0.0)
    dx = max(x0 + radius - u, 0.0, u - (x1 - radius))
    dy = max(y0 + radius - v, 0.0, v - (y1 - radius))
    return dx * dx + dy * dy <= radius * radius


def in_sofa(u: float, v: float, pad: float = 0.0) -> bool:
    return any(in_round_rect(u, v, shape, pad) for shape in SILHOUETTE)


def layer_color(u: float, v: float, palette: dict) -> tuple[int, int, int]:
    if any(in_round_rect(u, v, shape) for shape in (LEG_LEFT, LEG_RIGHT)):
        return palette["leg"]
    if any(in_round_rect(u, v, shape) for shape in (ARM_LEFT, ARM_RIGHT)):
        return palette["arm"]
    if any(in_round_rect(u, v, shape) for shape in (SEAT_LEFT, SEAT_RIGHT)):
        return palette["seat"]
    if in_round_rect(u, v, BACK):
        return palette["back"]
    return palette["body"]


def render(size: int, palette: dict, supersample: int) -> bytearray:
    """Render RGBA pixels, top row first, anti-aliased by supersampling."""
    hi = size * supersample
    scale = size / GRID
    alpha = [[0.0] * size for _ in range(size)]
    colour = [[(0.0, 0.0, 0.0)] * size for _ in range(size)]

    for py in range(hi):
        v = (py + 0.5) / (supersample * scale)
        row_y = py * size // hi
        for px in range(hi):
            u = (px + 0.5) / (supersample * scale)
            if not in_sofa(u, v, OUTLINE_WIDTH):
                continue
            if in_sofa(u, v):
                rgb = layer_color(u, v, palette)
            else:
                rgb = palette["outline"]
            row_x = px * size // hi
            r, g, b = colour[row_y][row_x]
            colour[row_y][row_x] = (r + rgb[0], g + rgb[1], b + rgb[2])
            alpha[row_y][row_x] += 1.0

    pixels = bytearray(size * size * 4)
    total = float(supersample * supersample)
    for y in range(size):
        for x in range(size):
            covered = alpha[y][x]
            index = (y * size + x) * 4
            if covered <= 0:
                continue
            r, g, b = colour[y][x]
            pixels[index] = min(255, round(r / covered))
            pixels[index + 1] = min(255, round(g / covered))
            pixels[index + 2] = min(255, round(b / covered))
            pixels[index + 3] = min(255, round(255 * covered / total))
    return pixels


def tga_bytes(pixels: bytearray, size: int) -> bytes:
    """32-bit uncompressed TGA, bottom-left origin (the classic addon format)."""
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x08)
    body = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            i = (y * size + x) * 4
            body += bytes((pixels[i + 2], pixels[i + 1], pixels[i], pixels[i + 3]))
    return header + bytes(body)


def png_bytes(pixels: bytearray, size: int) -> bytes:
    raw = b"".join(
        b"\x00" + bytes(pixels[y * size * 4 : (y + 1) * size * 4]) for y in range(size)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def bmp_icon_image(pixels: bytearray, size: int) -> bytes:
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            i = (y * size + x) * 4
            xor += bytes((pixels[i + 2], pixels[i + 1], pixels[i], pixels[i + 3]))

    stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        row = bytearray(stride)
        for x in range(size):
            if pixels[(y * size + x) * 4 + 3] == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask += row

    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0
    )
    return header + bytes(xor) + bytes(mask)


def ico_bytes(images: list[tuple[int, bytearray]], png_size: int) -> bytes:
    entries = []
    payload = bytearray()
    offset = 6 + 16 * len(images)
    for size, pixels in images:
        if size == png_size:
            data = png_bytes(pixels, size)
        else:
            data = bmp_icon_image(pixels, size)
        entries.append(
            struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        )
        payload += data
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + bytes(payload)


def main() -> int:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    grey = render(64, GREY, supersample=6)
    (ROOT / "addon" / "WoWVoice" / "sofa.tga").write_bytes(tga_bytes(grey, 64))

    sizes = [16, 32, 48, 64, 128, 256]
    warm = {size: render(size, WARM, supersample=3 if size <= 128 else 2) for size in sizes}
    (assets / "sofa.ico").write_bytes(
        ico_bytes([(size, warm[size]) for size in sizes], png_size=256)
    )
    (assets / "sofa.png").write_bytes(png_bytes(warm[256], 256))

    for path in (
        ROOT / "addon" / "WoWVoice" / "sofa.tga",
        assets / "sofa.ico",
        assets / "sofa.png",
    ):
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
