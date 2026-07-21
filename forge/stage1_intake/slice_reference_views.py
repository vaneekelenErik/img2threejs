#!/usr/bin/env python3
"""Slice a multi-angle / turnaround reference sheet into named referenceViews.

Accepts either:
  - a contact/turnaround sheet (one image with multiple angles) plus panel layout, or
  - already-separate files via --view role=path (pass-through packaging).

The agent proposes layout and role labels; this script only crops and packages.
It does not classify angles or score visuals.
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
from typing import Any

# Allow running as `python3 forge/stage1_intake/slice_reference_views.py` from skill root.
_SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from reference_views import (  # noqa: E402
    VALID_VIEW_ROLES,
    merge_reference_views,
    normalize_role,
    parse_view_args,
    primary_image_path,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

LAYOUT_PRESETS = {
    "row-2": ["front", "side"],
    "row-3": ["front", "side", "back"],
    "row-4": ["front", "three-quarter", "side", "back"],
    "col-2": ["front", "side"],
    "col-3": ["front", "side", "back"],
    "grid-2x2": ["front", "side", "back", "three-quarter"],
}


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


def composite_over_white(pixel: tuple[int, int, int, int]) -> tuple[int, int, int]:
    red, green, blue, alpha = pixel
    mix = alpha / 255.0
    return (
        round(red * mix + 255 * (1 - mix)),
        round(green * mix + 255 * (1 - mix)),
        round(blue * mix + 255 * (1 - mix)),
    )


def crop_region(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
    region: dict[str, float],
) -> tuple[int, int, list[tuple[int, int, int]]]:
    x0 = max(0, min(width - 1, int(round(region["x"] * width))))
    y0 = max(0, min(height - 1, int(round(region["y"] * height))))
    x1 = max(x0 + 1, min(width, int(round((region["x"] + region["width"]) * width))))
    y1 = max(y0 + 1, min(height, int(round((region["y"] + region["height"]) * height))))
    crop_w = x1 - x0
    crop_h = y1 - y0
    cropped: list[tuple[int, int, int]] = []
    for y in range(y0, y1):
        row = y * width
        for x in range(x0, x1):
            cropped.append(composite_over_white(pixels[row + x]))
    return crop_w, crop_h, cropped


def parse_panels(spec: str) -> list[dict[str, Any]]:
    """Parse `role:x,y,w,h;role:x,y,w,h` normalized panel boxes."""
    panels: list[dict[str, Any]] = []
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        name, sep, coords = part.partition(":")
        if not sep:
            raise ValueError(f"malformed --panels entry (expected role:x,y,w,h): {part!r}")
        values = [float(v) for v in coords.split(",")]
        if len(values) != 4:
            raise ValueError(f"malformed --panels entry (expected 4 normalized values): {part!r}")
        x, y, w, h = values
        if w <= 0 or h <= 0:
            raise ValueError(f"panel {name!r} width/height must be positive")
        role = normalize_role(name)
        panels.append(
            {
                "id": role if role not in {p["id"] for p in panels} else f"{role}-{len(panels) + 1}",
                "role": role,
                "region": {"x": x, "y": y, "width": w, "height": h, "units": "normalized"},
            }
        )
    if not panels:
        raise ValueError("--panels produced no panels")
    return panels


def panels_from_layout(layout: str) -> list[dict[str, Any]]:
    if layout not in LAYOUT_PRESETS:
        raise ValueError(f"unknown --layout {layout!r}; choose from {', '.join(sorted(LAYOUT_PRESETS))}")
    roles = LAYOUT_PRESETS[layout]
    panels: list[dict[str, Any]] = []
    if layout.startswith("row-"):
        n = len(roles)
        step = 1.0 / n
        for index, role in enumerate(roles):
            panels.append(
                {
                    "id": role,
                    "role": role,
                    "region": {
                        "x": round(index * step, 6),
                        "y": 0.0,
                        "width": round(step, 6),
                        "height": 1.0,
                        "units": "normalized",
                    },
                }
            )
    elif layout.startswith("col-"):
        n = len(roles)
        step = 1.0 / n
        for index, role in enumerate(roles):
            panels.append(
                {
                    "id": role,
                    "role": role,
                    "region": {
                        "x": 0.0,
                        "y": round(index * step, 6),
                        "width": 1.0,
                        "height": round(step, 6),
                        "units": "normalized",
                    },
                }
            )
    else:  # grid-2x2
        coords = [
            (0.0, 0.0),
            (0.5, 0.0),
            (0.0, 0.5),
            (0.5, 0.5),
        ]
        for (x, y), role in zip(coords, roles):
            panels.append(
                {
                    "id": role,
                    "role": role,
                    "region": {
                        "x": x,
                        "y": y,
                        "width": 0.5,
                        "height": 0.5,
                        "units": "normalized",
                    },
                }
            )
    return panels


def slice_sheet(
    image: Path,
    panels: list[dict[str, Any]],
    out_dir: Path,
) -> list[dict[str, Any]]:
    width, height, pixels = load_image(image)
    out_dir.mkdir(parents=True, exist_ok=True)
    views: list[dict[str, Any]] = []
    for panel in panels:
        role = panel["role"]
        view_id = panel["id"]
        crop_w, crop_h, crop_pixels = crop_region(width, height, pixels, panel["region"])
        crop_path = out_dir / f"{view_id}.png"
        write_png_rgb(crop_path, crop_w, crop_h, crop_pixels)
        views.append(
            {
                "id": view_id,
                "role": role,
                "path": str(crop_path.resolve()),
                "source": "turnaround-sheet",
                "sourceSheet": str(image.resolve()),
                "confidence": 0.55,
                "observations": [],
                "imageRegion": panel["region"],
                "referenceCamera": None,
                "note": (
                    "Cropped from a multi-angle sheet. Confirm the role label with agent vision "
                    "before relying on it for silhouette or projection."
                ),
            }
        )
    return views


def package_separate_views(view_args: list[str]) -> list[dict[str, Any]]:
    views = parse_view_args(view_args)
    for view in views:
        path = Path(str(view["path"])).expanduser()
        view["path"] = str(path.resolve()) if path.exists() else str(path)
        view["source"] = "separate-file"
    return views


def build_payload(
    views: list[dict[str, Any]],
    sheet: str | None,
    layout: str | None,
) -> dict[str, Any]:
    roles = sorted({str(v.get("role")) for v in views if v.get("role")})
    return {
        "referenceViews": views,
        "sourceImage": primary_image_path(views),
        "sourceSheet": sheet or "",
        "layout": layout or ("separate-files" if not sheet else "custom-panels"),
        "rolesPresent": roles,
        "coverage": {
            "hasFront": "front" in roles or "primary" in roles,
            "hasSide": "side" in roles,
            "hasBack": "back" in roles,
            "viewCount": len(views),
        },
        "authoringInstruction": (
            "Confirm each role label with agent vision. Copy referenceViews into the assessment/spec. "
            "Use matched view pairs when reviewing (front ref vs front render). Prefer side/back "
            "projection over mirror-symmetry when those roles exist. "
            f"Valid roles: {', '.join(VALID_VIEW_ROLES)}."
        ),
        "note": (
            "Multi-angle references improve depth inference, hidden-side materials, and proportion "
            "locks. This script only packages crops; it does not score or auto-detect panels."
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "sheet",
        nargs="?",
        type=Path,
        help="Optional turnaround / contact sheet image to slice",
    )
    parser.add_argument(
        "--layout",
        choices=sorted(LAYOUT_PRESETS),
        help="Preset equal-panel layout for the sheet (row-2, row-3, row-4, col-2, col-3, grid-2x2)",
    )
    parser.add_argument(
        "--panels",
        help="Custom normalized panels: role:x,y,w,h;role:x,y,w,h (overrides --layout roles/boxes)",
    )
    parser.add_argument(
        "--view",
        action="append",
        default=[],
        help="Separate reference file as role=path (repeatable). Can be used alone or merged with sheet crops.",
    )
    parser.add_argument("--out-dir", type=Path, help="Directory for cropped panel PNGs (required with a sheet)")
    parser.add_argument("--out", type=Path, help="Write referenceViews JSON payload here")
    parser.add_argument("--force", action="store_true", help="Overwrite --out if it exists")
    args = parser.parse_args(argv)

    views: list[dict[str, Any]] = []
    sheet_path: str | None = None
    layout_label: str | None = None

    if args.sheet:
        sheet = args.sheet.expanduser().resolve()
        if not sheet.exists():
            parser.error(f"sheet not found: {sheet}")
        if not args.layout and not args.panels:
            parser.error("slicing a sheet requires --layout or --panels")
        if not args.out_dir:
            parser.error("slicing a sheet requires --out-dir for cropped panels")
        panels = parse_panels(args.panels) if args.panels else panels_from_layout(args.layout)
        views = slice_sheet(sheet, panels, args.out_dir.expanduser().resolve())
        sheet_path = str(sheet)
        layout_label = "custom-panels" if args.panels else args.layout

    if args.view:
        separate = package_separate_views(args.view)
        views = merge_reference_views(views, separate)
        if not layout_label:
            layout_label = "separate-files"

    if not views:
        parser.error("provide a sheet (+ --layout/--panels) and/or one or more --view role=path")

    payload = build_payload(views, sheet_path, layout_label)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        output = args.out.expanduser().resolve()
        if output.exists() and not args.force:
            parser.error(f"{output} already exists; use --force to overwrite")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(output)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
