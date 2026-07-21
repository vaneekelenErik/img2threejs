# CONTEXT.md — img2threejs

## What the project does

img2threejs is an agent skill that rebuilds an object from a reference image as a **code-only** procedural Three.js model. Scripts gate each stage; the agent’s vision scores renders against the reference. Not photogrammetry or mesh downloads.

## Architecture overview

1. **Intake** (`forge/stage1_intake/`) — probe image, detail inventory, optional landmarks/PBR/camera helpers  
2. **Spec** (`forge/stage2_spec/`) — pre-spec assessment, ObjectSculptSpec authoring, validate + `--strict-quality`  
3. **Build** (`forge/stage3_build/`) — locked passes, Three.js factory generation  
4. **Review** (`forge/stage4_review/`) — comparison sheets, append review decisions  
5. **Grimoire** (`grimoire/`) — rubrics, geometry patterns, readiness, self-correction

Pass order: `blockout → structural-pass → form-refinement → material-pass → lighting-pass → interaction-pass → optimization-pass`

## Folder / file map

| Path | Role |
| --- | --- |
| `SKILL.md` | Agent entrypoint / skill contract |
| `forge/` | Pure Python 3.10+ stdlib pipeline CLIs |
| `grimoire/` | Domain docs the agent must follow |
| `assets/` | Demo GIFs / logo for README |
| `docs/` | Token cost, upgrade plan |
| `reconstructions/` | Local per-subject workspaces (image + pipeline outputs) |
| `reconstructions/pearl-smart-ring/` | Scaffold for the pearl smart-ring turnaround rebuild |

## Important logic

- Suitability + quality contract before any code  
- `detailInventory` must map every detail to `localFeatures` / `localOverrides`  
- Generator is pass-gated; reviews need render + comparison sheet + AI-vision scores  
- Runtime hierarchy via `root.userData.sculptRuntime`

## Implementation decisions

- Reconstruction-by-code only (primitives, Shape extrude, tubes, instancing, canvas textures)  
- No pip deps for forge scripts  
- Cursor Cloud cannot accept user image attachments → local Desktop workflow required for image-driven rebuilds  

## Conventions

- Spec schema 2.0 (`ObjectSculptSpec`)  
- Feature review targets: ≤5 critical, ≤3 important per pass  
- Prefer 3D vocabulary from `grimoire/glossary/3d_vocabulary.md`  
- Keep `README.md` and `CONTEXT.md` in sync with setup/workflows  

## Known issues

- Cloud Agent runs do not receive binary image attachments (description-only). Users must clone and run on Cursor Desktop, placing the reference under `reconstructions/<subject>/`.  
- A single view cannot guarantee hidden-side fidelity; multi-view turnarounds (like the smart-ring 2×2) are preferred.

## Next steps

- User: clone branch `cursor/pearl-smart-ring-24b0`, drop `reference.png` into `reconstructions/pearl-smart-ring/`, run [PROMPT.md](reconstructions/pearl-smart-ring/PROMPT.md) in Cursor Desktop.  
- Agent (local): execute full img2threejs pipeline for the pearl smart ring and land factory + reviews in that folder.
