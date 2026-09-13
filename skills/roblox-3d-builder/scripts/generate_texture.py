"""
Fetch a texture image from Pollinations.ai's free, keyless text-to-image API.

Standalone Python (not a bpy script) — run it with the system/venv Python, not Blender's
bundled interpreter, since it only needs the standard library:

    python generate_texture.py "seamless tileable stone wall texture, top-down, muted grey" \
        textures/stone_wall.png

Then load the resulting file with `apply_image_texture` from bpy_helpers.py.
"""

import sys
import urllib.parse
import urllib.request


def fetch_texture(prompt, out_path, width=1024, height=1024, seed=None):
    """Download an image for `prompt` to `out_path`. Pass the same `seed` across related
    textures (e.g. everything for one object, or one project's whole style guide) to keep
    their look related to each other, the same way a fixed seed keeps repeated image
    generations visually consistent.

    Ask for "seamless" / "tileable" in the prompt to reduce (not guarantee) visible seams when
    the texture repeats across a surface — inspect the result and regenerate with a tweaked
    prompt or seed if the tiling looks obviously wrong rather than accepting it as-is.
    """
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}"
    if seed is not None:
        url += f"&seed={seed}"
    urllib.request.urlretrieve(url, out_path)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_texture.py <prompt> <out_path> [seed]")
        sys.exit(1)
    prompt_arg = sys.argv[1]
    out_path_arg = sys.argv[2]
    seed_arg = int(sys.argv[3]) if len(sys.argv) > 3 else None
    result = fetch_texture(prompt_arg, out_path_arg, seed=seed_arg)
    print(f"Saved to {result}")
