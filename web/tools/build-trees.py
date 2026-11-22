#!/usr/bin/env python3
"""Procedural trees for the remastered Williamsburg.

The 2018 build used Unity's stock SpeedTree palms and broadleafs, which read as
noisy fronds up close and are the wrong species for Tidewater Virginia. This
grows proper deciduous trees instead: a live-oak-like spreading shade tree, a
tall vase-shaped elm, a round crabapple/dogwood-sized ornamental and a clipped
boxwood shrub (for the 2018 bushes). Branches are tapered tubes that follow the
recursive structure of a real crown; foliage is leaf-cluster cards whose normals
point out of the crown, so it lights like a soft mass rather than paper.

Writes web/assets/trees.glb (bark and leaf textures embedded). Each tree is a
root node named tree_<kind> with two meshes: bark and leaves. Trees are about
1 unit = 1 metre, base at the origin.
"""
import io, json, math, os, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'trees.glb')
rng = np.random.default_rng(1632)  # Middle Plantation was founded in 1632


# ---------------------------------------------------------------- textures
def leaf_poly(cx, cy, length, width, ang, lobes=0):
    pts = []
    for i in range(24):
        t = i / 23
        w = math.sin(math.pi * t) ** 0.8 * width
        if lobes: w *= 0.8 + 0.2 * abs(math.sin(t * math.pi * lobes))
        pts.append((t * length, w))
    pts += [(x, -y) for x, y in reversed(pts)]
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def leaf_atlas(S=1024):
    """2x2 atlas of leaf clusters: oak, elm, small round leaves, boxwood."""
    big = S * 2
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    q = big // 2
    kinds = [  # (leaf length, width, count, lobes, palette)
        (84, 38, 430, 3, [(58, 86, 34), (72, 102, 40), (46, 70, 30), (88, 112, 48)]),
        (74, 34, 460, 0, [(62, 94, 36), (80, 110, 44), (50, 78, 30), (96, 122, 52)]),
        (58, 38, 440, 0, [(70, 104, 42), (88, 122, 50), (56, 88, 34), (104, 132, 58)]),
        (30, 17, 1700, 0, [(44, 72, 30), (56, 86, 34), (36, 60, 26), (66, 96, 40)]),
    ]
    for k, (L, W, n, lobes, pal) in enumerate(kinds):
        ox, oy = (k % 2) * q, (k // 2) * q
        c = np.array([ox + q / 2, oy + q / 2])
        twig = (60, 48, 36, 255)
        # twigs radiating from the lower middle, leaves along them
        ntw = 7 if k < 3 else 16
        tips = []
        for t in range(ntw):
            a = -math.pi / 2 + (t / (ntw - 1) - 0.5) * 2.6 + rng.normal(0, 0.12)
            base = c + np.array([0, q * 0.36])
            ln = q * (0.55 + rng.random() * 0.25)
            tip = base + np.array([math.cos(a), math.sin(a)]) * ln
            if k < 3: d.line([tuple(base), tuple(tip)], fill=twig, width=5)
            tips.append((base, tip))
        for i in range(n):
            base, tip = tips[i % ntw]
            s = rng.random() ** 0.7
            p = base + (tip - base) * (0.25 + 0.75 * s) + rng.normal(0, q * (0.07 if k < 3 else 0.14), 2)
            if np.any(p < [ox + L, oy + L]) or np.any(p > [ox + q - L, oy + q - L]): continue
            ang = math.atan2(*(tip - base)[::-1]) + rng.normal(0, 0.9)
            sc = 0.75 + rng.random() * 0.5
            col = np.array(pal[rng.integers(len(pal))], float) * (0.85 + rng.random() * 0.3)
            poly = leaf_poly(p[0], p[1], L * sc, W * sc / 2, ang, lobes)
            d.polygon(poly, fill=tuple(int(v) for v in np.clip(col, 0, 255)) + (255,))
            # midrib and a lighter sunlit half
            e = (p[0] + math.cos(ang) * L * sc, p[1] + math.sin(ang) * L * sc)
            d.line([tuple(p), e], fill=tuple(int(v) for v in np.clip(col * 1.25, 0, 255)) + (255,), width=2)
    img = img.resize((S, S), Image.LANCZOS)
    a = np.asarray(img).astype(np.float32)
    # bleed leaf colour into transparent texels so mipmaps don't fringe dark
    rgb, al = a[..., :3], a[..., 3:] / 255
    blur = np.asarray(Image.fromarray(np.uint8(rgb * al)).filter(ImageFilter.GaussianBlur(12))).astype(np.float32)
    wb = np.asarray(Image.fromarray(np.uint8(al[..., 0] * 255)).filter(ImageFilter.GaussianBlur(12))).astype(np.float32)[..., None] / 255
    fill = blur / np.maximum(wb, 1e-3)
    out = np.where(al > 0.5, rgb, fill)
    alpha = np.where(al[..., 0] > 0.5, 255, 0)
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), alpha]).astype(np.uint8), 'RGBA')


def bark(S=512):
    """Tileable furrowed bark: vertical ridges broken by horizontal cracks."""
    f = np.fft.fftfreq(S)
    def nz(sx, sy, seed):
        w = np.random.default_rng(seed).standard_normal((S, S))
        k = np.exp(-((f[None, :] * sx) ** 2 + (f[:, None] * sy) ** 2) * 4)
        o = np.real(np.fft.ifft2(np.fft.fft2(w) * k)); o -= o.min(); return o / o.max()
    ridges = nz(14, 90, 1)
    cracks = nz(30, 12, 2)
    h = np.clip(ridges * 1.3 - 0.2 + (cracks - 0.5) * 0.35, 0, 1)
    h = h ** 1.4
    fine = nz(3, 3, 3)
    base = np.array([96, 86, 76]) / 255
    col = base[None, None, :] * (0.45 + 0.75 * h[..., None]) * (0.9 + 0.2 * fine[..., None])
    moss = np.clip((nz(40, 40, 4) - 0.62) * 3, 0, 1)[..., None] * (1 - h[..., None])
    col = col * (1 - moss * 0.5) + np.array([0.33, 0.37, 0.22]) * moss * 0.5
    img = Image.fromarray(np.uint8(np.clip(col, 0, 1) * 255), 'RGB')
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 6
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 6
    n = np.dstack([-dx, dy, np.ones_like(h)]); n /= np.linalg.norm(n, axis=2, keepdims=True)
    nimg = Image.fromarray(np.uint8((n * 0.5 + 0.5) * 255), 'RGB')
    return img, nimg


# ---------------------------------------------------------------- geometry
class Mesh:
    def __init__(self):
        self.p, self.n, self.uv, self.c, self.i = [], [], [], [], []

    def add(self, p, n, uv, c):
        self.p.append(p); self.n.append(n); self.uv.append(uv); self.c.append(c)
        return len(self.p) - 1


def frame(d):
    d = d / np.linalg.norm(d)
    a = np.array([0, 0, 1.0]) if abs(d[1]) > 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a); u /= np.linalg.norm(u)
    return u, np.cross(u, d)


def tube(m, path, radii, sides, vscale=1.5):
    """Tapered tube along a polyline; texture v runs in metres/vscale."""
    rings, v = [], 0.0
    u0, w0 = frame(path[1] - path[0])
    for k, (p, r) in enumerate(zip(path, radii)):
        d = (path[min(k + 1, len(path) - 1)] - path[max(k - 1, 0)])
        d /= np.linalg.norm(d)
        # parallel transport the frame so the bark doesn't twist
        u0 = u0 - d * np.dot(u0, d); u0 /= np.linalg.norm(u0); w0 = np.cross(u0, d)
        if k: v += np.linalg.norm(path[k] - path[k - 1]) / vscale
        ring = []
        for s in range(sides + 1):
            a = s / sides * 2 * math.pi
            nrm = u0 * math.cos(a) + w0 * math.sin(a)
            ao = min(1.0, 0.55 + 0.45 * min(1, p[1] / 3.0))
            ring.append(m.add(p + nrm * r, nrm, (s / sides * max(1, round(r * 2 * math.pi / 0.6)), v), (ao, ao, ao)))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for s in range(sides):
            m.i += [a[s], b[s], a[s + 1], a[s + 1], b[s], b[s + 1]]


def grow(bark_m, tips, p0, d, length, r0, depth, P, taper_to=None):
    """One branch: a curved tube, then children along it and at its end."""
    segs = max(3, int(length / 0.5))
    path, radii = [p0], []
    p, dd = p0.copy(), d / np.linalg.norm(d)
    r1 = taper_to if taper_to is not None else r0 * P['taper']
    for k in range(segs):
        dd = dd + rng.normal(0, P['wander'], 3) + np.array([0, P['up'][depth], 0])
        dd /= np.linalg.norm(dd)
        p = p + dd * (length / segs)
        path.append(p)
    for k in range(len(path)):
        t = k / (len(path) - 1)
        radii.append(r0 + (r1 - r0) * t)
    if depth == 0:  # root flare
        radii[0] *= 1.45; radii[1] *= 1.12
    sides = 10 if depth == 0 else 7 if depth == 1 else 5 if depth == 2 else 4
    if r0 > P['min_r']:
        tube(bark_m, np.array(path), radii, sides)
    if depth >= P['depth']:
        tips.append((path[-1], dd, path[-2]))
        return
    kids = P['kids'][depth]
    for c in range(kids):
        t = P['start'][depth] + (1 - P['start'][depth]) * (c + rng.random() * 0.8) / kids
        t = min(t, 1.0)
        k = int(t * (len(path) - 1))
        base = path[k]
        az = rng.random() * 2 * math.pi if depth else (c / kids) * 2 * math.pi + rng.normal(0, 0.3)
        spread = math.radians(P['spread'][depth] + rng.normal(0, 8))
        u, w = frame(dd)
        cd = dd * math.cos(spread) + (u * math.cos(az) + w * math.sin(az)) * math.sin(spread)
        cl = length * P['ratio'][depth] * (0.75 + rng.random() * 0.4) * (1.15 - 0.4 * t if depth else 1)
        cr = max(radii[k] * P['rratio'], P['min_r'] * 0.6)
        grow(bark_m, tips, base, cd, cl, cr, depth + 1, P)
    # a leader continues past the last fork on the upright kinds
    if P.get('leader') and depth < P['depth'] - 1:
        grow(bark_m, tips, path[-1], dd, length * 0.6, r1, depth + 1, P)
    elif depth >= 1:
        tips.append((path[-1], dd, path[-2]))


def leaves(m, tips, cell, P, center):
    """Leaf-cluster cards around branch tips; normals blend toward the crown shape."""
    lo, hi = cell
    for tip, d, prev in tips:
        for j in range(P['cards']):
            c = tip + rng.normal(0, P['spread_leaf'], 3) * np.array([1, 0.7, 1]) + d * rng.random() * 0.6
            s = P['card'] * (0.7 + rng.random() * 0.6)
            nrm = rng.normal(0, 1, 3); nrm /= np.linalg.norm(nrm)
            u, w = frame(nrm)
            rot = rng.random() * 2 * math.pi
            u, w = u * math.cos(rot) + w * math.sin(rot), -u * math.sin(rot) + w * math.cos(rot)
            out = c - center; out[1] *= 0.8; out /= np.linalg.norm(out) + 1e-6
            nn = out * 0.8 + np.array([0, 0.35, 0]); nn /= np.linalg.norm(nn)
            # darker deep inside the crown and underneath
            rel = np.linalg.norm((c - center) / P['crown'])
            ao = float(np.clip(0.45 + 0.55 * rel, 0.4, 1.0)) * (0.85 + 0.15 * float(np.clip((c[1] - center[1]) / P['crown'][1] + 0.5, 0, 1)))
            tint = 0.88 + rng.random() * 0.24
            col = (ao * tint, ao * tint * (0.97 + rng.random() * 0.06), ao * tint)
            corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
            idx = [m.add(c + (u * a + w * b) * s * 0.5, nn, (lo[0] + (a + 1) / 2 * (hi[0] - lo[0]), lo[1] + (1 - (b + 1) / 2) * (hi[1] - lo[1])), col) for a, b in corners]
            m.i += [idx[0], idx[1], idx[2], idx[0], idx[2], idx[3]]


CELLS = {'oak': ((0, 0), (.5, .5)), 'elm': ((.5, 0), (1, .5)), 'round': ((0, .5), (.5, 1)), 'box': ((.5, .5), (1, 1))}
KINDS = {
    # wide, low-forking shade tree (the big oaks on Palace Green)
    'oak': dict(trunk=3.4, r=0.42, depth=3, kids=[5, 4, 4], start=[0.9, 0.25, 0.3], spread=[52, 42, 45],
                ratio=[1.9, 0.55, 0.5], rratio=0.62, taper=0.55, wander=0.16, up=[0.02, 0.0, 0.05, 0.08],
                min_r=0.025, cards=9, card=1.5, spread_leaf=0.55, crown=np.array([7, 4.5, 7]), cy=7.0, cell='oak'),
    # tall vase-shaped street elm
    'elm': dict(trunk=4.2, r=0.36, depth=3, kids=[4, 4, 3], start=[0.92, 0.3, 0.3], spread=[28, 38, 45],
                ratio=[2.2, 0.5, 0.5], rratio=0.6, taper=0.55, wander=0.12, up=[0.03, 0.06, 0.04, 0.06],
                min_r=0.025, cards=8, card=1.4, spread_leaf=0.5, crown=np.array([5, 5.5, 5]), cy=9.5, cell='elm'),
    # small rounded ornamental
    'round': dict(trunk=1.8, r=0.2, depth=3, kids=[4, 3, 3], start=[0.9, 0.3, 0.35], spread=[45, 40, 45],
                  ratio=[1.7, 0.6, 0.55], rratio=0.6, taper=0.55, wander=0.18, up=[0.02, 0.03, 0.05, 0.05],
                  min_r=0.018, cards=8, card=1.1, spread_leaf=0.4, crown=np.array([2.8, 2.4, 2.8]), cy=3.8, cell='round'),
    # clipped boxwood clump
    'box': dict(trunk=0.3, r=0.06, depth=2, kids=[7, 4], start=[0.6, 0.3], spread=[55, 40],
                ratio=[3.0, 0.5], rratio=0.6, taper=0.6, wander=0.2, up=[0.0, 0.0, 0.02],
                min_r=0.012, cards=10, card=0.55, spread_leaf=0.22, crown=np.array([0.9, 0.7, 0.9]), cy=0.75, cell='box'),
}


def build_tree(kind):
    P = KINDS[kind]
    b, l, tips = Mesh(), Mesh(), []
    grow(b, tips, np.zeros(3), np.array([rng.normal(0, 0.05), 1, rng.normal(0, 0.05)]), P['trunk'], P['r'], 0, P)
    ys = np.array([t[0] for t in tips])
    center = np.array([0, P['cy'], 0]) if kind != 'box' else np.array([0, ys[:, 1].mean() * 0.8, 0])
    if kind == 'box':  # clipped: pull tips onto a soft dome
        tips = [(np.array([t[0][0], max(t[0][1], 0.2), t[0][2]]), t[1], t[2]) for t in tips]
    leaves(l, tips, CELLS[P['cell']], P, center)
    return b, l


# ---------------------------------------------------------------- glb writer
class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.j = {'asset': {'version': '2.0', 'generator': 'build-trees.py'}, 'scene': 0, 'scenes': [{'nodes': []}],
                  'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': [], 'materials': [], 'textures': [],
                  'images': [], 'samplers': [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}],
                  'buffers': [{'byteLength': 0}]}

    def view(self, data, target=None):
        while len(self.bin) % 4: self.bin.append(0)
        v = {'buffer': 0, 'byteOffset': len(self.bin), 'byteLength': len(data)}
        if target: v['target'] = target
        self.bin += data
        self.j['bufferViews'].append(v)
        return len(self.j['bufferViews']) - 1

    def acc(self, arr, typ, target):
        arr = np.asarray(arr)
        ct = 5125 if arr.dtype == np.uint32 else 5126
        a = {'bufferView': self.view(arr.tobytes(), target), 'componentType': ct, 'count': int(arr.shape[0]), 'type': typ}
        if typ == 'VEC3' and ct == 5126:
            a['min'] = arr.min(0).tolist(); a['max'] = arr.max(0).tolist()
        self.j['accessors'].append(a)
        return len(self.j['accessors']) - 1

    def image(self, img, fmt):
        buf = io.BytesIO(); img.save(buf, fmt, **({'quality': 88} if fmt == 'JPEG' else {'optimize': True}))
        self.j['images'].append({'bufferView': self.view(buf.getvalue()), 'mimeType': 'image/' + fmt.lower()})
        self.j['textures'].append({'sampler': 0, 'source': len(self.j['images']) - 1})
        return len(self.j['textures']) - 1

    def material(self, name, tex, normal=None, mask=False):
        m = {'name': name, 'pbrMetallicRoughness': {'baseColorTexture': {'index': tex}, 'metallicFactor': 0, 'roughnessFactor': 0.9}}
        if normal is not None: m['normalTexture'] = {'index': normal}
        if mask: m.update(alphaMode='MASK', alphaCutoff=0.5, doubleSided=True)
        self.j['materials'].append(m)
        return len(self.j['materials']) - 1

    def mesh(self, name, m, mat):
        prim = {'attributes': {'POSITION': self.acc(np.float32(m.p), 'VEC3', 34962),
                               'NORMAL': self.acc(np.float32(m.n), 'VEC3', 34962),
                               'TEXCOORD_0': self.acc(np.float32(m.uv), 'VEC2', 34962),
                               'COLOR_0': self.acc(np.float32(m.c), 'VEC3', 34962)},
                'indices': self.acc(np.uint32(m.i), 'SCALAR', 34963), 'material': mat}
        self.j['meshes'].append({'name': name, 'primitives': [prim]})
        self.j['nodes'].append({'name': name, 'mesh': len(self.j['meshes']) - 1})
        return len(self.j['nodes']) - 1

    def write(self, path):
        while len(self.bin) % 4: self.bin.append(0)
        self.j['buffers'][0]['byteLength'] = len(self.bin)
        js = json.dumps(self.j, separators=(',', ':')).encode()
        js += b' ' * ((4 - len(js) % 4) % 4)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.bin)))
            f.write(struct.pack('<II', len(js), 0x4E4F534A)); f.write(js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942)); f.write(self.bin)


if __name__ == '__main__':
    g = GLB()
    atlas = leaf_atlas()
    atlas.save('/tmp/leaf-atlas.png')
    bc, bn = bark()
    mat_leaf = g.material('leaves', g.image(atlas, 'PNG'), mask=True)
    mat_bark = g.material('bark', g.image(bc, 'JPEG'), g.image(bn, 'JPEG'))
    variants = {'oak': 3, 'elm': 3, 'round': 2, 'box': 2}
    for kind, n in variants.items():
        for v in range(n):
            b, l = build_tree(kind)
            kids = [g.mesh(f'{kind}{v}_bark', b, mat_bark), g.mesh(f'{kind}{v}_leaves', l, mat_leaf)]
            g.j['nodes'].append({'name': f'tree_{kind}{v}', 'children': kids})
            g.j['scenes'][0]['nodes'].append(len(g.j['nodes']) - 1)
            print(kind, v, 'bark tris', len(b.i) // 3, 'cards', len(l.i) // 6,
                  'height', round(max(p[1] for p in l.p), 1), 'width', round(max(abs(p[0]) for p in l.p) * 2, 1))
    g.write(OUT)
    print(OUT, os.path.getsize(OUT) // 1024, 'KB')
