---
name: roblox-3d-builder
description: Build 3D props and models for a Roblox game procedurally in Blender using Python (bpy), guided by a persistent per-project style guide so every generated asset shares the same look. Use this skill whenever the user asks to create, generate, model, design, or build any 3D asset, prop, object, character part, or environment piece for their game (for example "generate a treasure chest", "make me a low-poly pine tree", "build a rusty sword model", "I need a barrel prop") — even if they don't mention Blender, bpy, or "3D" explicitly. This skill writes and runs a Blender script headlessly instead of relying on Roblox Studio's built-in AI generation tools (generate_mesh, generate_procedural_model) or an external text-to-image concept step. It stops at producing a reviewable .blend/.glb file on disk — it does not import anything into Roblox Studio.
---

# Roblox 3D Builder (Blender, procedural)

## What this skill does, and what it deliberately skips

Given a description of an object, this skill writes a Blender Python (`bpy`) script that
constructs the object directly out of primitives (boxes, cylinders, etc.), materials, and
optionally textures, then runs Blender headlessly to produce a `.blend` file and a `.glb`
preview. The user opens the result in Blender themselves to judge it.

Two things are intentionally out of scope, by the user's own choice, and should not be
reintroduced without them asking:

- **No 2D concept image step.** Don't generate a preview image and ask the user to pick one
  before modeling. Go straight from the text description to the 3D build.
- **No Roblox Studio AI tools.** Don't call `generate_mesh` or `generate_procedural_model`
  even if the Roblox Studio MCP server is connected and available. This skill's whole point is
  that Claude designs the geometry itself, procedurally, so it stays deterministic, free, and
  editable.
- **No Roblox import.** Stop once the `.blend`/`.glb` exists. Getting the mesh into Roblox
  Studio (via Toolbox import or the Open Cloud API) is a separate step for later — mention this
  limit if the user asks, don't try to bridge it yourself.

## Prerequisite: Blender must be installed and on PATH

Before the first run in a project, confirm Blender works from the command line:

```
blender --version
```

If that fails, tell the user to install Blender from blender.org and make sure the install
added it to PATH (on Windows, this may require a manual PATH entry pointing at the Blender
install folder, e.g. `C:\Program Files\Blender Foundation\Blender X.X`). Don't proceed to
writing scripts until this works — a failed `blender --background --python ...` call with no
Blender on PATH is a confusing error to debug after the fact.

## Step 1 — Load or create the style guide

Look for `style-guide.md` at the root of the current project. This file is the "memory" that
keeps every generated asset visually consistent across sessions — read it before designing
anything, and treat its palette/proportions/material conventions as binding defaults unless the
user's request explicitly overrides them for this one object.

If it doesn't exist yet, don't invent one silently — ask the user a few short questions to
draft it (see `references/style-guide-template.md` for the fields to cover: overall art style,
color palette, proportion/scale conventions, edge/corner treatment, material defaults). Write
the answers into `style-guide.md` and confirm it with the user before moving on. This is a
one-time cost per project; every later request reuses it.

When the user asks to change the style going forward ("make things a bit more cartoony from
now on"), update `style-guide.md` accordingly rather than only applying the change to the
current object.

## Step 2 — Interpret the request into a build plan

Before writing code, work out in plain terms: what primitive shapes make up this object, their
rough proportions relative to each other, and which parts get which material from the style
guide's palette. For anything with left/right or repeated symmetry (chair legs, tree branches),
plan to build one and mirror/array it rather than writing out each copy by hand — it keeps the
script shorter and easier to adjust later.

## Step 3 — Write the bpy script

Use the helpers in `scripts/bpy_helpers.py` instead of re-deriving basic geometry/material code
each time — copy the file into the project (once) if it isn't already there, and `import` it
from the generation script. Reusing the same helpers across objects is a big part of how style
consistency actually holds up in practice: the same rounding, the same material construction,
applied every time.

A generation script generally follows this shape:

```python
import bpy
import sys, os
sys.path.append(os.path.dirname(__file__))
from bpy_helpers import (
    clear_scene, create_box, create_cylinder,
    make_principled_material, assign_material,
    apply_image_texture, add_procedural_noise,
    export_glb,
)

clear_scene()

wood = make_principled_material("Wood", base_color=(0.36, 0.22, 0.12, 1.0), roughness=0.7)

body = create_box("ChestBody", size=(1.2, 0.7, 0.6), location=(0, 0, 0.3), bevel=0.02)
assign_material(body, wood)
add_procedural_noise(wood, scale=8.0)  # subtle wood grain, procedural, no image needed

lid = create_box("ChestLid", size=(1.2, 0.7, 0.25), location=(0, 0, 0.72), bevel=0.03)
assign_material(lid, wood)

export_glb(bpy.path.abspath("//output/treasure_chest.glb"))
bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath("//output/treasure_chest.blend"))
```

Save the script under the project (e.g. `blender_scripts/<object_name>.py`) so it's a
reusable, versionable record of how the asset was built — re-running it after edits is how
iteration happens, not hand-editing the mesh outside of Blender.

## Step 4 — Materials and textures: both approaches, pick per-surface

The style guide should say which default to lean on, but as a rule of thumb:

- **Procedural (via `bpy_helpers`)** for stylized surfaces where a noise/gradient pattern
  reads fine at a glance — wood grain, rough stone, brushed metal. Free, instant, no external
  call, and trivially tweakable (just change a scale or color value and re-run).
- **Generated image texture** when the surface needs a specific painted/photographic look that
  a shader graph won't convincingly fake (an ornate carved pattern, a specific fabric print).
  Use `scripts/generate_texture.py`, which calls Pollinations.ai's free, keyless image API, to
  fetch a texture image, then apply it with `apply_image_texture`. Ask for a "seamless tileable"
  version of the texture in the prompt to reduce (not eliminate) visible seams — check the
  result and regenerate with a tweaked prompt or seed if the tiling is bad, rather than
  accepting an obviously repeating texture.
  - Pass the same `seed` value across related textures for one object (or one style guide) to
    keep their look consistent with each other, the same way a fixed seed keeps repeated image
    generations visually related.

Either way, once an object's final look is validated, offer to **bake** the material to an
image texture with `bake_material_to_image` from `bpy_helpers.py`. This isn't needed for
viewing the object in Blender, but Roblox's mesh import expects real texture images rather than
a Blender shader node graph — baking now saves redoing this work when the user gets to the
import step later.

## Step 5 — Run it and hand off for review

Execute the script headlessly:

```
blender --background --python blender_scripts/<object_name>.py
```

Report the output paths (`.blend` and `.glb`) to the user and tell them to open the `.blend` in
Blender to inspect it. Don't try to render a preview image yourself as a substitute — the user
said they want to look at the real model, not a picture of one.

## Step 6 — Iterate

Feedback comes back as adjustments ("legs too thick", "less shiny", "warmer wood tone") —
translate these into edits to the *script* (change a size/color/roughness argument, adjust a
helper call), not manual edits to the mesh, so the object stays reproducible and so the change
generalizes if the user asks for a similar object later. Re-run the same `blender --background`
command after each edit.

## Reference files

- `references/style-guide-template.md` — the questions to ask when drafting a new project's
  `style-guide.md`.
- `scripts/bpy_helpers.py` — reusable geometry/material/texture/export functions; read this
  before writing a generation script so you know what's already available.
- `scripts/generate_texture.py` — fetches a texture image from Pollinations.ai given a prompt.
