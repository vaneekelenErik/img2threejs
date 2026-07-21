---
name: img2threejs
description: Turn an object or character reference image into a quality-gated, animation-ready procedural Three.js model built in code. Use for image-to-3D reconstruction, detail-accurate object rebuilds, stylized/likeness-maximized human characters, sculpt specs, multi-angle/turnaround sheets, and staged code generation.
license: MIT
version: 1.2.1
---

# img2threejs — Image to procedural Three.js

This is the Cursor entrypoint for the img2threejs skill.

**Working directory:** always the **repository root** (the folder that contains `forge/`, `grimoire/`, and root `SKILL.md`), not `.cursor/skills/img2threejs/`.

1. Read and follow the canonical skill at repository-root `SKILL.md`.
2. Run every script as `python3 forge/...` from that root.
3. Rubrics and recipes live under `grimoire/`.

## Quick start when the user attaches an image

1. If the image is a **2×2 turnaround** (top-left / top-right / bottom-left / bottom-right), package views first:

   ```bash
   python3 forge/stage1_intake/slice_reference_views.py <sheet.png> \
     --layout grid-2x2 --out-dir views/ --out views.json --force
   ```

   Confirm role labels with vision (default: TL=front, TR=side, BL=back, BR=three-quarter). Override with `--panels` if the order differs. See `grimoire/intake/multi_view_references.md`.

2. Then run the full staged pipeline from root `SKILL.md`:
   probe → pre-spec assessment (`--reference-views views.json`) → detail inventory → sculpt spec → validate `--strict-quality` → pass-gated codegen → matched comparison sheets → `append_review`.

3. Never one-shot a mesh. Never let scripts score visuals — agent vision judges comparison sheets.

## When To Use

User attaches/points to an object or character image (or multi-angle sheet) and wants a procedural Three.js model, sculpt spec, or reconstruction plan.
