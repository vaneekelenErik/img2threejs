# Pearl smart ring — local reconstruction

Cursor Cloud agents cannot receive image attachments. Run this rebuild on **Cursor Desktop** with the skill repo open locally.

## Setup (once)

```bash
git clone https://github.com/vaneekelenerik/img2threejs.git
cd img2threejs
git checkout cursor/pearl-smart-ring-24b0
```

Open that folder in Cursor Desktop (Agent mode).

## Drop the reference

Save your 2×2 turnaround into this folder:

```text
reconstructions/pearl-smart-ring/reference.png
```

Layout expected:

| Cell | View |
| --- | --- |
| Top-left | Front |
| Top-right | Side |
| Bottom-left | Back (sensor + contacts) |
| Bottom-right | Three-quarter |

Any common image type works (`png`, `jpg`, `webp`). Keep the filename `reference.png` or update the path in the prompt.

## Run the skill

In Cursor Desktop chat, attach `reference.png` (or `@reconstructions/pearl-smart-ring/reference.png`) and paste:

```text
Use the img2threejs skill (SKILL.md at repo root). Rebuild this as a Three.js model.
The image is a 2×2 turnaround: TL front, TR side, BL back, BR three-quarter.
Write outputs under reconstructions/pearl-smart-ring/ (assessment, sculpt spec, factory, renders, reviews).
```

Or open [PROMPT.md](PROMPT.md) and paste from there.

## Expected outputs

After the pipeline finishes, this folder should contain:

- `assessment.json` — pre-spec assessment + quality contract
- `object-sculpt-spec.json` — full sculpt spec + review history
- `src/createPearlSmartRingModel.ts` — procedural Three.js factory
- `renders/` — pass screenshots and comparison sheets

## Preview tip

Pair the generated factory with a minimal Vite + Three.js page, or drop it into [img2threejs-showcase](https://github.com/hoainho/img2threejs-showcase) as a new demo.
