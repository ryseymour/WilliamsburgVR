#!/usr/bin/env python3
"""Rebuild the Williamsburg scene for the browser from the 2018 WebGL build.

The repo has no Unity source, only Build/. This unpacks
Build/WilliamsburgWebGL.data.unityweb, reads the one scene (level0) with UnityPy,
and writes:
  web/assets/town.glb   every visible mesh, baked to world space and merged per
                        material, plus the three terrain tree prototypes
  web/assets/world.json terrain size, tree instances, sites, signs, lamps, smoke
  web/assets/*.jpg|png  terrain heightmap/splat, layer textures, title and panel art
Usage: python3 web/tools/export-scene.py   (needs: pip install UnityPy pillow numpy)
"""
import gzip, io, json, os, struct, sys, tempfile
import numpy as np
import UnityPy
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'web', 'assets')
os.makedirs(OUT, exist_ok=True)

# --- unpack the UnityWebData container ------------------------------------
raw = gzip.open(os.path.join(ROOT, 'Build', 'WilliamsburgWebGL.data.unityweb')).read()
assert raw[:16] == b'UnityWebData1.0\x00'
hdr = struct.unpack('<I', raw[16:20])[0]
p, files = 20, {}
while p < hdr:
    off, sz, nl = struct.unpack('<III', raw[p:p + 12]); p += 12
    files[raw[p:p + nl].decode()] = raw[off:off + sz]; p += nl
tmp = tempfile.mkdtemp()
for n in ('data.unity3d', 'sharedassets0.resource'):
    open(os.path.join(tmp, n), 'wb').write(files[n])
open(os.path.join(tmp, 'unity default resources'), 'wb').write(files['Resources/unity_default_resources'])
env = UnityPy.load(os.path.join(tmp, 'data.unity3d'), os.path.join(tmp, 'unity default resources'))
bundle = next(f for f in env.files.values() if hasattr(f, 'files') and 'level0' in f.files)
LVL = bundle.files['level0']; SA = bundle.files['sharedassets0.assets']
GGM = bundle.files['globalgamemanagers.assets']
scripts = {pid: o.read().m_ClassName for pid, o in GGM.objects.items() if o.type.name == 'MonoScript'}

# --- transforms ------------------------------------------------------------
def trs(t):
    p, r, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
    x, y, z, w = r.x, r.y, r.z, r.w
    R = np.array([[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
                  [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
                  [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)]])
    M = np.eye(4); M[:3, :3] = R * np.array([s.x, s.y, s.z]); M[:3, 3] = [p.x, p.y, p.z]
    return M

tr = {pid: o.read() for pid, o in LVL.objects.items() if o.type.name in ('Transform', 'RectTransform')}
parent = {pid: t.m_Father.path_id for pid, t in tr.items()}
go_tr = {t.m_GameObject.path_id: pid for pid, t in tr.items()}
_world = {}
def world(pid):
    if pid not in _world:
        M = trs(tr[pid]); f = parent[pid]
        _world[pid] = world(f) @ M if f else M
    return _world[pid]
def active(pid):
    while pid:
        if not tr[pid].m_GameObject.read().m_IsActive: return False
        pid = parent[pid]
    return True
FLIP = np.diag([-1.0, 1, 1, 1])  # Unity is left-handed; glTF/three are right-handed

def comps(go):
    for c in go.m_Component:
        pp = c.component if hasattr(c, 'component') else c
        o = LVL.objects.get(pp.path_id) if pp.m_FileID == 0 else None
        if o: yield o

# --- mesh reading ----------------------------------------------------------
def mesh_data(mesh):
    from UnityPy.helpers.MeshHelper import MeshHandler
    h = MeshHandler(mesh); h.process()
    if not h.m_Vertices or len(h.m_Vertices) < 3: return None
    V = np.array(h.m_Vertices, dtype=np.float64).reshape(-1, 3)
    N = np.array(h.m_Normals, dtype=np.float64).reshape(-1, 3) if h.m_Normals else None
    UV = np.array(h.m_UV0, dtype=np.float64).reshape(-1, 2) if h.m_UV0 else np.zeros((len(V), 2))
    subs = h.get_triangles()  # list per submesh of [(a,b,c), ...]
    return V, N, UV, [np.array(s, dtype=np.int64).reshape(-1, 3) for s in subs]

# --- material translation --------------------------------------------------
tex_cache, textures, images, materials, mat_index = {}, [], [], [], {}
def tex_image(pptr, max_size=1024, alpha=False):
    t = pptr.read(); key = (pptr.path_id, max_size, alpha)
    if key in tex_cache: return tex_cache[key]
    im = t.image
    im.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    if alpha: im.convert('RGBA').save(buf, 'PNG', optimize=True); mime = 'image/png'
    else: im.convert('RGB').save(buf, 'JPEG', quality=82); mime = 'image/jpeg'
    images.append((buf.getvalue(), mime)); textures.append(len(images) - 1)
    tex_cache[key] = len(textures) - 1
    return tex_cache[key]

def material(pptr):
    key = (pptr.m_FileID, pptr.path_id)
    if key in mat_index: return mat_index[key]
    m = pptr.read()
    shader = m.m_Shader.read().m_ParsedForm.m_Name if m.m_Shader.path_id else ''
    props = m.m_SavedProperties
    col = dict(props.m_Colors).get('_Color'); floats = dict(props.m_Floats)
    texenv = dict(props.m_TexEnvs).get('_MainTex')
    mode = floats.get('_Mode', 0)
    tree = shader.startswith('Nature/SpeedTree')
    g = {'name': m.m_Name, 'pbrMetallicRoughness': {
        'metallicFactor': float(min(floats.get('_Metallic', 0), .3)),
        'roughnessFactor': 1.0 if 'Legacy' in shader or tree else float(1 - floats.get('_Glossiness', .5) * .6)}}
    c = [col.r, col.g, col.b, col.a] if col else [1, 1, 1, 1]
    blend = mode >= 2 or 'glass' in m.m_Name
    if not blend: c[3] = 1
    if blend: g['alphaMode'] = 'BLEND'; c[3] = max(c[3], .25); g['doubleSided'] = True
    if tree: g['alphaMode'] = 'MASK'; g['alphaCutoff'] = .33; g['doubleSided'] = True
    g['pbrMetallicRoughness']['baseColorFactor'] = [max(0.0, min(1.0, float(v))) for v in c]
    uvx = (1, 1, 0, 0)
    if texenv and texenv.m_Texture.path_id:
        big = 1024 if m.m_Name.lower().startswith(('sign', 'church2', 'residence')) else 512
        g['pbrMetallicRoughness']['baseColorTexture'] = {'index': tex_image(texenv.m_Texture, big, tree)}
        uvx = (texenv.m_Scale.x, texenv.m_Scale.y, texenv.m_Offset.x, texenv.m_Offset.y)
    materials.append(g); mat_index[key] = (len(materials) - 1, uvx)
    return mat_index[key]

# --- collect scene meshes --------------------------------------------------
groups = {}  # (landmark or None, material idx) -> [pos, nrm, uv, idx]
def add(mi, uvx, V, N, UV, T, M, lm=None):
    Mw = FLIP @ M
    Vw = (np.c_[V, np.ones(len(V))] @ Mw.T)[:, :3]
    if N is not None:
        Nw = N @ np.linalg.inv(Mw[:3, :3])
        Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-9)
    else: Nw = np.tile([0, 1, 0], (len(V), 1))
    UVw = UV * [uvx[0], uvx[1]] + [uvx[2], uvx[3]]
    used = np.unique(T); remap = -np.ones(len(V), dtype=np.int64); remap[used] = np.arange(len(used))
    tri = remap[T]
    if np.linalg.det(Mw[:3, :3]) < 0: tri = tri[:, ::-1]  # keep front faces front
    g = groups.setdefault((lm, mi), [[], [], [], [], 0])
    g[0].append(Vw[used]); g[1].append(Nw[used]); g[2].append(UVw[used]); g[3].append(tri + g[4]); g[4] += len(used)

# The four tour landmarks go into their own nodes so the remastered edition can
# swap them for rebuilt models. Picked by name/parent and position.
def landmark(name, par, c):
    x, y, z = -c[0], c[1], c[2]
    if par == 'wbchruch' and -170 < x < -157 and 284 < z < 304 and name not in ('ch.003', 'ch.004', 'ch.005'):
        return 'church'
    if par == 'courthouse (1)' and z < 300:
        return 'courthouse'
    if par in ('armory', 'armory (1)') or name in ('ch.door.001', 'ch.window.001 (15)') or par.startswith('Modular Window'):
        return 'magazine'
    if -160 < x < -154.3 and 220 < z < 237 and y > 2 and par not in ('well', 'lamppost2 (5)'):
        return 'randolph'
    return None

skipped, chimneys = [], []
for pid, o in LVL.objects.items():
    if o.type.name != 'MeshRenderer': continue
    r = o.read()
    if not r.m_Enabled: continue
    go = r.m_GameObject.read(); tpid = go_tr[r.m_GameObject.path_id]
    if not active(tpid): continue
    mf = next((c for c in comps(go) if c.type.name == 'MeshFilter'), None)
    if not mf: continue
    mptr = mf.read().m_Mesh
    if not mptr.path_id: continue
    mesh = mptr.read(); M = world(tpid)
    name = go.m_Name
    if name.startswith('Site'):  # invisible trigger boxes
        continue
    md = mesh_data(mesh)
    if md is None: skipped.append(name + ' (empty mesh)'); continue
    V, N, UV, subs = md
    Vw = (np.c_[V, np.ones(len(V))] @ M.T)[:, :3]
    lo, hi = Vw.min(0), Vw.max(0)
    if hi[1] < -1 or lo[0] > 520 or hi[0] < -20 or lo[2] > 520 or hi[2] < -20:
        skipped.append(f'{name}@{tr[parent[tpid]].m_GameObject.read().m_Name if parent[tpid] else "-"} y{hi[1]:.0f} x{lo[0]:.0f}..{hi[0]:.0f} z{lo[2]:.0f}'); continue
    par = tr[parent[tpid]].m_GameObject.read().m_Name if parent[tpid] else '-'
    lm = landmark(name, par, (lo + hi) / 2)
    if 'chimney' in name.lower() and not lm:
        chimneys.append([round(-(lo[0] + hi[0]) / 2, 2), round(float(hi[1]), 2), round((lo[2] + hi[2]) / 2, 2)])
    for i, T in enumerate(subs):
        if i >= len(r.m_Materials) or not r.m_Materials[i].path_id: continue
        mi, uvx = material(r.m_Materials[i])
        add(mi, uvx, V, N, UV, T, M, lm)
print('skipped off-map objects:', sorted(set(skipped)))

# --- glTF writer -----------------------------------------------------------
bin_parts, accessors, views, meshes, nodes = [], [], [], [], []
def blob(arr, target=None):
    b = arr.tobytes(); off = sum(len(x) for x in bin_parts)
    pad = (-len(b)) % 4
    bin_parts.append(b + b'\0' * pad)
    v = {'buffer': 0, 'byteOffset': off, 'byteLength': len(b)}
    if target: v['target'] = target
    views.append(v); return len(views) - 1
def acc(arr, typ, comp):
    a = {'bufferView': blob(arr, 34963 if typ == 'SCALAR' else 34962), 'componentType': comp,
         'count': int(len(arr)), 'type': typ}
    if typ == 'VEC3': a['min'] = arr.min(0).tolist(); a['max'] = arr.max(0).tolist()
    accessors.append(a); return len(accessors) - 1
def prim(pos, nrm, uv, idx, mi):
    big = pos.shape[0] > 65535
    return {'attributes': {'POSITION': acc(pos.astype(np.float32), 'VEC3', 5126),
                           'NORMAL': acc(nrm.astype(np.float32), 'VEC3', 5126),
                           'TEXCOORD_0': acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), 'VEC2', 5126)},
            'indices': acc(idx.reshape(-1).astype(np.uint32 if big else np.uint16), 'SCALAR', 5125 if big else 5123),
            'material': mi}

_td = next(o for o in SA.objects.values() if o.type.name == 'TerrainData').read_typetree()['m_Heightmap']
_W = _td['m_Width']; _sc = _td['m_Scale']
_H = np.array(_td['m_Heights'], dtype=np.float64).reshape(_W, _W) / 32766 * _sc['y']
def ground(x, z):
    # terrain height at three.js (x, z); Unity x = -x
    u = np.clip(-x / _sc['x'], 0, _W - 1.001); v = np.clip(z / _sc['z'], 0, _W - 1.001)
    x0 = np.floor(u).astype(int); z0 = np.floor(v).astype(int); fx = u - x0; fz = v - z0
    h = lambda xx, zz: _H[zz, xx]
    return (h(x0, z0) * (1 - fx) + h(x0 + 1, z0) * fx) * (1 - fz) + (h(x0, z0 + 1) * (1 - fx) + h(x0 + 1, z0 + 1) * fx) * fz

def cluster(pos, idx, cell):
    # The roads are Blender bezier strips with millions of tiny faces; they are
    # flat, so merging vertices on a grid keeps their shape at a fraction of the size.
    q = np.round(pos / cell).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1); t = inv[idx]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    key = np.sort(t, axis=1); _, keep = np.unique(key, axis=0, return_index=True); t = t[np.sort(keep)]
    return pos[first], t

from PIL import ImageDraw, ImageFilter
ROAD_RES = 2048  # road mask over the whole 500 m terrain, ~0.25 m per pixel
road_mask = Image.new('L', (ROAD_RES, ROAD_RES), 0); road_draw = ImageDraw.Draw(road_mask)
by_node, lm_bounds = {}, {}
for (lm, mi), (P, Nn, U, I, _) in groups.items():
    P, Nn, U, I = np.vstack(P), np.vstack(Nn), np.vstack(U), np.vstack(I)
    if materials[mi]['name'] == 'road.1':
        P, I = cluster(P, I, 0.6)
        # In the build the roads are thick slabs floating up to a metre above the
        # grass. Keep only their top faces and lay them on the terrain.
        a, b, c = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
        n = np.cross(b - a, c - a); ln = np.linalg.norm(n, axis=1)
        I = I[n[:, 1] > 0.5 * np.maximum(ln, 1e-12)]
        P = P.copy(); P[:, 1] = ground(P[:, 0], P[:, 2]) + 0.05
        Nn = np.tile([0.0, 1, 0], (len(P), 1)); U = np.c_[P[:, 0], P[:, 2]] / 6.0
        px = np.c_[-P[:, 0] / 500 * ROAD_RES, P[:, 2] / 500 * ROAD_RES]
        for t in I: road_draw.polygon([tuple(px[k]) for k in t], fill=255)
    if lm:
        b = lm_bounds.setdefault(lm, [P.min(0), P.max(0)])
        b[0] = np.minimum(b[0], P.min(0)); b[1] = np.maximum(b[1], P.max(0))
    by_node.setdefault(lm, []).append(prim(P, Nn, U, I, mi))
for lm, prims in by_node.items():
    meshes.append({'name': lm or 'town', 'primitives': prims})
    nodes.append({'name': 'lm:' + lm if lm else 'town', 'mesh': len(meshes) - 1})
road_mask.filter(ImageFilter.GaussianBlur(2)).save(os.path.join(OUT, 'roadmask.png'), optimize=True)

# tree prototypes (instanced in JS from world.json)
tree_meshes = {'Broadleaf_Desktop': 'Broadleaf_Desktop_LOD1', 'Broadleaf_Mobile': 'Broadleaf_Mobile_LOD1', 'bush06': 'bush06'}
td = next(o for o in SA.objects.values() if o.type.name == 'TerrainData').read_typetree()
dd = td['m_DetailDatabase']
proto_names = []
for proto in dd['m_TreePrototypes']:
    pgo = SA.objects[proto['prefab']['m_PathID']].read(); proto_names.append(pgo.m_Name)
    want = tree_meshes[pgo.m_Name]; found = None
    stack = [pgo]
    while stack and not found:
        g = stack.pop()
        for c in g.m_Component:
            o = SA.objects.get((c.component if hasattr(c, 'component') else c).path_id)
            if not o: continue
            if o.type.name == 'Transform': stack += [ch.read().m_GameObject.read() for ch in o.read().m_Children]
            if o.type.name == 'MeshFilter' and g.m_Name == want: found = (o.read(), g)
    mf, g = found
    rend = next(SA.objects[(c.component if hasattr(c, 'component') else c).path_id].read() for c in g.m_Component
                if SA.objects[(c.component if hasattr(c, 'component') else c).path_id].type.name == 'MeshRenderer')
    V, N, UV, subs = mesh_data(mf.m_Mesh.read())
    tp = []
    for i, T in enumerate(subs):
        mi, uvx = material(rend.m_Materials[i])
        used = np.unique(T); remap = -np.ones(len(V), dtype=np.int64); remap[used] = np.arange(len(used))
        V2 = V[used] * [-1, 1, 1]; N2 = N[used] * [-1, 1, 1] if N is not None else np.tile([0, 1, 0], (len(used), 1))
        tp.append(prim(V2, N2, UV[used] * uvx[:2] + uvx[2:], remap[T][:, ::-1], mi))
    meshes.append({'name': pgo.m_Name, 'primitives': tp}); nodes.append({'name': 'tree:' + pgo.m_Name, 'mesh': len(meshes) - 1})

# images into the buffer
gl_images = []
for data, mime in images:
    gl_images.append({'bufferView': blob(np.frombuffer(data, dtype=np.uint8)), 'mimeType': mime})
gltf = {'asset': {'version': '2.0', 'generator': 'williamsburg export-scene.py'},
        'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes,
        'materials': materials, 'textures': [{'source': s, 'sampler': 0} for s in textures],
        'samplers': [{'wrapS': 10497, 'wrapT': 10497, 'minFilter': 9987, 'magFilter': 9729}],
        'images': gl_images, 'accessors': accessors, 'bufferViews': views,
        'buffers': [{'byteLength': sum(len(x) for x in bin_parts)}]}
js = json.dumps(gltf, separators=(',', ':')).encode(); js += b' ' * ((-len(js)) % 4)
bn = b''.join(bin_parts)
glb = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bn)) + struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(bn), 0x004E4942) + bn
open(os.path.join(OUT, 'town.glb'), 'wb').write(glb)
print('town.glb', len(glb) // 1024, 'KB,', len(materials), 'materials,', len(images), 'images')

# --- terrain ---------------------------------------------------------------
hm = td['m_Heightmap']; W = hm['m_Width']; sc = hm['m_Scale']
H = np.array(hm['m_Heights'], dtype=np.uint16).reshape(W, W)  # [z][x], 0..32766 -> 0..sizeY
Hm = H.astype(np.float64) / 32766 * sc['y']  # metres
hmin, hmax = float(Hm.min()), float(Hm.max())
# 8-bit is enough: the town sits on ground only ~5 m from lowest to highest point
Image.fromarray(np.round((Hm - hmin) / (hmax - hmin) * 255).astype(np.uint8)).save(os.path.join(OUT, 'height.png'))
sd = td['m_SplatDatabase']
splat = SA.objects[sd['m_AlphaTextures'][0]['m_PathID']].read().image.convert('RGBA')
splat.save(os.path.join(OUT, 'splat.png'))
layers = []
for i, s in enumerate(sd['m_Splats'][:4]):
    t = SA.objects[s['texture']['m_PathID']].read(); im = t.image.convert('RGB'); im.thumbnail((512, 512))
    fn = f'layer{i}.jpg'; im.save(os.path.join(OUT, fn), quality=82)
    layers.append({'file': fn, 'name': t.m_Name, 'tile': [s['tileSize']['x'], s['tileSize']['y']]})
size = [sc['x'] * (W - 1), sc['y'], sc['z'] * (W - 1)]

trees = [{'p': proto_names[t['index']], 'x': -t['position']['x'] * size[0], 'y': t['position']['y'] * size[1],
          'z': t['position']['z'] * size[2], 'w': t['widthScale'], 'h': t['heightScale'], 'r': t['rotation']}
         for t in dd['m_TreeInstances']]

def wpos(name, need=None):
    for pid, t in tr.items():
        go = t.m_GameObject.read()
        if go.m_Name == name and (not need or any(c.type.name == need for c in comps(go))):
            v = world(pid)[:3, 3]; return [-v[0], v[1], v[2]]
def wrot_y(name, need=None):
    for pid, t in tr.items():
        go = t.m_GameObject.read()
        if go.m_Name == name and (not need or any(c.type.name == need for c in comps(go))):
            M = FLIP @ world(pid) @ FLIP; f = M[:3, 2]; return float(np.arctan2(f[0], f[2]))

def wbox(name):
    # world-space bounds of every mesh under a named object (e.g. a sign board)
    root = next(pid for pid, t in tr.items() if t.m_GameObject.read().m_Name == name)
    pts = []
    stack = [root]
    while stack:
        pid = stack.pop(); go = tr[pid].m_GameObject.read()
        stack += [c.path_id for c in tr[pid].m_Children]
        mf = next((c for c in comps(go) if c.type.name == 'MeshFilter'), None)
        if mf and mf.read().m_Mesh.path_id:
            md = mesh_data(mf.read().m_Mesh.read())
            if md: pts.append((np.c_[md[0], np.ones(len(md[0]))] @ (FLIP @ world(pid)).T)[:, :3])
    P = np.vstack(pts); return [P.min(0).round(2).tolist(), P.max(0).round(2).tolist()]

world_json = {
    'terrain': {'size': size, 'res': W, 'layers': layers, 'hmin': hmin, 'hmax': hmax},
    'trees': trees,
    'sites': {n: wpos(n) for n in ('Site1', 'Site2', 'Site3', 'Site4')},
    'signs': {n: {'pos': wpos(n), 'rotY': wrot_y(n), 'box': wbox(n)} for n in ('Church_Sign', 'Courthouse_Sign', 'Armory_Sign', 'Residence_Sign')},
    'smoke': [wpos(n) for n in ('Smoke (2)', 'Smoke (3)')],
    'dust': [wpos(n) for n in ('DustStorm', 'DustStorm (1)', 'DustStorm (2)', 'DustStorm (3)', 'DustStorm (4)', 'DustStorm (5)', 'DustStorm (6)', 'DustStorm (7)')],
    'flag': {'pos': wpos('Plane', 'Cloth'), 'pole': wpos('Cylinder (2)')},
    'title': wpos('king-s-arms-tavern'),
    'chimneys': chimneys,
    'landmarks': {k: [v[0].round(2).tolist(), v[1].round(2).tolist()] for k, v in lm_bounds.items()},
    'start': wpos('Player'),
    'music': 'Old Guard Fife and Drum Corps: Boismortier, Concerto for Five Flutes No. 4, I. Adagio',
}
json.dump(world_json, open(os.path.join(OUT, 'world.json'), 'w'), indent=1)

# --- 2D art: title card, info panel photos, flag, particles ---------------
for o in list(SA.objects.values()) + list(LVL.objects.values()):
    if o.type.name != 'Texture2D': continue
    t = o.read()
    wanted = {'king-s-arms-tavern': 'title.jpg', '1024px-Bruton_Church,_Williamsburg': 'photo-church.jpg',
              '1280px-Williamsburg_Virginia_Court_House': 'photo-courthouse.jpg',
              'US_flag_13_stars_–_Betsy_Ross.svg': 'flag.jpg', 'ParticleCloudWhite': 'smoke.png',
              'GrassFrond02AlbedoAlpha': 'grass.png'}
    if t.m_Name in wanted:
        fn = wanted[t.m_Name]; im = t.image; im.thumbnail((1024, 1024))
        if fn.endswith('png'): im.save(os.path.join(OUT, fn), optimize=True)
        else: im.convert('RGB').save(os.path.join(OUT, fn), quality=85)

# Ryan's photographs of the real surfaces, kept at full resolution for the
# remastered materials (see make-textures.py).
SRC = os.path.join(OUT, 'src'); os.makedirs(SRC, exist_ok=True)
photos = {'brick.seemless.1': 'brick', 'DSC_0713': 'clapboard-grey', 'VC_Summer__2935': 'clapboard-brown',
          'shingles01': 'shingles', 'roof_0097_02_preview': 'roof', 'DSC_0701': 'grass',
          'wildtextures_white-stained-wooden-boards': 'boards', 'T19_Dark_Chocolate': 'fence-wood'}
# Some names appear twice (the photo and its blurry parallax height map), so keep
# whichever copy has the most fine detail.
best = {}
for o in SA.objects.values():
    if o.type.name != 'Texture2D': continue
    t = o.read()
    if t.m_Name not in photos: continue
    im = t.image.convert('RGB'); a = np.asarray(im.convert('L'), dtype=np.float64)
    detail = np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean()
    if detail > best.get(t.m_Name, (-1, None))[0]: best[t.m_Name] = (detail, im)
for n, (_, im) in best.items():
    im.save(os.path.join(SRC, photos[n] + '.png'))

# The magazine and Peyton Randolph House photos only exist on the 3D sign boards,
# so cut them out of the sign textures for the info panels.
for o in SA.objects.values():
    if o.type.name != 'Texture2D': continue
    t = o.read()
    crops = {'Sign.courthouse': ('photo-magazine.jpg', (545, 40, 1018, 290)),
             'Sign.residence': ('photo-residence.jpg', (60, 68, 532, 298))}
    if t.m_Name in crops:
        fn, box = crops[t.m_Name]
        t.image.convert('RGB').transpose(Image.ROTATE_180).crop(box).save(os.path.join(OUT, fn), quality=88)

# --- music -----------------------------------------------------------------
ac = next(o for o in SA.objects.values() if o.type.name == 'AudioClip').read()
for name, data in ac.samples.items():
    open(os.path.join(OUT, 'fife-raw' + os.path.splitext(name)[1]), 'wb').write(data)
print('done ->', OUT)
print('next: npx @gltf-transform/cli quantize web/assets/town.glb web/assets/town.glb && python3 web/tools/pack.py')
