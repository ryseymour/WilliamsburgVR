# Williamsburg: browser edition

A playable browser version of **WilliamsburgVR** (2018), the Google Cardboard tour of
Colonial Williamsburg. The repo only ever held the compiled Unity WebGL build in
`Build/`, with no project source, so this edition was rebuilt from what that build contains.

Open `web/index.html` from a local web server (for example `python3 -m http.server` in `web/`).

## What came from the original build

Everything in the scene is the original: the terrain heightmap and painted ground, the
55 terrain trees and bushes, every building, fence, cannon, tent, lamp and sign board at
its original position, the chimney smoke and dust, the 13-star flag on the courthouse,
the title card ("Tour of Colonial Williamsburg. Instructions: Tap headset to jump to new
locations"), the photos and quotes printed on the four sign boards, and the Old Guard Fife
and Drum Corps recording that played in the background.

The tour follows the original `playerspawner` script, which cycled the player between four
trigger sites (`Site1` to `Site4`) next to four sign boards:

1. Bruton Parish Church
2. The Courthouse
3. The Magazine (the "Armory" sign)
4. The Peyton Randolph House (the "Residence" sign)

## What's new

- Press **Space** or **Next stop** to jump, which replaces tapping the headset. A short fade
  plays between stops.
- An info card for each stop with the sign's photo and quote. In the original, the Info3
  panel repeated the courthouse text, and the magazine and Randolph House were only on the
  3D boards. Their text and photos are now taken from those boards.
- You can walk freely (W A S D, or the on-screen stick on phones) and drag to look around.
- A progress row of the four stops, a "tour complete" card, and a music toggle.
- The camera stands back from each board so the whole sign is readable. The boards are
  lightly self-lit so their shaded sides stay legible.

## Rebuilding the assets

```
pip install UnityPy pillow numpy
python3 web/tools/export-scene.py        # unpacks Build/, writes web/assets/
npx @gltf-transform/cli quantize web/assets/town.glb web/assets/town.glb
python3 web/tools/pack.py                # writes web/data/*.js (base64, gzip for the town)
```

The exporter bakes every visible mesh to world space and merges it by material. It flips
Unity's left-handed X axis, simplifies the road strips (Blender bezier curves with millions
of tiny faces) on a 0.6 m grid, and skips a stray duplicate courthouse placed 700 m in the
air. Several meshes are empty in the build itself (`Cabin1`, `cabin2`, one `BezierCurve`
road), so they are missing here too.
