# Prompt for Cursor Desktop

1. Place your turnaround at `reconstructions/pearl-smart-ring/reference.png`.
2. Attach that file in chat (or `@`-mention it).
3. Paste:

---

Use the img2threejs skill (`SKILL.md` at the repo root). Rebuild this wearable as a code-only procedural Three.js model.

**Reference:** `reconstructions/pearl-smart-ring/reference.png`  
**Layout:** 2×2 turnaround — TL front, TR side, BL back (sensor + gold contacts), BR three-quarter.

**Subject notes (from the sheet):**
- Continuous elliptical smart-ring / rigid band
- Glossy pearl-white outer shell, thicker at top, tapering toward bottom
- Matte brushed silver/titanium inner lining
- Inner top: black optical sensor window (circular + square photodiodes)
- Four vertical gold pogo charging contacts beside the sensor
- Soft studio lighting on a neutral taupe ground

**Outputs** — keep everything under `reconstructions/pearl-smart-ring/`:
- Slice the turnaround with multi-view packaging first:
  `python3 forge/stage1_intake/slice_reference_views.py reference.png --layout grid-2x2 --out-dir views/ --out views.json`
  (roles: TL=`front`, TR=`side`, BL=`back`, BR=`three-quarter` — adjust if the sheet differs)
- Then run the full staged pipeline with `--reference-views views.json` (probe → assessment → detail inventory → sculpt spec → strict-quality → pass-gated build → matched-view screenshot reviews)
- `assessment.json`, `object-sculpt-spec.json`, `views.json`, `views/`, `src/createPearlSmartRingModel.ts`, `renders/`

Intended use: real-time browser prop / hero product render.

This branch already includes multi-view support (`grimoire/intake/multi_view_references.md`).
