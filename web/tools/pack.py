#!/usr/bin/env python3
"""Pack web/assets into base64 ES modules so the tour runs as one page with no fetches
(the claude.ai artifact sandbox blocks fetch() of most binary types).
Run after export-scene.py and `npx @gltf-transform/cli quantize web/assets/town.glb web/assets/town.glb`."""
import base64, gzip, json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, 'assets'); D = os.path.join(ROOT, 'data'); os.makedirs(D, exist_ok=True)
b64 = lambda f: base64.b64encode(open(os.path.join(A, f), 'rb').read()).decode()
# gzip the quantized GLB; the page inflates it with the browser's DecompressionStream
town = gzip.compress(open(os.path.join(A, 'town.glb'), 'rb').read(), 9, mtime=0)
open(os.path.join(D, 'town.js'), 'w').write('export default "' + base64.b64encode(town).decode() + '";\n')
open(os.path.join(D, 'music.js'), 'w').write('export default "data:audio/mp4;base64,' + b64('fife-raw.m4a') + '";\n')
art = {}
for f in sorted(os.listdir(A)):
    ext = f.rsplit('.', 1)[-1]
    if ext in ('png', 'jpg'):
        art[f.rsplit('.', 1)[0]] = f'data:image/{"jpeg" if ext == "jpg" else "png"};base64,' + b64(f)
world = json.load(open(os.path.join(A, 'world.json')))
with open(os.path.join(D, 'art.js'), 'w') as fh:
    fh.write('export const WORLD = ' + json.dumps(world, separators=(',', ':')) + ';\n')
    fh.write('export const ART = ' + json.dumps(art, separators=(',', ':')) + ';\n')
for f in os.listdir(D): print(f, os.path.getsize(os.path.join(D, f)) // 1024, 'KB')
