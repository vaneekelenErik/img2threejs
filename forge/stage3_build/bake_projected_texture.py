#!/usr/bin/env python3
"""Emit a projection/UV-bake descriptor for photo-projected texturing.

This script does not perform GPU projective texturing and it does not
rasterize or bake any pixels. Actual camera-space projection of the
(ideally de-lit) reference image onto the fitted mesh, and the bake of that
projection into the mesh's UV space, is a Three.js runtime operation (a
projective ShaderMaterial, e.g. the `three-projected-material` technique).
What this script produces is the plan: a validated, versioned descriptor
that records which camera, which source image(s), which mesh, and which
projection settings the Three.js generator/agent should use to actually run
that bake, plus the back/side inference strategy for regions the camera
never saw.

When multi-angle references exist, pass --view role=path (and optional
per-view cameras) so observed sides replace mirror/palette inference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from reference_views import normalize_role, parse_view_arg, roles_present  # noqa: E402


VALID_PROJECTION_MODES = ("perspective-camera-projection", "orthographic-front-projection", "triplanar-fallback")
VALID_UNSEEN_STRATEGIES = ("mirror-symmetry", "palette-continue", "request-additional-view", "leave-unprojected")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def load_camera(camera_arg: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    if not camera_arg:
        warnings.append("no --camera reference supplied; projection will use an identity/front camera assumption")
        return None, warnings
    path = Path(camera_arg).expanduser()
    if not path.exists():
        warnings.append(f"--camera path {camera_arg!r} does not exist; recording it as an opaque reference id instead")
        return {"reference": camera_arg}, warnings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"could not parse --camera JSON at {path}: {exc}; recording it as an opaque reference id")
        return {"reference": camera_arg}, warnings
    camera = data.get("referenceCamera", data) if isinstance(data, dict) else None
    if not isinstance(camera, dict):
        warnings.append(f"--camera JSON at {path} did not contain a referenceCamera object")
        return {"reference": camera_arg}, warnings
    return camera, warnings


def load_reference_views_file(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("referenceViews"), list):
        return data["referenceViews"]
    if isinstance(data, list):
        return data
    raise ValueError(f"{path} must contain a referenceViews array or be an array of views")


def build_projection_views(
    reference_image: str,
    delit_image: str | None,
    view_args: list[str],
    views_file: str | None,
    view_cameras: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    views: list[dict[str, Any]] = []

    for item in load_reference_views_file(views_file):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "primary")
        try:
            role = normalize_role(role)
        except ValueError:
            warnings.append(f"keeping non-standard projection view role {role!r}")
        path = item.get("path") or item.get("delit") or ""
        if not path:
            continue
        views.append(
            {
                "role": role,
                "reference": str(Path(str(path)).expanduser()),
                "delit": str(Path(str(item["delit"])).expanduser()) if item.get("delit") else None,
                "camera": item.get("referenceCamera"),
                "confidence": item.get("confidence", 0.5),
            }
        )

    for raw in view_args:
        role, path = parse_view_arg(raw)
        views.append(
            {
                "role": role,
                "reference": str(Path(path).expanduser()),
                "delit": None,
                "camera": None,
                "confidence": 0.55,
            }
        )

    # Always include the primary --reference-image as front/primary if not already present.
    roles = {v["role"] for v in views}
    if "front" not in roles and "primary" not in roles:
        views.insert(
            0,
            {
                "role": "front",
                "reference": str(Path(reference_image).expanduser()),
                "delit": str(Path(delit_image).expanduser()) if delit_image else None,
                "camera": None,
                "confidence": 0.55,
            },
        )
    elif delit_image:
        for view in views:
            if view["role"] in {"front", "primary"} and not view.get("delit"):
                view["delit"] = str(Path(delit_image).expanduser())

    camera_by_role: dict[str, dict[str, Any] | None] = {}
    for raw in view_cameras:
        role, camera_path = parse_view_arg(raw)
        camera, cam_warnings = load_camera(camera_path)
        warnings.extend(cam_warnings)
        camera_by_role[role] = camera
    for view in views:
        if view["role"] in camera_by_role:
            view["camera"] = camera_by_role[view["role"]]

    return views, warnings


def choose_unseen_strategy(
    requested: str,
    projection_views: list[dict[str, Any]],
) -> tuple[str, float, list[str]]:
    notes: list[str] = []
    roles = roles_present(projection_views)
    has_side = "side" in roles
    has_back = "back" in roles
    if has_side and has_back and requested == "mirror-symmetry":
        notes.append(
            "side and back reference views are available; prefer projecting those observed views "
            "instead of mirror-symmetry for unseen regions"
        )
        return "observed-multi-view", 0.75, notes
    if (has_side or has_back) and requested == "request-additional-view":
        notes.append("at least one side/back view exists; downgrading request-additional-view to observed-multi-view")
        return "observed-multi-view", 0.7, notes
    confidence = {
        "mirror-symmetry": 0.45,
        "palette-continue": 0.3,
        "request-additional-view": 0.0,
        "leave-unprojected": 0.0,
        "observed-multi-view": 0.75,
    }.get(requested, 0.3)
    if not has_side and not has_back and requested == "mirror-symmetry":
        notes.append("no side/back referenceViews; mirror-symmetry remains an inference heuristic")
    return requested, confidence, notes


def build_descriptor(args: argparse.Namespace) -> dict[str, Any]:
    camera, camera_warnings = load_camera(args.camera)
    warnings = list(camera_warnings)

    projection_views, view_warnings = build_projection_views(
        args.reference_image,
        args.delit_image,
        list(args.view or []),
        args.reference_views,
        list(args.view_camera or []),
    )
    warnings.extend(view_warnings)

    source_images: dict[str, Any] = {"reference": str(Path(args.reference_image).expanduser())}
    if args.delit_image:
        source_images["delit"] = str(Path(args.delit_image).expanduser())
    else:
        warnings.append(
            "no --delit-image supplied; projecting the raw reference will bake its lighting into the mesh "
            "unless the runtime applies its own de-lighting pass first"
        )
    source_images["views"] = [
        {
            "role": v["role"],
            "reference": v["reference"],
            "delit": v.get("delit"),
            "camera": v.get("camera"),
            "confidence": v.get("confidence", 0.5),
        }
        for v in projection_views
    ]

    unseen_strategy, unseen_confidence, strategy_notes = choose_unseen_strategy(
        args.unseen_strategy,
        projection_views,
    )
    warnings.extend(strategy_notes)

    bake_steps = [
        "load the fitted mesh identified by targetMeshId and its UV layout",
        "for each entry in sourceImages.views, load delit if present else reference as that view's projection texture",
        "construct a projection camera per view from that view's camera block (or the shared camera / identity fallback)",
        f"apply {args.projection_mode} per view, writing only to mesh surfaces that face that view within tolerance",
        "blend overlapping projections by facing-weight; prefer higher-confidence / more frontal samples",
        f"for surfaces still uncovered after all views, apply the '{unseen_strategy}' strategy",
        f"rasterize the resulting multi-view projection into a {args.texture_size}x{args.texture_size} UV-space texture",
        "flag any UV texels that received no projected sample (fully unseen regions) in the bake output metadata",
        "hand the baked texture back to the material pipeline as the projected albedo input",
    ]

    return {
        "projectedTextureBake": {
            "version": "1.1",
            "generator": "stage3_build/bake_projected_texture.py",
            "status": "descriptor-only; no pixels are baked or rasterized by this script",
            "targetMeshId": args.mesh_id,
            "projectionMode": args.projection_mode,
            "textureSize": args.texture_size,
            "camera": camera,
            "sourceImages": source_images,
            "projectionViews": source_images["views"],
            "unseenRegionStrategy": {
                "mode": unseen_strategy,
                "confidence": unseen_confidence,
                "note": (
                    "Regions no reference camera saw (back, occluded folds, underside) are inferred, not observed — "
                    "unless a matching side/back referenceView was supplied."
                ),
            },
            "runtimeApproach": (
                "actual projective texturing and UV bake happen in the Three.js runtime via a projective "
                "ShaderMaterial (the three-projected-material approach) or an equivalent camera-space "
                "projection shader; this descriptor only records the plan for that step. With multiple "
                "views, project each angle then blend by facing weight."
            ),
            "bakeSteps": bake_steps,
            "limitations": [
                "this script performs no image sampling, projection math, or UV rasterization",
                "camera accuracy is inherited from whatever produced the camera block; an unrefined camera will misalign the projection",
                "unseen-region inference is a heuristic guess, not observed geometry or texture",
                "the resulting bake still needs a rendered overlay review against the reference image before being trusted",
            ]
            + warnings,
            "note": (
                "Feed this descriptor to the Three.js generator/agent to run the actual projection and bake, "
                "then re-render and visually compare the baked mesh against matched reference views before "
                "accepting the result as final."
            ),
        }
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference-image", required=True, help="Path to the original (primary/front) reference photo")
    parser.add_argument("--delit-image", help="Path to a de-lit albedo produced by stage1_intake/delight_albedo.py, if available")
    parser.add_argument("--camera", help="Path to a referenceCamera JSON produced by stage1_intake/solve_camera_pose.py")
    parser.add_argument(
        "--view",
        action="append",
        default=[],
        help="Additional projection view as role=path (repeatable), e.g. side=side.png back=back.png",
    )
    parser.add_argument(
        "--view-camera",
        action="append",
        default=[],
        help="Per-view camera JSON as role=path (repeatable)",
    )
    parser.add_argument(
        "--reference-views",
        help="JSON from stage1_intake/slice_reference_views.py (or a referenceViews array)",
    )
    parser.add_argument("--mesh-id", required=True, help="Identifier of the target mesh/node to project onto")
    parser.add_argument(
        "--projection-mode",
        choices=VALID_PROJECTION_MODES,
        default="perspective-camera-projection",
        help="Projection technique the Three.js runtime should use (default perspective-camera-projection)",
    )
    parser.add_argument("--texture-size", type=int, default=1024, help="Target baked texture resolution (square)")
    parser.add_argument(
        "--unseen-strategy",
        choices=VALID_UNSEEN_STRATEGIES,
        default="mirror-symmetry",
        help="How to handle mesh regions outside all reference cameras (default mirror-symmetry; auto-upgrades when side/back views exist)",
    )
    parser.add_argument("--out", type=Path, help="Write the descriptor JSON to this path")
    args = parser.parse_args(argv)

    if args.texture_size <= 0:
        parser.error("--texture-size must be positive")

    try:
        descriptor = build_descriptor(args)
        text = json.dumps(descriptor, indent=2, ensure_ascii=False)
        if args.out:
            out_path = args.out.expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
