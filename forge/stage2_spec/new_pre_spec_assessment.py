#!/usr/bin/env python3
"""Create a pre-spec assessment and quality contract skeleton before ObjectSculptSpec authoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from new_sculpt_spec import make_pre_spec_assessment, make_quality_contract

_SHARED = Path(__file__).resolve().parents[1] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from reference_views import (  # noqa: E402
    merge_reference_views,
    parse_view_args,
    primary_image_path,
    roles_present,
)


COMPLEXITY_MINIMUMS = {
    "simple": {
        "macroComponents": 1,
        "mesoComponents": 0,
        "microFeatureGroups": 0,
        "materialLayers": 1,
        "repetitionSystems": 0,
        "reviewViewpoints": 2,
    },
    "moderate": {
        "macroComponents": 2,
        "mesoComponents": 3,
        "microFeatureGroups": 2,
        "materialLayers": 2,
        "repetitionSystems": 0,
        "reviewViewpoints": 3,
    },
    "complex": {
        "macroComponents": 3,
        "mesoComponents": 8,
        "microFeatureGroups": 5,
        "materialLayers": 3,
        "repetitionSystems": 1,
        "reviewViewpoints": 4,
    },
    "ultra-complex": {
        "macroComponents": 5,
        "mesoComponents": 16,
        "microFeatureGroups": 8,
        "materialLayers": 4,
        "repetitionSystems": 2,
        "reviewViewpoints": 5,
    },
}


DETAIL_MINIMUMS = {
    "simple": 3,
    "moderate": 6,
    "complex": 10,
    "ultra-complex": 16,
}


def load_reference_views_file(path: Path | None) -> list[dict]:
    if path is None:
        return []
    data = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("referenceViews"), list):
        return data["referenceViews"]
    if isinstance(data, list):
        return data
    raise ValueError(f"{path} must contain a referenceViews array or be an array of views")


def make_payload(
    target_name: str,
    image: str | None,
    complexity: str,
    views: list[dict] | None = None,
) -> dict:
    assessment = make_pre_spec_assessment(target_name)
    contract = make_quality_contract()
    reference_views = list(views or [])
    primary = primary_image_path(reference_views, image)
    assessment["sourceImage"] = primary
    assessment["referenceViews"] = reference_views
    assessment["complexity"]["tier"] = complexity
    assessment["specDepthDecision"]["requiredDepth"] = complexity
    assessment["detailInventory"]["targetMinDetails"] = DETAIL_MINIMUMS[complexity]
    roles = roles_present(reference_views)
    multi_view = len(reference_views) >= 2
    assessment["specDepthDecision"]["hasMultiViewReferences"] = multi_view
    assessment["specDepthDecision"]["observedViewRoles"] = sorted(roles)
    if multi_view:
        assessment["specDepthDecision"]["needsMultipleReviewViews"] = True
        assessment["specDepthDecision"]["rationale"] = (
            "Multi-angle references are available; require matched review viewpoints and prefer "
            "observed side/back evidence over inferred geometry."
        )
    if complexity in {"complex", "ultra-complex"}:
        assessment["specDepthDecision"]["needsRepetitionSystems"] = True
        assessment["specDepthDecision"]["needsMaterialLocalOverrides"] = True
        assessment["specDepthDecision"]["minimumComponentLevels"] = ["macro", "meso", "micro"]
    elif complexity == "moderate":
        assessment["specDepthDecision"]["minimumComponentLevels"] = ["macro", "meso"]
    contract["qualityBar"] = complexity
    contract["minimumSpecDepth"] = COMPLEXITY_MINIMUMS[complexity]
    if multi_view:
        contract["definitionOfDone"] = list(contract.get("definitionOfDone") or []) + [
            "Matched multi-view reviews (front/side/back as available) confirm proportions and hidden-side materials.",
        ]
    return {
        "targetName": target_name,
        "sourceImage": primary,
        "referenceViews": reference_views,
        "preSpecAssessment": assessment,
        "qualityContract": contract,
        "authoringInstruction": (
            "Fill observed object class, complexity reasoning, featureGroups, visualDeltaChecks, "
            "and unknowns before generating or implementing ObjectSculptSpec. "
            "When referenceViews has multiple roles, author per-view observations and review "
            "against matched camera angles."
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_name", help="Human-readable object name")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Reference image path/URL, or role=path (repeatable for multi-angle sets)",
    )
    parser.add_argument(
        "--view",
        action="append",
        default=[],
        help="Alias for --image role=path (repeatable)",
    )
    parser.add_argument(
        "--reference-views",
        type=Path,
        help="JSON from stage1_intake/slice_reference_views.py (or a referenceViews array)",
    )
    parser.add_argument(
        "--complexity",
        choices=sorted(COMPLEXITY_MINIMUMS),
        default="moderate",
        help="Initial complexity estimate. Refine after visual inspection.",
    )
    parser.add_argument("--out", type=Path, help="Output JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite output file")
    args = parser.parse_args(argv)

    try:
        from_file = load_reference_views_file(args.reference_views)
        from_cli = parse_view_args(list(args.image) + list(args.view))
        views = merge_reference_views(from_file, from_cli)
        # bare --image without role still works as primary when no other views exist
        primary_fallback = None
        if not views and args.image:
            primary_fallback = parse_view_args(args.image)[0]["path"] if args.image else None
        payload = make_payload(args.target_name, primary_fallback, args.complexity, views)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

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
