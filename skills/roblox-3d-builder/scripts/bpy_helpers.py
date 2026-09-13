"""
Reusable Blender (bpy) helpers for procedurally building Roblox game props.

Copy this file next to your generation scripts (or keep one shared copy per project) and
import from it, instead of re-deriving basic geometry/material code in every script — reusing
the same building blocks is a big part of how generated objects end up looking consistent with
each other.

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
    """Export the whole current scene as a .glb — the easiest format to preview quickly
    (drag into any online glTF viewer, or Blender's own File > Import for a sanity check)."""
    bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB')
