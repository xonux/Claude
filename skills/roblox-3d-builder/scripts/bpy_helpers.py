"""
Reusable Blender (bpy) helpers for procedurally building Roblox game props and characters.

Copy this file next to your generation scripts (or keep one shared copy per project) and
import from it, instead of re-deriving basic geometry/material code in every script — reusing
the same building blocks is a big part of how generated objects end up looking consistent with
each other.

Two families of geometry helpers, pick per-object rather than defaulting to one:

- Primitives (create_box, create_cylinder, create_sphere) + boolean_combine — good for
  hard-surface objects: furniture, containers, weapons, machinery. Distinct flat/angular parts
  that plausibly bolt together.
- skin_mesh_from_edges, create_mesh_from_data, create_bezier_curve, add_subsurf — good for
  organic shapes: creatures, characters, plants, anything that should read as one continuous
  rounded form rather than a collection of parts. Stacking primitives for these tends to
  produce a visibly segmented "pile of shapes" look — reach for these instead.

Everything here is meant to be called from a script run as:
    blender --background --python your_script.py
"""

import bpy


def clear_scene():
    """Remove every object and orphaned mesh data from the current scene.

    Call this first in a generation script so re-running it doesn't pile up duplicate
    objects from the previous run.
    """
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)


def create_box(name, size=(1.0, 1.0, 1.0), location=(0.0, 0.0, 0.0), bevel=0.0, bevel_segments=2):
    """Create a box with the given (x, y, z) dimensions, optionally with beveled edges.

    `size` is the full dimension along each axis (not a half-extent), so size=(1,1,1) gives a
    1x1x1 unit cube — matches how most people think about prop dimensions.
    """
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", 'BEVEL')
        mod.width = bevel
        mod.segments = bevel_segments
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def create_cylinder(name, radius=0.5, depth=1.0, location=(0.0, 0.0, 0.0), vertices=16):
    """Create a cylinder. Lower `vertices` (e.g. 6-8) for a low-poly look."""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=vertices, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    return obj


def create_sphere(name, radius=0.5, location=(0.0, 0.0, 0.0), segments=16, rings=8):
    """Create a UV sphere. Lower segments/rings for a low-poly look."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, location=location, segments=segments, ring_count=rings
    )
    obj = bpy.context.active_object
    obj.name = name
    return obj


def mirror_object(obj, axis='X'):
    """Add a mirror modifier so symmetric parts (legs, arms, branches) only need to be
    modeled once. Apply the modifier afterward if you need the mirrored geometry as real
    separate mesh data (e.g. before further per-side edits)."""
    mod = obj.modifiers.new("Mirror", 'MIRROR')
    mod.use_axis[0] = axis == 'X'
    mod.use_axis[1] = axis == 'Y'
    mod.use_axis[2] = axis == 'Z'
    return mod


def shade_smooth(obj):
    """Set smooth shading on an object. Almost always wanted alongside add_subsurf() —
    without this, a subdivided mesh still displays with visible facets even though the extra
    geometry is there, which defeats the point of subdividing it in the first place."""
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def add_subsurf(obj, levels=2, render_levels=None, apply=False):
    """Add a Subdivision Surface modifier — the single biggest lever for turning a blocky,
    low-poly cage into a smooth, rounded, organic-looking shape. The right way to use this is
    to build a *simple, chunky* base mesh (few vertices, roughly the right proportions) and let
    this modifier do the rounding, rather than trying to fake roundness by stacking lots of
    small primitives — the latter is what produces a "pile of shapes" look instead of a single
    coherent silhouette. Always pair with shade_smooth(obj) so the result actually reads as
    curved.
    """
    mod = obj.modifiers.new("Subdivision", 'SUBSURF')
    mod.levels = levels
    mod.render_levels = render_levels if render_levels is not None else levels
    if apply:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return mod


def boolean_combine(obj_a, obj_b, operation='UNION', apply=True, delete_operand=True):
    """Combine two mesh objects with a real boolean operation, so their geometry actually
    merges or cuts into a single continuous mesh — unlike just placing two objects so they
    visually overlap, which leaves two separate surfaces intersecting each other (visible
    seams, wrong shading, and it reads as "two shapes touching" rather than one form). Use
    UNION to fuse overlapping pieces into one blob (e.g. two overlapping spheres into a single
    rounded body), DIFFERENCE to carve a notch or hole, INTERSECT to keep only the overlap.

    `obj_a` ends up holding the combined result and is what you keep working with afterward.
    `obj_b` is deleted once merged in (pass delete_operand=False to keep it, e.g. if you plan to
    reuse it in another boolean op).
    """
    mod = obj_a.modifiers.new("Boolean", 'BOOLEAN')
    mod.operation = operation
    mod.object = obj_b
    if apply:
        bpy.context.view_layer.objects.active = obj_a
        bpy.ops.object.modifier_apply(modifier=mod.name)
        if delete_operand:
            bpy.data.objects.remove(obj_b, do_unlink=True)
    return obj_a


def create_mesh_from_data(name, verts, faces, location=(0.0, 0.0, 0.0)):
    """Build a completely custom mesh from raw vertex positions and faces — for shapes that
    don't reduce to a primitive, or a boolean combination of primitives (a custom silhouette, a
    hand-authored low-poly head or wing shape). `verts` is a list of (x, y, z) tuples; `faces`
    is a list of index tuples/lists into `verts` (3+ indices per face).

    Reach for this whenever describing a shape as stacked primitives would be more convoluted
    than just placing the vertices you actually want directly — it's the general-purpose
    fallback underneath every other geometry helper here.
    """
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(list(verts), [], [list(f) for f in faces])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def skin_mesh_from_edges(name, points, edges, radii=None, location=(0.0, 0.0, 0.0), subsurf_levels=2):
    """Build an organic, rounded shape from a simple skeleton: a list of `points` (vertex
    positions) connected by `edges` (pairs of indices into `points`), fleshed out into a smooth
    tube/blob mesh by Blender's Skin modifier. Think of it as drawing the "stick figure" of a
    limb, tail, or creature torso and letting Blender generate the volume around it — this is
    almost always a better starting point for an organic character body or limb than manually
    stacking spheres and cylinders, which tends to produce a visibly segmented "snowman" look
    instead of one continuous form.

    `radii` optionally controls skin thickness per point — a list the same length as `points`,
    each entry either a single float (circular cross-section) or an (x, y) pair (elliptical).
    Vary these along a limb to taper it, or make one point much larger than its neighbors for a
    torso/head bulge. A Subdivision Surface modifier is added automatically so the result reads
    as smooth; adjust `subsurf_levels` (or remove the modifier afterward) for a chunkier look.
    """
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(list(points), [list(e) for e in edges], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.collection.objects.link(obj)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_add(type='SKIN')

    if radii is not None:
        skin_layer = obj.data.skin_vertices[0].data
        for i, r in enumerate(radii):
            skin_layer[i].radius = (r, r) if isinstance(r, (int, float)) else tuple(r)

    add_subsurf(obj, levels=subsurf_levels)
    shade_smooth(obj)
    return obj


def create_bezier_curve(name, points, bevel_depth=0.05, bevel_resolution=4, location=(0.0, 0.0, 0.0)):
    """Create a Bezier curve running through `points` (a list of (x, y, z) coordinates, with
    automatic smooth handles) and give it real 3D thickness via `bevel_depth` so it renders as a
    solid tube rather than a flat line. Use this for anything with a flowing, curved silhouette
    that primitives can't capture well — a tail, a horn, a vine, a wing spar.
    """
    curve_data = bpy.data.curves.new(name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = bevel_resolution

    spline = curve_data.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for i, co in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = co
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    obj = bpy.data.objects.new(name, curve_data)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def make_principled_material(name, base_color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, metallic=0.0):
    """Create a standard Principled BSDF material. `base_color` is (r, g, b, a) in 0-1 range —
    convert hex from a style guide with e.g. int('5C', 16) / 255."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def assign_material(obj, mat):
    """Assign (replacing any existing) material to an object."""
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def add_procedural_noise(mat, scale=5.0, color_a=(0.0, 0.0, 0.0, 1.0), color_b=(1.0, 1.0, 1.0, 1.0), affect_roughness=True):
    """Wire a Noise Texture -> Color Ramp into the material's base color (and optionally
    roughness), for a cheap procedural grain/variation — wood, stone, rough metal, etc.
    Tweak `scale` for finer/coarser grain; use a fixed value across related objects in the
    same style guide to keep the grain size visually consistent."""
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs["Scale"].default_value = scale

    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = color_a
    ramp.color_ramp.elements[1].color = color_b

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if affect_roughness:
        links.new(noise.outputs["Fac"], bsdf.inputs["Roughness"])
    return mat


def apply_image_texture(obj, image_path, mat_name=None):
    """Load an image from disk and wire it into the object's material as the base color.
    Creates a new material if the object doesn't have one yet."""
    mat = obj.active_material
    if mat is None:
        mat = make_principled_material(mat_name or f"{obj.name}_mat")
        assign_material(obj, mat)

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    tex_node = nodes.new('ShaderNodeTexImage')
    tex_node.image = bpy.data.images.load(image_path)
    links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def bake_material_to_image(obj, resolution=1024, out_path="baked_texture.png", bake_type='DIFFUSE'):
    """Bake an object's current material (procedural or not) down to a single image texture.

    Not needed just to look at the object in Blender — this exists for later, when exporting
    to Roblox, which needs real texture image files rather than a Blender shader node graph.
    Requires the object to be UV-unwrapped; if it isn't, this adds a basic smart UV project
    first so the bake has somewhere to write to.
    """
    if not obj.data.uv_layers:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.render.engine = 'CYCLES'

    mat = obj.active_material
    img = bpy.data.images.new(f"{obj.name}_bake", width=resolution, height=resolution)
    img_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    img_node.image = img
    mat.node_tree.nodes.active = img_node

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.bake(type=bake_type)

    img.filepath_raw = out_path
    img.file_format = 'PNG'
    img.save()
    return out_path


def export_glb(filepath):
    """Export the whole current scene as a .glb. Not part of the default workflow (the default
    deliverable is the .blend file itself, reviewed by opening it in Blender) — this is only
    for the rare case where a lightweight web/glTF preview is specifically wanted."""
    bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB')


def export_fbx(filepath, selected_only=False):
    """Export the scene (or just the selected objects) as .fbx — the format Roblox Studio's
    mesh import (Toolbox > Import 3D, or drag-and-drop) expects. Only call this when the user
    explicitly asks to export/prepare a model for Roblox — the default deliverable after a
    generation is just the .blend file, not an export.

    Bake any procedural materials to real image textures first with bake_material_to_image —
    Roblox needs actual texture images, not a Blender shader node graph, and fbx export does not
    carry procedural node setups over.
    """
    bpy.ops.export_scene.fbx(filepath=filepath, use_selection=selected_only)
