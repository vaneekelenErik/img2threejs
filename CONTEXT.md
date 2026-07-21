# CONTEXT.md — img2threejs project memory

## What the project does

img2threejs is an agent skill that rebuilds an object or character from reference imagery as a **code-only**, procedural Three.js model. It is reconstruction-by-code (primitives, shaders, generated geometry), not photogrammetry or downloaded mesh packs. Quality is gated by staged build passes and AI-vision review of comparison sheets.

## Architecture overview

```
Reference image(s) / turnaround sheet
  → stage1 intake (probe, detail inventory, landmarks, camera, de-light, multi-view slice)
  → stage2 spec (pre-spec assessment, ObjectSculptSpec, validate + strict-quality)
  → stage3 build (locked passes, codegen, projection bake descriptor)
  → stage4 review (comparison sheet packaging, append_review gates)
  → agent vision scores the sheet; scripts never score visuals
```

Division of labor: **Python scripts enforce structure and package evidence; the host agent's vision judges fidelity.**

## Folder / file map

| Path | Role |
|---|---|
| `SKILL.md` | Agent entrypoint / loop |
| `README.md` | User-facing overview |
| `ROADMAP.md` / `docs/UPGRADE_PLAN.md` | Version plan + technical design |
| `grimoire/` | Rubrics and how-tos (intake, build, review, character) |
| `grimoire/intake/multi_view_references.md` | Multi-angle / turnaround workflow |
| `forge/stage1_intake/` | Image probe, detail zones, landmarks, camera, de-light, PBR, **slice_reference_views** |
| `forge/stage2_spec/` | Assessment, sculpt spec, validator |
| `forge/stage3_build/` | Pass orchestrator, TS factory generator, projection bake plan |
| `forge/stage4_review/` | Comparison sheets, review history append |
| `forge/_shared/` | `feature_acceptance_policy.py`, `reference_views.py` |
| `forge/tests/test_pipeline.py` | Stdlib integration tests |

## Important logic

- **Spec schema 2.0** (`new_sculpt_spec.py`): `sourceImage` (primary alias), `referenceViews[]` (multi-angle), `viewEvidence`, `referenceCamera`, `componentTree`, materials, `sculptPipeline`, `selfCorrectLoop`, `featureReviewTargets`.
- **Strict quality** (`validate_sculpt_spec.py`): blocks shallow specs before codegen; also validates `referenceViews` when present.
- **Multi-view packaging** (`slice_reference_views.py` + `_shared/reference_views.py`): separate `role=path` files or slice a contact/turnaround sheet (`--layout` / `--panels`) into crops + JSON.
- **Review packaging** (`make_comparison_sheet.py`): single pair or `--turnaround --pair role:ref,render` multi-row sheet (one vision call).
- **Projection plan** (`bake_projected_texture.py`): descriptor-only; with side/back views upgrades unseen strategy toward `observed-multi-view`.

## Key data flows

1. User supplies 1+ images (or one multi-panel sheet).
2. Agent labels roles → `slice_reference_views` / CLI `--image role=path` → `referenceViews`.
3. Assessment + spec seed primary `sourceImage` + per-view evidence.
4. Pass-gated codegen; render at matched viewpoints.
5. Package comparison sheet → agent scores → `append_review` gates `continue`.

## Implementation decisions

- Pure Python 3.10+ stdlib (PNG via `struct`/`zlib`); no pip deps.
- Backward compatible: `sourceImage` remains the primary path; multi-view is additive.
- Agent proposes turnaround panel boxes/roles; scripts do not auto-detect or score.
- One packaged sheet per review pass (token-efficient), even for multi-view grids.

## Conventions

- Run scripts from skill root: `python3 forge/...`.
- View roles: `front`, `side`, `back`, `three-quarter`, `top`, `bottom`, `close-up`, `custom`, `primary`.
- Never let scripts assign visual acceptance scores.
- Prefer matched camera angles for review (front vs front, not front vs side).

## Known issues / limits

- Single image still cannot guarantee hidden-side geometry; multi-view reduces but does not eliminate inference.
- `slice_reference_views` equal-panel presets assume panels fill the sheet without gutters; use `--panels` for irregular layouts.
- Projection bake is a descriptor only — actual GPU projection is a Three.js runtime step.
- Character likeness maximization (v1.3) still planned beyond current multi-view packaging.

## Next steps

- Wire per-view cameras into character likeness demos.
- Optional gutter-aware turnaround presets.
- Empirical token-cost benchmark with multi-view review sheets.
