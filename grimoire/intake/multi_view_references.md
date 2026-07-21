# Multi-View / Multi-Angle References

Use multiple angles — separate files **or** one turnaround/contact sheet — to improve
depth inference, proportion locks, hidden-side materials, and projection coverage.

Scripts package and gate; **agent vision** labels panel roles and judges fidelity.

## Why it helps

A single photo cannot observe the back, far side, or true depth. Multi-angle input:

- locks width/depth/height across front + side (artist turnaround workflow)
- replaces mirror-symmetry guesses with observed back/side albedo
- raises PBR confidence (`extract_pbr_evidence.py --multi-view-reference`)
- enables matched review: front ref vs front render, side vs side

## Inputs

### A. Separate files

```bash
python3 forge/stage1_intake/slice_reference_views.py \
  --view front=front.png --view side=side.png --view back=back.png \
  --out reference-views.json

python3 forge/stage2_spec/new_pre_spec_assessment.py "Widget" \
  --reference-views reference-views.json \
  --complexity moderate --out assessment.json
```

Or pass roles directly:

```bash
python3 forge/stage2_spec/new_sculpt_spec.py "Widget" \
  --image front=front.png --image side=side.png --image back=back.png \
  --out object-sculpt-spec.json
```

### B. One image showing multiple angles

Agent vision first: classify the sheet layout (2-up, 3-up, 2×2) and confirm role order.
Then slice with a preset or explicit normalized boxes:

```bash
# equal horizontal panels: front | side | back
python3 forge/stage1_intake/slice_reference_views.py turnaround.png \
  --layout row-3 --out-dir views/ --out reference-views.json --force

# custom boxes (normalized x,y,w,h)
python3 forge/stage1_intake/slice_reference_views.py sheet.png \
  --panels "front:0,0,0.33,1;side:0.33,0,0.34,1;back:0.67,0,0.33,1" \
  --out-dir views/ --out reference-views.json --force
```

Presets: `row-2`, `row-3`, `row-4`, `col-2`, `col-3`, `grid-2x2`.

Do **not** invent panel labels without looking. If unsure, use `--panels` after measuring
regions, or ask the user which angle is which.

## Spec fields

| Field | Role |
|---|---|
| `sourceImage` | Primary/default view path (alias of front/primary). Kept for backward compatibility. |
| `referenceViews[]` | `{ id, role, path, source, imageRegion, confidence, referenceCamera? }` |
| `viewEvidence[]` | Seeded per view so observations trace to a specific angle |
| `qualityTargets.reviewViewpoints` | Render angles to capture; prefer roles that exist in `referenceViews` |

Valid roles: `front`, `side`, `back`, `three-quarter`, `top`, `bottom`, `close-up`, `custom`, `primary`.

## Review

Package **one** sheet per pass (still one vision call):

```bash
# single matched pair (unchanged)
python3 forge/stage4_review/make_comparison_sheet.py \
  --reference views/front.png --render renders/front.png --out cmp.png

# multi-view turnaround sheet
python3 forge/stage4_review/make_comparison_sheet.py --turnaround \
  --pair front:views/front.png,renders/front.png \
  --pair side:views/side.png,renders/side.png \
  --pair back:views/back.png,renders/back.png \
  --out cmp-turnaround.png --json
```

Never judge a front reference against a side render.

## Projection

```bash
python3 forge/stage3_build/bake_projected_texture.py \
  --reference-image views/front.png \
  --delit-image albedo-front.png \
  --view side=views/side.png --view back=views/back.png \
  --mesh-id head --out bake-plan.json
```

When side/back views exist, the descriptor upgrades `unseenRegionStrategy` toward
`observed-multi-view` instead of blind mirror-symmetry.

## Agent checklist

1. Probe each image / confirm sheet readability.
2. Label roles (vision) → slice or `--view` package → write `referenceViews`.
3. Assess + author spec; fill per-view observations in `viewEvidence`.
4. Blockout against front **and** side silhouettes when available.
5. Review with matched pairs or one turnaround comparison sheet.
6. Project with all observed views; only then infer remaining unseen texels.
7. If a needed angle is missing for the fidelity bar, `request-input` — do not fake confidence.
