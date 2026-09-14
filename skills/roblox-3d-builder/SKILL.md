---
name: roblox-3d-builder
description: Build 3D props and characters for a Roblox game procedurally in Blender using Python (bpy), guided by a persistent per-project style guide so every generated asset shares the same look. Use this skill whenever the user asks to create, generate, model, design, or build any 3D asset, prop, object, character, creature, or environment piece for their game (for example "generate a treasure chest", "make me a low-poly pine tree", "build a rusty sword model", "generate a fire dragon") — even if they don't mention Blender, bpy, or "3D" explicitly. Delivers a single joined mesh (not several separate floating pieces), a basic armature for characters/creatures so they're animation-ready, and a self-rendered preview Claude looks at and critiques before handing off — quality over speed is the explicit priority here, so take the time a clean result needs. Writes and runs a Blender script headlessly instead of relying on Roblox Studio's built-in AI generation tools (generate_mesh, generate_procedural_model) or an external text-to-image concept step. Stops at producing a reviewable .blend file on disk — it does not import anything into Roblox Studio.
---

# Roblox 3D Builder (Blender, procedural)

## What this skill does, and what it deliberately skips

Given a description of an object, this skill writes a Blender Python (`bpy`) script that
constructs it procedurally, joins it into a single mesh, rigs it with a basic armature if it's
a character/creature, renders a quick preview and looks at that render before deciding the
result is worth showing, then saves a `.blend` file. The user opens the result in Blender
themselves for the final say, but the goal is for what they open to already look right, not to
outsource the judgment call entirely to them.

Take the time this needs. The user has explicitly said a slower, more deliberate generation is
worth it in exchange for a clean, detailed result — don't rush to a first-pass script and call
it done. Build carefully, render, actually look at the render, and fix what's visibly wrong
before presenting anything.

Three things are intentionally out of scope, by the user's own choice, and should not be
reintroduced without them asking:

- **No 2D concept image step.** Don't generate a preview image and ask the user to pick one
  before modeling. Go straight from the text description to the 3D build.
- **No Roblox Studio AI tools.** Don't call `generate_mesh` or `generate_procedural_model`
  even if the Roblox Studio MCP server is connected and available. This skill's whole point is
  that Claude designs the geometry itself, procedurally, so it stays deterministic, free, and
  editable.
- **No Roblox import.** Stop once the `.blend` exists. Getting the mesh into Roblox Studio (via
  Toolbox import or the Open Cloud API) is a separate step for later — mention this limit if the
  user asks, don't try to bridge it yourself.

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

Before writing code, decide which of two families of technique fits the object — this is the
single biggest factor in whether the result looks coherent or like a pile of shapes glued
together, so don't skip it:

- **Hard-surface** (furniture, containers, weapons, machinery, architecture): the object is
  genuinely made of distinct flat/angular parts that plausibly bolt or hinge together. Build it
  from `create_box`/`create_cylinder`/`create_sphere`, combined with `boolean_combine` where
  parts should read as one continuous piece of material (e.g. a handle actually fused into a
  lid) rather than just touching.
- **Organic** (creatures, characters, plants, anything that should read as one continuous
  rounded form): do **not** default to stacking primitives — a body built from a sphere-head +
  cylinder-limbs + sphere-hands reads as a snowman, not a creature, because each part is
  visibly its own separate blob with a seam where it meets the next one. Instead, lean on
  `skin_mesh_from_edges` (draw the "stick figure" skeleton, let Blender flesh it out into one
  continuous skin) and `add_subsurf` + `shade_smooth` (round off a simple blocky cage into a
  smooth form), with `create_bezier_curve` for flowing bits like tails/horns/vines, and
  `boolean_combine`/`create_mesh_from_data` for anything neither of those covers.

Work out in plain terms: for hard-surface, what primitive shapes make up the object and their
proportions; for organic, what the skeleton/silhouette looks like (which points, connected how,
tapering where, and — for a character/creature — roughly where the joints will need to be for
Step 4's armature, so the two line up). For anything with left/right or repeated symmetry
(chair legs, tree branches, a creature's four limbs), plan to build one and `mirror_object` it
rather than writing out each copy by hand.

## Step 3 — Build each piece with its material, then join into one Part

Build the object as however many logical pieces make sense (head, body, wings, tail, handle,
lid...), assigning each piece its material **as you create it** — via `make_principled_material`
+ `assign_material`, per the palette in the style guide. Use the helpers in
`scripts/bpy_helpers.py` throughout instead of re-deriving geometry/material code each time —
copy the file into the project (once) if it isn't already there, and `import` it from the
generation script.

Once every piece looks right individually, call `join_objects` to merge them into a **single
mesh object** — the deliverable is one continuous Part, not several separate objects merely
sitting next to each other (Roblox, and Blender itself, both still treat those as unrelated
pieces rather than one asset). Joining preserves which faces came from which original piece as
separate material slots on the result, so a single joined dragon can still show red scales on
the body and pale yellow on the wing membrane — that's *why* materials must be assigned before
joining, not after: there's no "which piece was this face part of" information left afterward.

A curve object (from `create_bezier_curve`) can't be joined directly — convert it to a mesh
first with `convert_curve_to_mesh`.

A hard-surface generation script generally follows this shape:

```python
import bpy
import sys, os
sys.path.append(os.path.dirname(__file__))
from bpy_helpers import (
    clear_scene, create_box, create_cylinder,
    make_principled_material, assign_material,
    add_procedural_noise, join_objects,
    render_preview,
)

clear_scene()

wood = make_principled_material("Wood", base_color=(0.36, 0.22, 0.12, 1.0), roughness=0.7)
add_procedural_noise(wood, scale=8.0)  # subtle wood grain, procedural, no image needed

body = create_box("ChestBody", size=(1.2, 0.7, 0.6), location=(0, 0, 0.3), bevel=0.02)
assign_material(body, wood)

lid = create_box("ChestLid", size=(1.2, 0.7, 0.25), location=(0, 0, 0.72), bevel=0.03)
assign_material(lid, wood)

chest = join_objects("TreasureChest", [body, lid])

render_preview(bpy.path.abspath("//output/treasure_chest_preview.png"))
bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath("//output/treasure_chest.blend"))
```

An organic character adds an armature (Step 4) between the join and the render/save — see that
section for the full example continuing from a joined dragon mesh.

Save the script under the project (e.g. `blender_scripts/<object_name>.py`) so it's a
reusable, versionable record of how the asset was built — re-running it after edits is how
iteration happens, not hand-editing the mesh outside of Blender.

## Step 4 — Rig characters/creatures with a basic armature

Any character or creature — not static props like a chest or barrel — should end up with a
simple armature (skeleton) so it's animation-ready later, even though this skill doesn't do the
animating itself. Build the armature's bones along the same joint positions you used for
`skin_mesh_from_edges` in Step 2/3, so the rig actually lines up with the mesh it will move.

```python
from bpy_helpers import create_armature, bind_mesh_to_armature

# Same joint positions as the skin_mesh_from_edges skeleton used to build the body.
bones = [
    ("Spine", (0, 0, 0.7), (0, 0, 1.1), None),
    ("Neck",  (0, 0, 1.1), (0, 0, 1.4), "Spine"),
    ("Tail",  (0, -0.6, 0.5), (0, -1.4, 0.15), "Spine"),
]
armature = create_armature("DragonRig", bones)
bind_mesh_to_armature(dragon_mesh, armature)  # parents with automatic weights
```

This gives a usable starting rig (bone chain + automatic weight painting) — real animation
setup (IK, custom controls, hand-painted weights) is out of scope, mention that if asked rather
than attempting it.

## Step 5 — Materials and textures: both approaches, pick per-piece

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

Each piece keeps its own material slot through the Step 3 join, so per-region coloring (scales
vs. wing membrane vs. horns) still works on the single final mesh — assign per-piece as
described in Step 3, this step is about *what* each material should look like, not how many
objects to build.

Once an object's final look is validated, offer to **bake** each material to an image texture
with `bake_material_to_image` from `bpy_helpers.py`. This isn't needed for viewing the object in
Blender, but Roblox's mesh import expects real texture images rather than a Blender shader node
graph — baking now saves redoing this work when the user gets to the import step later.

## Step 6 — Render, look at it yourself, and fix what's wrong before showing the user

Execute the script headlessly:

```
blender --background --python blender_scripts/<object_name>.py
```

The script's last steps should be `render_preview(...)` (writes a PNG) then
`bpy.ops.wm.save_as_mainfile(...)` (writes the `.blend`) — in that order, so a preview exists
even if you stop to fix something before finalizing. Use your Read tool to actually look at the
rendered PNG once it exists. This is the whole point of the render: catching what reading the
code can't — floating disconnected pieces, wildly wrong proportions, a hole where two pieces
should have joined, a material that came out looking nothing like intended.

If something is visibly wrong, fix the script and re-run rather than presenting a flawed
result and hoping the user doesn't notice or will do the fixing themselves. This is the
"take the time" part — one extra render-and-check cycle (or several) is exactly the tradeoff
the user asked for.

Once the render actually looks right, report the `.blend` path to the user and tell them to
open it in Blender for the final look — the render was for your own check, not a replacement
for them seeing the real model.

## Step 7 — Iterate

Feedback comes back as adjustments ("legs too thick", "less shiny", "warmer wood tone") —
translate these into edits to the *script* (change a size/color/roughness argument, adjust a
helper call), not manual edits to the mesh, so the object stays reproducible and so the change
generalizes if the user asks for a similar object later. Re-run the same `blender --background`
command after each edit, and re-check the render yourself again before reporting back — the
self-check from Step 6 applies to every iteration, not just the first pass.

## Step 8 — Exporting for Roblox (only when asked)

The `.blend` stays the working file across every iteration above — don't export anything until
the user explicitly says the model is ready and asks for it to go toward Roblox. At that point:

1. If any material is still procedural (noise/color-ramp nodes rather than an image), bake it
   to a real texture image with `bake_material_to_image` first — Roblox's importer doesn't
   understand Blender shader graphs, only image textures.
2. Export with `export_fbx(filepath)` from `bpy_helpers.py` — `.fbx` is the format Roblox
   Studio's mesh import (Toolbox > Import 3D, or drag-and-drop) expects, not `.glb`. An armature
   (Step 4) and its weights export along with the mesh in `.fbx`, so a rigged character carries
   its rig into the export too.
3. Tell the user where the `.fbx` landed and that importing it into Studio itself is a manual
   step on their end (see the project's Roblox Studio MCP setup for anything further inside
   Studio — that's a separate concern from this skill).

## Reference files

- `references/style-guide-template.md` — the questions to ask when drafting a new project's
  `style-guide.md`.
- `scripts/bpy_helpers.py` — reusable geometry/material/rigging/render/export functions,
  covering hard-surface (primitives, boolean), organic (skin, subsurf, curves, custom mesh),
  joining, armatures, and preview rendering; read this before writing a generation script so you
  know what's already available, and re-read it if a first attempt at an organic shape comes
  out looking like disconnected parts rather than one form — it means the wrong family of
  helper was used, or the join step was skipped.
- `scripts/generate_texture.py` — fetches a texture image from Pollinations.ai given a prompt.
