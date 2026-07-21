"""Helpers for multi-angle / multi-view reference packaging.

Scripts package and gate; the agent labels roles and judges fidelity.
Keeps sourceImage as the primary/default view for backward compatibility.
"""

from __future__ import annotations

from typing import Any


VALID_VIEW_ROLES = (
    "front",
    "side",
    "back",
    "three-quarter",
    "top",
    "bottom",
    "close-up",
    "custom",
    "primary",
)

ROLE_ALIASES = {
    "front": "front",
    "frontal": "front",
    "ortho-front": "front",
    "side": "side",
    "left": "side",
    "right": "side",
    "profile": "side",
    "ortho-side": "side",
    "back": "back",
    "rear": "back",
    "ortho-back": "back",
    "three-quarter": "three-quarter",
    "3/4": "three-quarter",
    "threequarter": "three-quarter",
    "top": "top",
    "bottom": "bottom",
    "close-up": "close-up",
    "closeup": "close-up",
    "detail": "close-up",
    "custom": "custom",
    "primary": "primary",
    "main": "primary",
}


def normalize_role(role: str) -> str:
    key = role.strip().lower().replace("_", "-").replace(" ", "-")
    if key not in ROLE_ALIASES:
        raise ValueError(
            f"unknown view role {role!r}; expected one of {', '.join(VALID_VIEW_ROLES)}"
        )
    return ROLE_ALIASES[key]


def parse_view_arg(value: str) -> tuple[str, str]:
    """Parse `role=path` or bare path (role defaults to primary)."""
    text = value.strip()
    if not text:
        raise ValueError("empty --view/--image value")
    if "=" in text:
        role, _, path = text.partition("=")
        role = normalize_role(role)
        path = path.strip()
        if not path:
            raise ValueError(f"view {role!r} is missing a path")
        return role, path
    return "primary", text


def parse_view_args(values: list[str] | None) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for index, raw in enumerate(values or []):
        role, path = parse_view_arg(raw)
        # allow duplicate custom roles with distinct ids; otherwise first wins as canonical role
        view_id = role if role not in seen_roles else f"{role}-{index + 1}"
        seen_roles.add(role)
        views.append(
            {
                "id": view_id,
                "role": role,
                "path": path,
                "source": "separate-file",
                "confidence": 0.5,
                "observations": [],
                "imageRegion": {
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 1.0,
                    "units": "normalized",
                },
                "referenceCamera": None,
            }
        )
    return views


def primary_image_path(views: list[dict[str, Any]], fallback: str | None = None) -> str:
    if not views:
        return fallback or ""
    for preferred in ("primary", "front", "three-quarter"):
        for view in views:
            if view.get("role") == preferred and view.get("path"):
                return str(view["path"])
    return str(views[0].get("path") or fallback or "")


def merge_reference_views(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge by id; incoming overwrites matching ids, preserves order of existing then new."""
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for collection in (existing or [], incoming or []):
        for item in collection:
            if not isinstance(item, dict):
                continue
            view_id = str(item.get("id") or item.get("role") or "").strip()
            if not view_id:
                continue
            if view_id not in by_id:
                order.append(view_id)
            merged = dict(by_id.get(view_id, {}))
            merged.update(item)
            merged["id"] = view_id
            if "role" in merged:
                try:
                    merged["role"] = normalize_role(str(merged["role"]))
                except ValueError:
                    pass
            by_id[view_id] = merged
    return [by_id[view_id] for view_id in order]


def roles_present(views: list[dict[str, Any]] | None) -> set[str]:
    roles: set[str] = set()
    for view in views or []:
        if not isinstance(view, dict):
            continue
        role = view.get("role")
        if isinstance(role, str) and role.strip():
            try:
                roles.add(normalize_role(role))
            except ValueError:
                roles.add(role.strip().lower())
    return roles


def make_view_evidence_from_views(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seed viewEvidence entries so observations can be traced to a specific angle.

    Always keeps a `full-object` entry (primary/front) so starter component evidenceRefs
    remain valid, then adds one entry per reference view.
    """
    primary_path = primary_image_path(views)
    evidence: list[dict[str, Any]] = [
        {
            "id": "full-object",
            "view": "primary",
            "sourceImage": primary_path,
            "imageRegion": {
                "x": 0.0,
                "y": 0.0,
                "width": 1.0,
                "height": 1.0,
                "units": "normalized",
            },
            "observations": [],
            "confidence": 0.55 if views else 0.5,
        }
    ]
    if not views:
        return evidence
    for view in views:
        role = str(view.get("role") or "primary")
        region = view.get("imageRegion") if isinstance(view.get("imageRegion"), dict) else {
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0,
            "units": "normalized",
        }
        evidence.append(
            {
                "id": f"view-{view.get('id', role)}",
                "view": role,
                "sourceViewId": view.get("id"),
                "sourceImage": view.get("path", ""),
                "imageRegion": region,
                "observations": list(view.get("observations") or []),
                "confidence": view.get("confidence", 0.5),
            }
        )
    return evidence
