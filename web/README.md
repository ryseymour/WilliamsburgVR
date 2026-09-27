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

## Remastered version

The tour opens in a remastered version. Press **V**, or use the **2018 / Remastered**
switch in the top bar or on the title card, to flip between it and the faithful 2018 look
at any moment, from the same spot.

- **Materials from the real place.** The brick, weatherboard, shingle, grass and
  floorboard textures in the 2018 build were Ryan's photos of the actual surfaces.
  `tools/make-textures.py` turns each one into a full PBR set (colour, normal, roughness,
  occlusion). The remaster projects them in world space, so brick courses and boards stay
  level and true to scale on every wall. Surfaces without a photo (the sandy
  oyster-shell streets, painted trim, weathered wood, tent canvas, gravestones) are
  generated from tileable noise.
- **Every building, rebuilt.** `tools/build-landmarks.py` models the town in Blender.
  The four landmarks follow the photos on the tour's own sign boards:
  - the Courthouse, with its pediment cantilevered over the steps (no columns), a lunette
    in the pediment, white shutters, twin ridge chimneys and a bell-domed cupola;
  - Bruton Parish Church, with a three-stage brick tower, a white octagonal steeple and a
    shingled spire;
  - the octagonal Magazine inside its wall;
  - the seven-bay, hip-roofed Peyton Randolph House.

  The twenty ordinary houses are rebuilt on their 2018 footprints, facing the same way,
  in the same colours and with chimneys at the same ends. `export-scene.py` records
  those details in `world.json`. Walls have real openings, so the sash windows,
  panelled doors and fanlights sit back in their reveals. Roofs are laid shingle by
  shingle, and the eaves carry modillion and dentil cornices. There are open shutters,
  dormers and corbelled chimney caps.
- **Atmosphere.** A physically based sky with drifting clouds lights the scene through
  an environment map, so glass and metal reflect it. It also adds distance haze, a warm
  late-afternoon sun with sharper shadows that follow you, ambient occlusion, gentle bloom
  and a filmic grade.
- **Life.** The streets are painted into the ground with worn verges. There are
  wind-blown grass tufts, swaying trees, smoke from every chimney, a flock of birds over
  the town and dust motes in the sunlight.
- Phones get a lighter version (less grass, no ambient occlusion).

## Rebuilding the assets

```
pip install UnityPy pillow numpy bpy
python3 web/tools/export-scene.py        # unpacks Build/, writes web/assets/
npx @gltf-transform/cli quantize web/assets/town.glb web/assets/town.glb
python3 web/tools/make-textures.py       # PBR sets for the remaster, web/assets/rm/
python3 web/tools/build-landmarks.py     # Blender (bpy) models of the landmarks and houses
npx @gltf-transform/cli quantize web/assets/landmarks.glb web/assets/landmarks.glb
python3 web/tools/pack.py                # writes web/data/*.js (base64, gzip for the town)
```

The exporter bakes every visible mesh to world space and merges it by material. It flips
Unity's left-handed X axis, simplifies the road strips (Blender bezier curves with millions
of tiny faces) on a 0.6 m grid, and skips a stray duplicate courthouse placed 700 m in the
air. Several meshes are empty in the build itself (`Cabin1`, `cabin2`, one `BezierCurve`
road), so they are missing here too.
