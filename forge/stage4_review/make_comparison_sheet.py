#!/usr/bin/env python3
"""Create a side-by-side visual acceptance sheet for AI vision review.

The sheet is only evidence packaging. It does not score the images. the agent or
another AI vision reviewer should inspect the generated sheet and write the
score back with stage4_review/append_review.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    cursor = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    while cursor + 8 <= len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        chunk_type = data[cursor + 4 : cursor + 8]
        chunk_data = data[cursor + 8 : cursor + 8 + length]
        cursor += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth != 8 or interlace != 0:
        raise ValueError("unsupported PNG; expected 8-bit non-interlaced image")
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError("unsupported PNG color type; convert to RGB/RGBA first")
    channels = channels_by_type[color_type]
    row_bytes = width * channels
    raw = zlib.decompress(bytes(idat))
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(row_bytes)
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + row_bytes])
        offset += row_bytes
        for index in range(row_bytes):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + paeth_predictor(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter {filter_type}")
        rows.append(row)
        previous = row
    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for x in range(width):
            base = x * channels
            if color_type == 0:
                gray = row[base]
                pixels.append((gray, gray, gray, 255))
            elif color_type == 2:
                pixels.append((row[base], row[base + 1], row[base + 2], 255))
            elif color_type == 4:
                gray = row[base]
                pixels.append((gray, gray, gray, row[base + 1]))
            elif color_type == 6:
                pixels.append((row[base], row[base + 1], row[base + 2], row[base + 3]))
    return width, height, pixels


def write_png_rgb(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    if len(pixels) != width * height:
        raise ValueError("pixel payload has the wrong size")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind)
        checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        for red, green, blue in pixels[y * width : (y + 1) * width]:
            scanlines.extend((red, green, blue))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), level=6))
        + chunk(b"IEND", b"")
    )


def load_image(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    try:
        return read_png(path)
    except Exception as direct_error:
        sips = shutil.which("sips")
        if not sips:
            raise ValueError(f"could not decode {path.name} as PNG and sips is unavailable: {direct_error}") from direct_error
        with tempfile.TemporaryDirectory() as tmpdir:
            converted = Path(tmpdir) / "converted.png"
            result = subprocess.run(
                [sips, "-s", "format", "png", str(path), "--out", str(converted)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError(result.stderr.strip() or result.stdout.strip() or "sips conversion failed")
            return read_png(converted)


def composite_over_checker(pixel: tuple[int, int, int, int], x: int, y: int) -> tuple[int, int, int]:
    red, green, blue, alpha = pixel
    background = 238 if ((x // 12 + y // 12) % 2 == 0) else 210
    mix = alpha / 255.0
    return (
        round(red * mix + background * (1 - mix)),
        round(green * mix + background * (1 - mix)),
        round(blue * mix + background * (1 - mix)),
    )


def resize_cover(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
    target_w: int,
    target_h: int,
) -> list[tuple[int, int, int]]:
    scale = max(target_w / width, target_h / height)
    scaled_w = max(1, round(width * scale))
    scaled_h = max(1, round(height * scale))
    offset_x = max(0, (scaled_w - target_w) // 2)
    offset_y = max(0, (scaled_h - target_h) // 2)
    output: list[tuple[int, int, int]] = []
    for y in range(target_h):
        source_y = min(height - 1, max(0, int((y + offset_y) / scale)))
        for x in range(target_w):
            source_x = min(width - 1, max(0, int((x + offset_x) / scale)))
            output.append(composite_over_checker(pixels[source_y * width + source_x], x, y))
    return output


def fill_rect(
    canvas: list[tuple[int, int, int]],
    width: int,
    x0: int,
    y0: int,
    rect_w: int,
    rect_h: int,
    color: tuple[int, int, int],
) -> None:
    height = len(canvas) // width
    for y in range(max(0, y0), min(height, y0 + rect_h)):
        row = y * width
        for x in range(max(0, x0), min(width, x0 + rect_w)):
            canvas[row + x] = color


def blit(
    canvas: list[tuple[int, int, int]],
    width: int,
    image: list[tuple[int, int, int]],
    image_w: int,
    x0: int,
    y0: int,
) -> None:
    image_h = len(image) // image_w
    height = len(canvas) // width
    for y in range(image_h):
        target_y = y0 + y
        if target_y < 0 or target_y >= height:
            continue
        for x in range(image_w):
            target_x = x0 + x
            if 0 <= target_x < width:
                canvas[target_y * width + target_x] = image[y * image_w + x]


def create_sheet(
    reference: Path,
    render: Path,
    out: Path,
    width: int,
    height: int,
    gutter: int,
) -> dict:
    ref_w, ref_h, ref_pixels = load_image(reference)
    ren_w, ren_h, ren_pixels = load_image(render)
    panel_w = width
    panel_h = height
    canvas_w = panel_w * 2 + gutter * 3
    header_h = 28
    canvas_h = panel_h + gutter * 2 + header_h
    canvas = [(246, 242, 236)] * (canvas_w * canvas_h)
    fill_rect(canvas, canvas_w, gutter, gutter, panel_w, header_h, (40, 45, 48))
    fill_rect(canvas, canvas_w, gutter * 2 + panel_w, gutter, panel_w, header_h, (40, 45, 48))
    fill_rect(canvas, canvas_w, gutter, gutter + header_h, panel_w, panel_h, (230, 230, 230))
    fill_rect(canvas, canvas_w, gutter * 2 + panel_w, gutter + header_h, panel_w, panel_h, (230, 230, 230))
    ref_panel = resize_cover(ref_w, ref_h, ref_pixels, panel_w, panel_h)
    ren_panel = resize_cover(ren_w, ren_h, ren_pixels, panel_w, panel_h)
    blit(canvas, canvas_w, ref_panel, panel_w, gutter, gutter + header_h)
    blit(canvas, canvas_w, ren_panel, panel_w, gutter * 2 + panel_w, gutter + header_h)
    fill_rect(canvas, canvas_w, panel_w + gutter + gutter // 2, gutter, max(2, gutter // 5), canvas_h - gutter * 2, (170, 146, 92))
    write_png_rgb(out, canvas_w, canvas_h, canvas)
    return {
        "comparisonImage": str(out.resolve()),
        "referenceImage": str(reference.resolve()),
        "renderScreenshot": str(render.resolve()),
        "layout": "left=reference,right=render",
        "panelWidth": panel_w,
        "panelHeight": panel_h,
        "note": "Send this image to AI vision for global, layer, and semantic feature scores; this script does not score.",
    }


def parse_pair_arg(value: str) -> dict[str, str]:
    """Parse `role:ref,render` or `role=ref,render`."""
    text = value.strip()
    for sep in (":", "="):
        if sep in text:
            role, _, rest = text.partition(sep)
            break
    else:
        raise ValueError(f"malformed --pair (expected role:ref,render): {value!r}")
    parts = [p.strip() for p in rest.split(",")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"malformed --pair (expected role:ref,render): {value!r}")
    role = role.strip().lower().replace("_", "-").replace(" ", "-") or "primary"
    return {"role": role, "reference": parts[0], "render": parts[1]}


def create_multi_pair_sheet(
    pairs: list[dict[str, str]],
    out: Path,
    width: int,
    height: int,
    gutter: int,
) -> dict:
    """Package N matched view pairs as rows: left=reference, right=render per role.

    Still one sheet for one vision call — preserves token-efficient review.
    """
    if not pairs:
        raise ValueError("at least one --pair is required for multi-view sheets")
    panel_w = width
    panel_h = height
    header_h = 28
    rows = len(pairs)
    canvas_w = panel_w * 2 + gutter * 3
    canvas_h = rows * (panel_h + header_h) + gutter * (rows + 1)
    canvas = [(246, 242, 236)] * (canvas_w * canvas_h)
    packed: list[dict[str, str]] = []
    for index, pair in enumerate(pairs):
        y0 = gutter + index * (panel_h + header_h + gutter)
        fill_rect(canvas, canvas_w, gutter, y0, panel_w, header_h, (40, 45, 48))
        fill_rect(canvas, canvas_w, gutter * 2 + panel_w, y0, panel_w, header_h, (40, 45, 48))
        fill_rect(canvas, canvas_w, gutter, y0 + header_h, panel_w, panel_h, (230, 230, 230))
        fill_rect(canvas, canvas_w, gutter * 2 + panel_w, y0 + header_h, panel_w, panel_h, (230, 230, 230))
        ref_path = Path(pair["reference"]).expanduser().resolve()
        ren_path = Path(pair["render"]).expanduser().resolve()
        ref_w, ref_h, ref_pixels = load_image(ref_path)
        ren_w, ren_h, ren_pixels = load_image(ren_path)
        blit(canvas, canvas_w, resize_cover(ref_w, ref_h, ref_pixels, panel_w, panel_h), panel_w, gutter, y0 + header_h)
        blit(
            canvas,
            canvas_w,
            resize_cover(ren_w, ren_h, ren_pixels, panel_w, panel_h),
            panel_w,
            gutter * 2 + panel_w,
            y0 + header_h,
        )
        fill_rect(
            canvas,
            canvas_w,
            panel_w + gutter + gutter // 2,
            y0,
            max(2, gutter // 5),
            panel_h + header_h,
            (170, 146, 92),
        )
        packed.append(
            {
                "role": pair["role"],
                "referenceImage": str(ref_path),
                "renderScreenshot": str(ren_path),
            }
        )
    write_png_rgb(out, canvas_w, canvas_h, canvas)
    return {
        "comparisonImage": str(out.resolve()),
        "layout": "rows=matched-view-pairs(left=reference,right=render)",
        "pairs": packed,
        "panelWidth": panel_w,
        "panelHeight": panel_h,
        "rowCount": rows,
        "note": (
            "Multi-view turnaround sheet for one AI-vision review call. Score each matched role; "
            "this script does not score."
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, help="Single-pair reference image")
    parser.add_argument("--render", type=Path, help="Single-pair render screenshot")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Matched multi-view pair as role:ref,render (repeatable). Builds a turnaround comparison sheet.",
    )
    parser.add_argument(
        "--turnaround",
        action="store_true",
        help="Alias that requires one or more --pair entries (explicit multi-view mode)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-width", type=int, default=720)
    parser.add_argument("--panel-height", type=int, default=720)
    parser.add_argument("--gutter", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = args.out.expanduser().resolve()
        panel_w = max(128, args.panel_width)
        panel_h = max(128, args.panel_height)
        gutter = max(6, args.gutter)
        if args.pair or args.turnaround:
            if not args.pair:
                raise ValueError("--turnaround requires one or more --pair role:ref,render entries")
            pairs = [parse_pair_arg(item) for item in args.pair]
            payload = create_multi_pair_sheet(pairs, out, panel_w, panel_h, gutter)
        else:
            if not args.reference or not args.render:
                raise ValueError("provide --reference and --render, or one or more --pair role:ref,render")
            payload = create_sheet(
                args.reference.expanduser().resolve(),
                args.render.expanduser().resolve(),
                out,
                panel_w,
                panel_h,
                gutter,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else payload["comparisonImage"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
