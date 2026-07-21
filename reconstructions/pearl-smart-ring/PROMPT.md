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
- Run the full staged pipeline (probe → assessment → detail inventory → sculpt spec → strict-quality → pass-gated build → screenshot reviews)
- `assessment.json`, `object-sculpt-spec.json`, `src/createPearlSmartRingModel.ts`, `renders/`

Intended use: real-time browser prop / hero product render.
