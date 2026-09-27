#!/usr/bin/env python3
"""Model the remastered Williamsburg buildings in Blender.

Run with Blender's Python module (pip install bpy) or `blender -b -P`:
    python3 web/tools/build-landmarks.py
Reads web/assets/world.json (from export-scene.py) and writes
web/assets/landmarks.glb with one object per landmark plus 'houses'.

Everything is modelled in the page's world coordinates (three.js: x east, y up,
z south) on the footprints of the 2018 models, so the signs and tour stops still
line up. The four landmarks follow the photographs on the tour's own sign boards:

  Courthouse (1770)      brick, hipped roof with a modillion cornice, four tall
                         arched windows with open white shutters, an arched door
                         under a pediment cantilevered out over the steps with no
                         columns, a lunette in the tympanum, two ridge chimneys
                         and an octagonal cupola with a bell-shaped dome and
                         weathervane; a rear wing makes the T plan
  Bruton Parish Church   cruciform brick church with round-arched windows in
                         rubbed-brick arches, brick gable ends with round windows,
                         and a west tower of three brick stages under a white
                         two-stage octagonal wooden steeple and a shingled spire
  Magazine (1715)        octagonal brick powder house with a steep shingled roof,
                         high arched windows and a plain door, inside a high
                         brick wall
  Peyton Randolph House  two storeys of dark weatherboard, seven bays, hipped roof
                         with a modillion cornice, shuttered sash windows, a door
                         with a pedimented surround and big chimneys at the ends

The ordinary houses are rebuilt from the footprint, door side, colour and chimney
positions export-scene.py records for each: weatherboarded one- and two-storey
houses on brick foundations, with shingled roofs, box cornices, shuttered sash
windows, dormers on the one-storey houses and brick end chimneys.

Walls have real openings cut through them, so windows and doors sit back in their
reveals and cast shadows. Roofs are laid in shingle courses. Surfaces are named by
material; the page maps each to a textured PBR material projected in world space,
so no UVs are needed.
"""
import json, math, os, random
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'landmarks.glb')
WORLD = json.load(open(os.path.join(ROOT, 'assets', 'world.json')))
rng = random.Random(1699)
CHIMNEYS = []   # chimney tops, for the page's smoke


# ------------------------------------------------------------------ vectors
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))
def unit(a):
    l = length(a); return (a[0] / l, a[1] / l, a[2] / l)
UP = (0.0, 1.0, 0.0)
DOWN = (0.0, -1.0, 0.0)


def clip(poly, f):
    """Clip a convex 2D polygon to the half-plane f(p) >= 0 (f linear)."""
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]; fc, fp = f(cur), f(prev)
        if fc >= 0:
            if fp < 0:
                t = fp / (fp - fc); out.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            out.append(cur)
        elif fp >= 0:
            t = fp / (fp - fc); out.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
    return out


# ------------------------------------------------------------------ mesh builder
class Builder:
    """Accumulates flat polygons per material, in three.js coordinates."""
    def __init__(self, name):
        self.name = name
        self.verts, self.faces, self.mats, self.mat_names = [], [], [], []

    def mat(self, m):
        if m not in self.mat_names: self.mat_names.append(m)
        return self.mat_names.index(m)

    def face(self, pts, m, want):
        """Add a polygon, flipped if needed so that its normal faces `want`."""
        if len(pts) < 3: return
        n = [0.0, 0.0, 0.0]
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            n[0] += (a[1] - b[1]) * (a[2] + b[2]); n[1] += (a[2] - b[2]) * (a[0] + b[0]); n[2] += (a[0] - b[0]) * (a[1] + b[1])
        if length(n) < 1e-8: return
        pts = pts if dot(n, want) >= 0 else pts[::-1]
        base = len(self.verts)
        self.verts += [tuple(p) for p in pts]
        self.faces.append(tuple(range(base, base + len(pts))))
        self.mats.append(self.mat(m))

    def box(self, x0, x1, y0, y1, z0, z1, m, skip=()):
        x0, x1 = min(x0, x1), max(x0, x1); y0, y1 = min(y0, y1), max(y0, y1); z0, z1 = min(z0, z1), max(z0, z1)
        f = {
            '+x': ([(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)], (1, 0, 0)),
            '-x': ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
            '+y': ([(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], UP),
            '-y': ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], DOWN),
            '+z': ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1)),
            '-z': ([(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)], (0, 0, -1)),
        }
        for k, (pts, n) in f.items():
            if k not in skip: self.face(pts, m, n)

    def ring(self, cx, cz, profile, sides, m, rot=0.0, cap=True):
        """Surface of revolution (a `sides`-gon) through (radius, y) profile points, bottom to top."""
        rings = [[(cx + r * math.cos(rot + 2 * math.pi * i / sides), y, cz + r * math.sin(rot + 2 * math.pi * i / sides))
                  for i in range(sides)] for r, y in profile]
        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            dr = profile[k + 1][0] - profile[k][0]; dy = profile[k + 1][1] - profile[k][1]
            for i in range(sides):
                j = (i + 1) % sides
                mid = mul(add(a[i], a[j]), 0.5)
                out = unit((mid[0] - cx, 0, mid[2] - cz))
                self.face([a[j], a[i], b[i], b[j]], m, add(mul(out, dy), (0, -dr, 0)))
        if cap and profile[-1][0] > 1e-6: self.face(rings[-1], m, UP)

    def cap_line(self, p0, p1, m, w=0.1, h=0.05):
        """A saddle board along a ridge or hip line."""
        d = unit(sub(p1, p0)); s = cross(d, UP)
        if length(s) < 1e-6: return
        s = mul(unit(s), w); top = (0, h, 0)
        for sg in (1, -1):
            a0, a1 = add(p0, mul(s, sg)), add(p1, mul(s, sg))
            self.face([add(p0, top), add(p1, top), a1, a0], m, add(mul(s, sg), (0, w, 0)))

    def build(self):
        me = bpy.data.meshes.new(self.name)
        # three.js (x, y, z) -> Blender (x, -z, y); the glTF exporter converts back to Y-up
        me.from_pydata([(x, -z, y) for x, y, z in self.verts], [], self.faces)
        me.validate()
        ob = bpy.data.objects.new(self.name, me)
        for n in self.mat_names:
            ob.data.materials.append(bpy.data.materials.get(n) or bpy.data.materials.new(n))
        for poly, mi in zip(me.polygons, self.mats):
            poly.material_index = mi
            poly.use_smooth = False
        bpy.context.scene.collection.objects.link(ob)
        print(self.name, len(self.faces), 'faces')
        return ob


# ------------------------------------------------------------------ wall frames
class Frame:
    """A vertical wall plane. u runs along the wall (to the right, seen from
    outside), v is world height, d is distance out from the face."""
    def __init__(self, b, o, n):
        self.b = b; self.o = (o[0], 0.0, o[2]); self.n = unit((n[0], 0.0, n[2]))
        self.t = (self.n[2], 0.0, -self.n[0])

    @staticmethod
    def between(b, p0, p1):
        """Frame whose u axis runs from p0 to p1 (world x, z); its normal is (-t.z, 0, t.x)."""
        t = unit((p1[0] - p0[0], 0, p1[2] - p0[2]))
        return Frame(b, p0, (-t[2], 0, t[0])), math.hypot(p1[0] - p0[0], p1[2] - p0[2])

    def P(self, u, v, d=0.0):
        return (self.o[0] + self.t[0] * u + self.n[0] * d, v, self.o[2] + self.t[2] * u + self.n[2] * d)

    def D(self, du, dv, dd):
        return (self.t[0] * du + self.n[0] * dd, dv, self.t[2] * du + self.n[2] * dd)

    def u_of(self, x, z):
        return (x - self.o[0]) * self.t[0] + (z - self.o[2]) * self.t[2]

    def quad(self, u0, u1, v0, v1, d, m):
        self.b.face([self.P(u0, v0, d), self.P(u1, v0, d), self.P(u1, v1, d), self.P(u0, v1, d)], m, self.n)

    def box(self, u0, u1, v0, v1, d0, d1, m, skip=()):
        u0, u1 = min(u0, u1), max(u0, u1); v0, v1 = min(v0, v1), max(v0, v1); d0, d1 = min(d0, d1), max(d0, d1)
        P, b = self.P, self.b
        if 'f' not in skip: b.face([P(u0, v0, d1), P(u1, v0, d1), P(u1, v1, d1), P(u0, v1, d1)], m, self.n)
        if 'k' not in skip: b.face([P(u0, v0, d0), P(u1, v0, d0), P(u1, v1, d0), P(u0, v1, d0)], m, mul(self.n, -1))
        if 'r' not in skip: b.face([P(u1, v0, d0), P(u1, v0, d1), P(u1, v1, d1), P(u1, v1, d0)], m, self.t)
        if 'l' not in skip: b.face([P(u0, v0, d0), P(u0, v0, d1), P(u0, v1, d1), P(u0, v1, d0)], m, mul(self.t, -1))
        if 't' not in skip: b.face([P(u0, v1, d0), P(u1, v1, d0), P(u1, v1, d1), P(u0, v1, d1)], m, UP)
        if 'b' not in skip: b.face([P(u0, v0, d0), P(u1, v0, d0), P(u1, v0, d1), P(u0, v0, d1)], m, DOWN)

    def bar(self, a, c, w, d0, d1, m):
        """A bar of width w in the wall plane between two (u, v) points, from d0 out to d1."""
        eu, ev = c[0] - a[0], c[1] - a[1]; l = math.hypot(eu, ev)
        if l < 1e-6: return
        eu, ev = eu / l, ev / l; pu, pv = -ev * w / 2, eu * w / 2
        c0, c1, c2, c3 = (a[0] + pu, a[1] + pv), (c[0] + pu, c[1] + pv), (c[0] - pu, c[1] - pv), (a[0] - pu, a[1] - pv)
        P, b = self.P, self.b
        b.face([P(*c0, d1), P(*c1, d1), P(*c2, d1), P(*c3, d1)], m, self.n)
        b.face([P(*c0, d0), P(*c0, d1), P(*c1, d1), P(*c1, d0)], m, self.D(pu, pv, 0))
        b.face([P(*c2, d0), P(*c2, d1), P(*c3, d1), P(*c3, d0)], m, self.D(-pu, -pv, 0))
        b.face([P(*c1, d0), P(*c1, d1), P(*c2, d1), P(*c2, d0)], m, self.D(eu, ev, 0))
        b.face([P(*c3, d0), P(*c3, d1), P(*c0, d1), P(*c0, d0)], m, self.D(-eu, -ev, 0))


class Hole:
    """An opening in a wall: centred at u, sill at v, width w, total height h."""
    def __init__(self, u, v, w, h, arch=False):
        self.u, self.v, self.w, self.h, self.arch = u, v, w, h, arch
        self.r = w / 2
        self.body = h - (self.r if arch else 0)   # height of the straight part

    @property
    def u0(self): return self.u - self.w / 2
    @property
    def u1(self): return self.u + self.w / 2
    @property
    def vt(self): return self.v + self.body   # springing line (arched) or head (square)
    @property
    def top(self): return self.v + self.h


ARC = 12   # arch segments (a multiple of 4 so the box corners fall on segment ends)


def arc_pts(h, r, n=ARC):
    return [(h.u + r * math.cos(math.pi * k / n), h.vt + r * math.sin(math.pi * k / n)) for k in range(n + 1)]


def wall(F, u0, u1, v0, v1, m, holes=(), depth=0.35, reveal=None, top=None):
    """A wall face with openings cut through it, plus their reveals.
    `top` optionally continues the face above v1 (a gable), as (u, v) points from the u1 end to the u0 end."""
    reveal = reveal or m
    xs = sorted({u0, u1, *[h.u0 for h in holes], *[h.u1 for h in holes]})
    ys = sorted({v0, v1, *[h.v for h in holes], *[h.vt for h in holes], *[h.top for h in holes]})
    xs = [x for x in xs if u0 <= x <= u1]; ys = [y for y in ys if v0 <= y <= v1]
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            mx, my = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(h.u0 < mx < h.u1 and h.v < my < h.top for h in holes): continue
            F.quad(xs[i], xs[i + 1], ys[j], ys[j + 1], 0, m)
    if top:
        F.b.face([F.P(u0, v1), F.P(u1, v1)] + [F.P(u, v) for u, v in top], m, F.n)
    for h in holes:
        if h.arch:
            pts = arc_pts(h, h.r)
            def edge(a):
                c, s = math.cos(a), math.sin(a)
                t = min(h.r / abs(c) if abs(c) > 1e-9 else 1e9, h.r / s if s > 1e-9 else 1e9)
                return (h.u + c * t, h.vt + s * t)
            for k in range(ARC):   # spandrels between the arch and its bounding box
                q0, q1 = edge(math.pi * k / ARC), edge(math.pi * (k + 1) / ARC)
                F.b.face([F.P(*pts[k]), F.P(*q0), F.P(*q1), F.P(*pts[k + 1])], m, F.n)
            for k in range(ARC):
                a, c = pts[k], pts[k + 1]
                mid = ((a[0] + c[0]) / 2 - h.u, (a[1] + c[1]) / 2 - h.vt)
                F.b.face([F.P(*a, 0), F.P(*c, 0), F.P(*c, -depth), F.P(*a, -depth)], reveal, F.D(-mid[0], -mid[1], 0))
        else:
            F.b.face([F.P(h.u0, h.vt, 0), F.P(h.u1, h.vt, 0), F.P(h.u1, h.vt, -depth), F.P(h.u0, h.vt, -depth)], reveal, DOWN)
        for s, uu in ((1, h.u0), (-1, h.u1)):
            F.b.face([F.P(uu, h.v, 0), F.P(uu, h.vt, 0), F.P(uu, h.vt, -depth), F.P(uu, h.v, -depth)], reveal, F.D(s, 0, 0))
        F.b.face([F.P(h.u0, h.v, 0), F.P(h.u1, h.v, 0), F.P(h.u1, h.v, -depth), F.P(h.u0, h.v, -depth)], reveal, UP)
        # dark back of the opening, in case anything is visible past the sash
        F.quad(h.u0, h.u1, h.v, h.top, -depth - 0.02, 'dark')


def gable_top(L, yt, ye, ridge, over, half):
    """Gable-wall outline under a roof whose eave is `over` beyond the wall at height ye."""
    yw = ye + (ridge - ye) * over / (half + over) - 0.04
    return [(L, yw), (L / 2, ridge - 0.08), (0, yw)]


# ------------------------------------------------------------------ windows and doors
def sash(F, u0, u1, v0, v1, d, cols, rows, m='trim', fw=0.055):
    """One sash: stiles and rails, muntins and glass, front face at d."""
    F.quad(u0, u1, v0, v1, d - 0.03, 'glass')
    F.box(u0, u0 + fw, v0, v1, d - 0.045, d, m); F.box(u1 - fw, u1, v0, v1, d - 0.045, d, m)
    F.box(u0 + fw, u1 - fw, v0, v0 + fw, d - 0.045, d, m); F.box(u0 + fw, u1 - fw, v1 - fw, v1, d - 0.045, d, m)
    for i in range(1, cols):
        x = u0 + fw + (u1 - u0 - 2 * fw) * i / cols
        F.box(x - 0.011, x + 0.011, v0 + fw, v1 - fw, d - 0.04, d - 0.008, m, skip=('k', 't', 'b'))
    for j in range(1, rows):
        y = v0 + fw + (v1 - v0 - 2 * fw) * j / rows
        F.box(u0 + fw, u1 - fw, y - 0.011, y + 0.011, d - 0.04, d - 0.008, m, skip=('k', 'l', 'r'))


def fan(F, h, d, m='trim', spokes=5, fw=0.07):
    """Fanlight / arched sash head: glass half-disc, frame ring and radial bars."""
    r = h.r
    pts = arc_pts(h, r); inner = arc_pts(h, r - fw)
    for k in range(ARC):
        F.b.face([F.P(h.u, h.vt, d - 0.03), F.P(*inner[k], d - 0.03), F.P(*inner[k + 1], d - 0.03)], 'glass', F.n)
        F.b.face([F.P(*pts[k], d), F.P(*pts[k + 1], d), F.P(*inner[k + 1], d), F.P(*inner[k], d)], m, F.n)
        F.b.face([F.P(*inner[k], d), F.P(*inner[k + 1], d), F.P(*inner[k + 1], d - 0.05), F.P(*inner[k], d - 0.05)], m,
                 F.D(h.u - (inner[k][0] + inner[k + 1][0]) / 2, h.vt - (inner[k][1] + inner[k + 1][1]) / 2, 0))
    F.box(h.u0, h.u1, h.vt - 0.03, h.vt + 0.03, d - 0.05, d, m)   # springing bar
    for k in range(1, spokes):
        a = math.pi * k / spokes
        F.bar((h.u, h.vt), (h.u + (r - fw) * math.cos(a), h.vt + (r - fw) * math.sin(a)), 0.022, d - 0.04, d - 0.008, m)
    F.b.face([F.P(h.u + 0.09 * math.cos(math.pi * k / 6), h.vt + 0.09 * math.sin(math.pi * k / 6), d - 0.005) for k in range(7)], m, F.n)


def window(F, h, depth, cols=3, rows=(3, 3), frame='trim', sill='stone', head=None, shutters=None,
           shutter_m='shutter', casing=False):
    """A double-hung sash window set back in its opening."""
    dw = -depth + 0.1
    fw = 0.07
    F.box(h.u0, h.u0 + fw, h.v, h.vt, dw - 0.06, dw + 0.03, frame)
    F.box(h.u1 - fw, h.u1, h.v, h.vt, dw - 0.06, dw + 0.03, frame)
    if not h.arch: F.box(h.u0 + fw, h.u1 - fw, h.vt - fw, h.vt, dw - 0.06, dw + 0.03, frame)
    F.box(h.u0 + fw, h.u1 - fw, h.v, h.v + 0.06, dw - 0.06, dw + 0.03, frame)
    inner_top = h.vt - (0 if h.arch else fw)
    mid = h.v + 0.06 + (inner_top - h.v - 0.06) * rows[1] / (rows[0] + rows[1])
    sash(F, h.u0 + fw, h.u1 - fw, h.v + 0.06, mid + 0.02, dw, cols, rows[1])              # lower sash, in front
    sash(F, h.u0 + fw, h.u1 - fw, mid - 0.02, inner_top, dw - 0.05, cols, rows[0])        # upper sash, behind
    if h.arch: fan(F, h, dw - 0.05, frame, spokes=cols + 1)
    if sill: F.box(h.u0 - 0.08, h.u1 + 0.08, h.v - 0.07, h.v, dw - 0.05, 0.07, sill)
    dress(F, h, head, casing)
    if shutters: shutter_pair(F, h, shutters, shutter_m, casing)


def dress(F, h, head, casing):
    """Masonry or timber dressings around an opening."""
    if head == 'jack':           # flat gauged-brick arch
        F.box(h.u0 - 0.12, h.u1 + 0.12, h.vt, h.vt + 0.3, 0.0, 0.012, 'brick_rubbed', skip=('k',))
    elif head == 'arch':         # rubbed-brick round arch with a stone keystone
        a, o = arc_pts(h, h.r), arc_pts(h, h.r + 0.3)
        for k in range(ARC):
            F.b.face([F.P(*a[k], 0.012), F.P(*o[k], 0.012), F.P(*o[k + 1], 0.012), F.P(*a[k + 1], 0.012)], 'brick_rubbed', F.n)
        F.box(h.u - 0.1, h.u + 0.1, h.top - 0.02, h.top + 0.32, 0, 0.035, 'stone', skip=('k',))
    if casing:                   # timber architrave with a moulded cap on a weatherboarded wall
        cw = 0.1
        F.box(h.u0 - cw, h.u0, h.v, h.vt, 0, 0.035, 'trim', skip=('k',)); F.box(h.u1, h.u1 + cw, h.v, h.vt, 0, 0.035, 'trim', skip=('k',))
        F.box(h.u0 - cw, h.u1 + cw, h.vt, h.vt + 0.12, 0, 0.035, 'trim', skip=('k',))
        F.box(h.u0 - cw - 0.05, h.u1 + cw + 0.05, h.vt + 0.12, h.vt + 0.18, 0, 0.09, 'trim', skip=('k',))


def shutter_pair(F, h, kind, m, casing):
    """Open shutters folded back against the wall either side of an opening."""
    off = 0.1 if casing else 0.03
    hh = h.h
    for s in (-1, 1):
        a = h.u0 - off if s < 0 else h.u1 + off
        c = a + s * h.w / 2
        u0, u1 = min(a, c), max(a, c)
        F.box(u0, u1, h.v, h.v + hh, 0.02, 0.05, m, skip=('k',))
        sw = 0.06
        F.box(u0, u0 + sw, h.v, h.v + hh, 0.05, 0.07, m, skip=('k', 'b')); F.box(u1 - sw, u1, h.v, h.v + hh, 0.05, 0.07, m, skip=('k', 'b'))
        F.box(u0 + sw, u1 - sw, h.v, h.v + sw * 1.5, 0.05, 0.07, m, skip=('k', 'l', 'r'))
        F.box(u0 + sw, u1 - sw, h.v + hh - sw, h.v + hh, 0.05, 0.07, m, skip=('k', 'l', 'r'))
        F.box(u0 + sw, u1 - sw, h.v + hh * 0.48, h.v + hh * 0.48 + sw, 0.05, 0.07, m, skip=('k', 'l', 'r'))
        if kind == 'louver':
            y = h.v + sw * 1.5
            while y < h.v + hh - sw - 0.05:
                if not (h.v + hh * 0.48 - 0.05 < y < h.v + hh * 0.48 + sw):
                    F.b.face([F.P(u0 + sw, y, 0.068), F.P(u1 - sw, y, 0.068), F.P(u1 - sw, y + 0.05, 0.03), F.P(u0 + sw, y + 0.05, 0.03)], m, add(F.n, (0, -1.2, 0)))
                y += 0.055
        else:   # raised fielded panels
            for y0, y1 in ((h.v + sw * 1.5 + 0.04, h.v + hh * 0.48 - 0.04), (h.v + hh * 0.48 + sw + 0.04, h.v + hh - sw - 0.04)):
                F.box(u0 + sw + 0.04, u1 - sw - 0.04, y0, y1, 0.05, 0.062, m, skip=('k',))


def door(F, h, depth, leaves=1, fanlight=None, m='door', surround=None, steps=0, step_w=None, step_d=0.35, ground=None):
    """A panelled door in its opening, with optional fanlight or transom, surround and steps."""
    dd = -depth + 0.12
    fw = 0.08
    top = h.vt
    F.box(h.u0, h.u0 + fw, h.v, top, dd - 0.06, dd + 0.05, 'trim'); F.box(h.u1 - fw, h.u1, h.v, top, dd - 0.06, dd + 0.05, 'trim')
    leaf_top = top - (0.5 if fanlight == 'transom' else 0) - (0 if h.arch else fw)
    if fanlight == 'transom':
        F.box(h.u0 + fw, h.u1 - fw, leaf_top, leaf_top + 0.07, dd - 0.06, dd + 0.05, 'trim')
        sash(F, h.u0 + fw, h.u1 - fw, leaf_top + 0.07, top - fw, dd, 4, 1)
    if not h.arch: F.box(h.u0 + fw, h.u1 - fw, top - fw, top, dd - 0.06, dd + 0.05, 'trim')
    lw = (h.w - 2 * fw) / leaves
    for i in range(leaves):
        u0 = h.u0 + fw + i * lw; u1 = u0 + lw
        F.box(u0, u1, h.v, leaf_top, dd - 0.05, dd, m, skip=('k',))
        st = 0.1
        F.box(u0, u0 + st, h.v, leaf_top, dd, dd + 0.02, m, skip=('k', 'b'))
        F.box(u1 - st, u1, h.v, leaf_top, dd, dd + 0.02, m, skip=('k', 'b'))
        H = leaf_top - h.v
        rails = [h.v, h.v + H * 0.22, h.v + H * 0.55, leaf_top - 0.1]
        for y in rails:
            F.box(u0 + st, u1 - st, y, min(y + 0.1, leaf_top), dd, dd + 0.02, m, skip=('k', 'l', 'r'))
        cols = 2 if leaves == 1 else 1
        pw = (u1 - u0 - 2 * st - (cols - 1) * 0.08) / cols
        for c in range(cols):
            pu0 = u0 + st + c * (pw + 0.08)
            if c == 1: F.box(pu0 - 0.08, pu0, h.v, leaf_top, dd, dd + 0.02, m, skip=('k', 't', 'b'))
            for y0, y1 in ((rails[0] + 0.1, rails[1]), (rails[1] + 0.1, rails[2]), (rails[2] + 0.1, rails[3])):
                F.box(pu0 + 0.04, pu0 + pw - 0.04, y0 + 0.04, y1 - 0.04, dd, dd + 0.014, m, skip=('k',))
    if h.arch: fan(F, h, dd, 'trim', spokes=6)
    F.box(h.u0 - 0.05, h.u1 + 0.05, h.v - 0.06, h.v, -depth, 0.08, 'stone')   # threshold
    if surround == 'pediment':          # pilasters, entablature and pediment
        pw = 0.2
        for uu in (h.u0 - 0.12 - pw, h.u1 + 0.12):
            F.box(uu, uu + pw, h.v, top + 0.05, 0, 0.1, 'trim', skip=('k',))
            F.box(uu - 0.03, uu + pw + 0.03, h.v, h.v + 0.2, 0, 0.13, 'trim', skip=('k',))
        e0 = top + 0.05
        F.box(h.u0 - 0.4, h.u1 + 0.4, e0, e0 + 0.32, 0, 0.12, 'trim', skip=('k',))
        F.box(h.u0 - 0.48, h.u1 + 0.48, e0 + 0.32, e0 + 0.42, 0, 0.26, 'trim', skip=('k',))
        pa = e0 + 0.42; apex = pa + (h.w + 0.96) * 0.28
        F.b.face([F.P(h.u0 - 0.45, pa, 0.12), F.P(h.u1 + 0.45, pa, 0.12), F.P(h.u, apex - 0.05, 0.12)], 'trim', F.n)
        F.bar((h.u0 - 0.5, pa), (h.u, apex), 0.12, 0, 0.27, 'trim'); F.bar((h.u, apex), (h.u1 + 0.5, pa), 0.12, 0, 0.27, 'trim')
    elif surround == 'casing':
        F.box(h.u0 - 0.12, h.u0, h.v, top, 0, 0.04, 'trim', skip=('k',)); F.box(h.u1, h.u1 + 0.12, h.v, top, 0, 0.04, 'trim', skip=('k',))
        F.box(h.u0 - 0.12, h.u1 + 0.12, top, top + 0.14, 0, 0.04, 'trim', skip=('k',))
        F.box(h.u0 - 0.18, h.u1 + 0.18, top + 0.14, top + 0.22, 0, 0.11, 'trim', skip=('k',))
    elif surround == 'arch':
        dress(F, h, 'arch', False)
    if steps:
        g = ground if ground is not None else h.v - steps * 0.18
        rise = (h.v - g) / steps
        sw = step_w or h.w + 0.5
        for i in range(steps):
            F.box(h.u - sw / 2 - i * 0.1, h.u + sw / 2 + i * 0.1, g - 0.25, h.v - 0.06 - i * rise, 0, step_d * (i + 1), 'stone', skip=('k', 'b'))


# ------------------------------------------------------------------ cornices
def cornice(b, p0, p1, y, inside, over=0.42, ext=None, modillions=True, dentils=True, m='trim'):
    """Classical eaves cornice along the top of the wall from p0 to p1 (world x, z).
    `inside` is any point inside the building; `ext` extends the ends (number or pair)."""
    F, L = Frame.between(b, (p0[0], 0, p0[1]), (p1[0], 0, p1[1]))
    if F.u_of(inside[0], inside[1]) is not None and dot(F.n, (inside[0] - p0[0], 0, inside[1] - p0[1])) > 0:
        F, L = Frame.between(b, (p1[0], 0, p1[1]), (p0[0], 0, p0[1]))
        if isinstance(ext, tuple): ext = (ext[1], ext[0])
    e = over + 0.1 if ext is None else ext
    e0, e1 = e if isinstance(e, tuple) else (e, e)
    u0, u1 = -e0, L + e1
    F.box(u0, u1, y - 0.3, y, 0, 0.04, m, skip=('k', 't'))                 # frieze board
    F.box(u0, u1, y - 0.07, y, 0.04, 0.1, m, skip=('k', 't'))              # bed mould
    F.box(u0, u1, y, y + 0.07, 0, over, m, skip=('k', 't'))                 # soffit
    F.box(u0, u1, y + 0.07, y + 0.27, over - 0.04, over, m, skip=('k', 't'))   # fascia
    F.b.face([F.P(u0, y + 0.27, over), F.P(u1, y + 0.27, over), F.P(u1, y + 0.4, over + 0.11), F.P(u0, y + 0.4, over + 0.11)], m, F.D(0, 1, 1))
    F.b.face([F.P(u0, y + 0.4, over + 0.11), F.P(u1, y + 0.4, over + 0.11), F.P(u1, y + 0.4, 0), F.P(u0, y + 0.4, 0)], m, UP)
    for uu, s in ((u0, -1), (u1, 1)):
        F.b.face([F.P(uu, y + 0.07, 0), F.P(uu, y + 0.07, over), F.P(uu, y + 0.27, over), F.P(uu, y + 0.4, over + 0.11), F.P(uu, y + 0.4, 0)], m, F.D(s, 0, 0))
    if dentils:
        u = u0 + 0.12
        while u < u1 - 0.12:
            F.box(u, u + 0.06, y - 0.2, y - 0.08, 0.04, 0.12, m, skip=('k', 't'))
            u += 0.13
    if modillions:
        u = u0 + 0.25
        while u < u1 - 0.2:
            F.box(u, u + 0.09, y - 0.1, y, 0.1, over - 0.06, m, skip=('k', 't'))
            u += 0.4


# ------------------------------------------------------------------ roofs
def roof_plane(b, O, U, S, poly, m='shingle', exposure=0.17, lift=0.028, split=False, underside=None):
    """A roof plane laid in shingle courses. O is a world point on the eave line,
    U runs along the eave, S up the slope; poly is a convex outline in (u, s)."""
    U = unit(U); S = unit(S); N = cross(U, S)
    if N[1] < 0: N = mul(N, -1)
    W = lambda u, s, d=0.0: add(add(add(O, mul(U, u)), mul(S, s)), mul(N, d))
    b.face([W(u, s, -0.006) for u, s in poly], m, N)
    if underside: b.face([W(u, s, -0.08) for u, s in poly], underside, mul(N, -1))
    smin = min(s for _, s in poly); smax = max(s for _, s in poly)
    s0 = smin; k = 0
    while s0 < smax - 1e-4:
        s1 = min(s0 + exposure, smax)
        band = clip(clip(poly, lambda p: p[1] - s0), lambda p: s1 - p[1])
        if len(band) >= 3:
            if split:
                umin = min(u for u, _ in band); umax = max(u for u, _ in band)
                cuts = [umin]; u = umin + (0.12 if k % 2 else 0.24)
                while u < umax - 0.06:
                    cuts.append(u); u += rng.uniform(0.17, 0.32)
                cuts.append(umax)
                pieces = [(clip(clip(band, lambda p, a=a: p[0] - a), lambda p, c=c: c - p[0]), rng.uniform(0.55, 1.3)) for a, c in zip(cuts, cuts[1:])]
            else:
                pieces = [(band, 1.0)]
            for pc, lf in pieces:
                if len(pc) < 3: continue
                L = lift * lf
                dz = lambda s: L * (s1 - s) / max(s1 - s0, 1e-6)
                b.face([W(u, s, dz(s)) for u, s in pc], m, N)
                low = [p for p in pc if abs(p[1] - s0) < 1e-6]
                if len(low) == 2 and abs(low[0][0] - low[1][0]) > 1e-4:
                    (ua, _), (ub, _) = sorted(low)
                    b.face([W(ua, s0, 0), W(ub, s0, 0), W(ub, s0, L), W(ua, s0, L)], m, mul(S, -1))
        s0 = s1; k += 1


def plane_from(b, e0, e1, ridge_seg, m='shingle', **kw):
    """Roof plane from the eave edge e0->e1 up to a ridge segment (r0, r1), or an apex when r0 == r1."""
    r0, r1 = ridge_seg
    U = unit(sub(e1, e0))
    v = sub(mul(add(r0, r1), 0.5), e0); S = unit(sub(v, mul(U, dot(v, U))))
    uv = lambda p: (dot(sub(p, e0), U), dot(sub(p, e0), S))
    poly = [uv(e0), uv(e1), uv(r1), uv(r0)] if length(sub(r0, r1)) > 1e-6 else [uv(e0), uv(e1), uv(r0)]
    roof_plane(b, e0, U, S, poly, m, **kw)


def hip_roof(b, x0, x1, z0, z1, ye, yr, over, m='shingle', **kw):
    X0, X1, Z0, Z1 = x0 - over, x1 + over, z0 - over, z1 + over
    run = min(X1 - X0, Z1 - Z0) / 2
    if X1 - X0 >= Z1 - Z0:
        zm = (Z0 + Z1) / 2; a, c = (X0 + run, yr, zm), (X1 - run, yr, zm)
    else:
        xm = (X0 + X1) / 2; a, c = (xm, yr, Z0 + run), (xm, yr, Z1 - run)
    C = [(X0, ye, Z0), (X1, ye, Z0), (X1, ye, Z1), (X0, ye, Z1)]
    near = lambda p: a if math.hypot(p[0] - a[0], p[2] - a[2]) <= math.hypot(p[0] - c[0], p[2] - c[2]) else c
    for i in range(4):
        e0, e1 = C[i], C[(i + 1) % 4]
        plane_from(b, e0, e1, (near(e0), near(e1)), m, **kw)
    if length(sub(a, c)) > 1e-6: b.cap_line(a, c, m)
    for p in C: b.cap_line(p, near(p), m, w=0.07, h=0.04)


def gable_roof(b, x0, x1, z0, z1, ye, yr, axis, over=0.35, rake=0.25, m='shingle', **kw):
    """Gable roof with its ridge along `axis`."""
    if axis == 'z':
        xm = (x0 + x1) / 2; Z0, Z1 = z0 - rake, z1 + rake
        for xe in (x0 - over, x1 + over):
            plane_from(b, (xe, ye, Z0), (xe, ye, Z1), ((xm, yr, Z0), (xm, yr, Z1)), m, **kw)
        b.cap_line((xm, yr, Z0), (xm, yr, Z1), m)
    else:
        zm = (z0 + z1) / 2; X0, X1 = x0 - rake, x1 + rake
        for ze in (z0 - over, z1 + over):
            plane_from(b, (X0, ye, ze), (X1, ye, ze), ((X0, yr, zm), (X1, yr, zm)), m, **kw)
        b.cap_line((X0, yr, zm), (X1, yr, zm), m)


def rake_boards(b, F, L, ye, ridge, over, out=0.0, m='trim'):
    """Barge boards up both slopes of a gable on wall frame F (u 0..L), `out` beyond the face."""
    for ue in (-over, L + over):
        F.bar((ue, ye - 0.02), (L / 2, ridge + 0.02), 0.22, out, out + 0.1, m)


def chimney(b, x0, x1, z0, z1, y0, y1, m='brick', flues=1):
    """Brick stack with a corbelled cap."""
    CHIMNEYS.append([round((x0 + x1) / 2, 2), round(y1, 2), round((z0 + z1) / 2, 2)])
    b.box(x0, x1, y0, y1 - 0.42, z0, z1, m, skip=('-y', '+y'))
    for o, h0, h1 in ((0.04, y1 - 0.42, y1 - 0.34), (0.08, y1 - 0.34, y1 - 0.26), (0.04, y1 - 0.26, y1 - 0.18)):
        b.box(x0 - o, x1 + o, h0, h1, z0 - o, z1 + o, m)
    b.box(x0, x1, y1 - 0.18, y1, z0, z1, m, skip=('-y', '+y'))
    lx, lz = x1 - x0, z1 - z0
    rim = []
    for i in range(flues):
        if lx >= lz:
            fx0 = x0 + 0.1 + i * (lx - 0.1) / flues; fx1 = fx0 + (lx - 0.1) / flues - 0.1; fz0, fz1 = z0 + 0.1, z1 - 0.1
        else:
            fz0 = z0 + 0.1 + i * (lz - 0.1) / flues; fz1 = fz0 + (lz - 0.1) / flues - 0.1; fx0, fx1 = x0 + 0.1, x1 - 0.1
        b.box(fx0, fx1, y1 - 0.4, y1, fz0, fz1, 'dark', skip=('+y',))
        rim.append((fx0, fx1, fz0, fz1))
    b.box(x0, x1, y1 - 0.01, y1, z0, z1, m, skip=('-y', '-x', '+x', '-z', '+z'))


def end_chimney(b, F, u, g, sh, top, wb=1.9, ws=1.1, proj=0.9, m='brick'):
    """Exterior end chimney against a gable wall: wide base, sloped weatherings,
    a slimmer stack and a corbelled cap."""
    F.box(u - wb / 2, u + wb / 2, g, sh, 0, proj, m, skip=('k', 't'))
    ds = proj - 0.15
    P = F.P
    b.face([P(u - wb / 2, sh, proj), P(u + wb / 2, sh, proj), P(u + ws / 2, sh + 0.55, ds), P(u - ws / 2, sh + 0.55, ds)], m, F.D(0, 1, 1))
    b.face([P(u - wb / 2, sh, 0), P(u - wb / 2, sh, proj), P(u - ws / 2, sh + 0.55, ds), P(u - ws / 2, sh + 0.55, 0)], m, F.D(-1, 1, 0))
    b.face([P(u + wb / 2, sh, proj), P(u + wb / 2, sh, 0), P(u + ws / 2, sh + 0.55, 0), P(u + ws / 2, sh + 0.55, ds)], m, F.D(1, 1, 0))
    a, c = P(u - ws / 2, 0, 0), P(u + ws / 2, 0, ds)
    chimney(b, min(a[0], c[0]), max(a[0], c[0]), min(a[2], c[2]), max(a[2], c[2]), sh + 0.55, top, m)


def water_table(F, u0, u1, g, y, m='brick_rubbed'):
    F.box(u0 - 0.05, u1 + 0.05, g, y, 0, 0.05, m, skip=('k', 't'))
    F.b.face([F.P(u0 - 0.05, y, 0.05), F.P(u1 + 0.05, y, 0.05), F.P(u1 + 0.05, y + 0.06, 0), F.P(u0 - 0.05, y + 0.06, 0)], m, F.D(0, 1, 1))


def weathervane(b, x, z, y, h=1.1):
    b.ring(x, z, [(0.07, y), (0.11, y + 0.06), (0.11, y + 0.14), (0.07, y + 0.2), (0.001, y + 0.24)], 10, 'gilt', cap=False)
    b.box(x - 0.015, x + 0.015, y + 0.2, y + h, z - 0.015, z + 0.015, 'gilt')
    b.box(x - 0.2, x + 0.2, y + h * 0.55, y + h * 0.55 + 0.02, z - 0.01, z + 0.01, 'gilt')
    b.box(x - 0.01, x + 0.01, y + h * 0.55, y + h * 0.55 + 0.02, z - 0.2, z + 0.2, 'gilt')
    yb = y + h * 0.82
    for n in ((0, 0, 1), (0, 0, -1)):   # arrow with a banner tail
        b.face([(x - 0.45, yb, z), (x + 0.3, yb, z), (x + 0.3, yb + 0.16, z), (x - 0.25, yb + 0.16, z), (x - 0.4, yb + 0.25, z)], 'gilt', n)
        b.face([(x + 0.3, yb - 0.06, z), (x + 0.5, yb + 0.08, z), (x + 0.3, yb + 0.22, z)], 'gilt', n)


def rect_walls(b, x0, x1, z0, z1):
    """Frames for the four walls of a rectangle, each with u running left to right seen from outside."""
    return {
        '+x': Frame(b, (x1, 0, z1), (1, 0, 0)),
        '-x': Frame(b, (x0, 0, z0), (-1, 0, 0)),
        '+z': Frame(b, (x0, 0, z1), (0, 0, 1)),
        '-z': Frame(b, (x1, 0, z0), (0, 0, -1)),
    }


def wall_len(side, x0, x1, z0, z1):
    return (z1 - z0) if side in ('+x', '-x') else (x1 - x0)


def cornice_loop(b, pts, y, inside, **kw):
    for p0, p1 in zip(pts, pts[1:] + pts[:1]):
        cornice(b, p0, p1, y, inside, **kw)


# =============================================================== the Courthouse
def courthouse():
    b = Builder('courthouse')
    g, fl = 2.2, 2.95                      # ground and floor levels
    x0, x1, z0, z1 = -160.8, -154.8, 261.9, 274.7
    wx0, wz0, wz1 = -166.8, 265.3, 271.1   # rear wing, the stem of the T
    yt = 6.9                               # top of the brick walls
    zc = 268.3
    depth = 0.45
    arched = lambda u: Hole(u, g + 1.05, 1.1, 3.2, arch=True)
    def finish(F, L, hs):
        wall(F, 0, L, g - 0.3, yt, 'brick', hs, depth)
        for h in hs:
            window(F, h, depth, cols=3, rows=(4, 4), head='arch', shutters='panel', shutter_m='shutter_white')
        water_table(F, 0, L, g - 0.3, g + 0.75)
    W = rect_walls(b, x0, x1, z0, z1)
    # front: four arched windows with open white shutters, arched double door in the middle
    F = W['+x']
    dh = Hole(F.u_of(x1, zc), fl, 1.45, 3.4, arch=True)
    hs = [arched(F.u_of(x1, z)) for z in (263.3, 265.7, 270.9, 273.3)]
    wall(F, 0, z1 - z0, g - 0.3, yt, 'brick', hs + [dh], depth)
    for h in hs: window(F, h, depth, cols=3, rows=(4, 4), head='arch', shutters='panel', shutter_m='shutter_white')
    door(F, dh, depth, leaves=2, surround='arch', m='door_white', fanlight='arch')
    water_table(F, 0, z1 - z0, g - 0.3, g + 0.75)
    for side in ('+z', '-z'):
        F = W[side]; zz = z1 if side == '+z' else z0
        finish(F, x1 - x0, [arched(F.u_of(x, zz)) for x in (-159.3, -156.3)])
    F = W['-x']
    finish(F, z1 - z0, [arched(F.u_of(x0, z)) for z in (263.3, 273.3)])
    Wg = rect_walls(b, wx0, x0 + 0.3, wz0, wz1)
    for side in ('+z', '-z'):
        F = Wg[side]; zz = wz1 if side == '+z' else wz0
        finish(F, x0 + 0.3 - wx0, [arched(F.u_of(x, zz)) for x in (-165.2, -162.5)])
    F = Wg['-x']
    finish(F, wz1 - wz0, [arched(F.u_of(wx0, zc))])
    # modillion cornice all round the T
    ring = [(x1, z1), (x1, z0), (x0, z0), (x0, wz0), (wx0, wz0), (wx0, wz1), (x0, wz1), (x0, z1)]
    exts = [(0.52, 0.52), (0.52, 0.52), (0.52, 0.0), (0.0, 0.52), (0.52, 0.52), (0.52, 0.0), (0.0, 0.52), (0.52, 0.52)]
    for (p0, p1), e in zip(zip(ring, ring[1:] + ring[:1]), exts):
        inside = (-158.0, 268.3) if min(p0[0], p1[0]) >= x0 - 1e-6 else (-163.5, 268.2)
        cornice(b, p0, p1, yt, inside, over=0.42, ext=e)
    ye = yt + 0.4; ov = 0.53
    hip_roof(b, x0, x1, z0, z1, ye, 9.55, ov, split=True)
    hip_roof(b, wx0, x0 - 0.8, wz0, wz1, ye, 9.1, ov, split=True)
    # the pediment, cantilevered out over the steps on its entablature, with no columns
    pz0, pz1, px = 266.05, 270.55, x1 + 2.2
    L = pz1 - pz0
    eb = 6.3                                           # underside of the entablature
    Fp = Frame(b, (px, 0, pz1), (1, 0, 0))             # its front, u from pz1 toward pz0
    Fp.box(0, L, eb, yt, -0.35, 0, 'trim')
    Fp.box(-0.02, L + 0.02, eb, eb + 0.16, 0, 0.05, 'trim', skip=('k',))
    for zz, n in ((pz0, (0, 0, -1)), (pz1, (0, 0, 1))):
        Fs = Frame(b, (x1, 0, zz), n)
        a, c = Fs.u_of(x1, zz), Fs.u_of(px, zz)
        Fs.box(min(a, c), max(a, c), eb, yt, -0.35, 0, 'trim')
        Fs.box(min(a, c), max(a, c), eb, eb + 0.16, 0, 0.05, 'trim', skip=('k',))
    b.face([(x1, eb, pz0), (px, eb, pz0), (px, eb, pz1), (x1, eb, pz1)], 'trim', DOWN)   # soffit
    pin = (x1 + 1.0, zc)
    cornice(b, (px, pz0), (px, pz1), yt, pin, over=0.42, ext=0.52)
    cornice(b, (x1, pz0), (px, pz0), yt, pin, over=0.42, ext=(0.0, 0.52))
    cornice(b, (px, pz1), (x1, pz1), yt, pin, over=0.42, ext=(0.52, 0.0))
    ya = yt + 0.4
    apex = ya + (L + 1.1) * 0.34
    Fp.b.face([Fp.P(-0.4, ya), Fp.P(L + 0.4, ya), Fp.P(L / 2, apex - 0.1)], 'trim', Fp.n)       # tympanum
    for a, c in (((-0.62, ya - 0.02), (L / 2, apex)), ((L / 2, apex), (L + 0.62, ya - 0.02))):     # raking cornices
        Fp.bar((a[0], a[1] - 0.1), (c[0], c[1] - 0.1), 0.2, 0.0, 0.42, 'trim')
        Fp.bar((a[0], a[1] - 0.26), (c[0], c[1] - 0.26), 0.1, 0.0, 0.2, 'trim')
        for k in range(1, 8):
            t = k / 8; mu, mv = a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t
            Fp.box(mu - 0.045, mu + 0.045, mv - 0.33, mv - 0.21, 0.0, 0.34, 'trim', skip=('k',))
    lh = Hole(L / 2, ya + 0.14, 1.3, 0.65, arch=True)     # lunette
    fan(Fp, lh, 0.03, 'trim', spokes=6, fw=0.08)
    a, o = arc_pts(lh, lh.r), arc_pts(lh, lh.r + 0.12)
    for k in range(ARC):
        b.face([Fp.P(*a[k], 0.06), Fp.P(*o[k], 0.06), Fp.P(*o[k + 1], 0.06), Fp.P(*a[k + 1], 0.06)], 'trim', Fp.n)
    Fp.box(lh.u0 - 0.12, lh.u1 + 0.12, lh.v - 0.08, lh.v, 0, 0.08, 'trim')
    gable_roof(b, x1 - 2.2, px + 0.62, pz0, pz1, ya, apex + 0.05, 'x', over=0.53, rake=0.0, split=True, underside='trim')
    # broad stone steps under the pediment
    for i in range(4):
        b.box(x1, x1 + 0.55 + 0.42 * (i + 1), g - 0.3, fl - 0.19 * i, pz0 - 0.4 - 0.15 * i, pz1 + 0.4 + 0.15 * i, 'stone')
    xm = (x0 + x1) / 2
    for zz in (264.35, 272.25):
        chimney(b, xm - 0.5, xm + 0.5, zz - 0.42, zz + 0.42, 8.6, 11.3, flues=2)
    cupola(b, xm, zc, 9.25)
    return b


def cupola(b, cx, cz, y):
    """Octagonal cupola: square curb, arched louvred drum, cornice, bell dome and vane."""
    b.box(cx - 0.95, cx + 0.95, y - 0.4, y + 0.55, cz - 0.95, cz + 0.95, 'trim', skip=('-y',))
    b.box(cx - 1.03, cx + 1.03, y + 0.55, y + 0.68, cz - 1.03, cz + 1.03, 'trim')
    ap = 0.72; R = ap / math.cos(math.pi / 8); y0, y1 = y + 0.68, y + 2.05
    for k, F, L in oct_faces(b, cx, cz, ap):
        h = Hole(L / 2, y0 + 0.22, 0.36, 1.0, arch=True)
        wall(F, 0, L, y0, y1, 'trim', [h], 0.12)
        yy = h.v + 0.05
        while yy < h.vt:
            b.face([F.P(h.u0, yy, -0.02), F.P(h.u1, yy, -0.02), F.P(h.u1, yy + 0.07, -0.09), F.P(h.u0, yy + 0.07, -0.09)], 'trim', add(F.n, (0, -1.2, 0)))
            yy += 0.08
        F.box(-0.02, 0.08, y0, y1, 0, 0.04, 'trim', skip=('k',))   # corner pilaster
    b.ring(cx, cz, [(R + 0.05, y1), (R + 0.05, y1 + 0.12), (R + 0.16, y1 + 0.2), (R + 0.16, y1 + 0.26)], 8, 'trim', rot=math.pi / 8, cap=False)
    prof = [(R + 0.1, y1 + 0.26), (R + 0.04, y1 + 0.4), (R - 0.1, y1 + 0.6), (R * 0.64, y1 + 0.82), (R * 0.38, y1 + 0.98), (0.2, y1 + 1.12), (0.12, y1 + 1.3)]
    b.ring(cx, cz, prof, 16, 'lead', cap=True)
    weathervane(b, cx, cz, y1 + 1.3, 1.3)


# =============================================================== Bruton Parish Church
def church():
    b = Builder('church')
    g = 2.4
    cx = -163.85
    nx0, nx1, nz0, nz1 = cx - 2.8, cx + 2.8, 285.6, 299.4
    tx0, tx1, tz0, tz1 = -169.3, -158.4, 288.4, 294.0
    yt, ridge = 7.0, 10.3
    ye, over = yt + 0.4, 0.5
    depth = 0.5
    win = lambda u: Hole(u, g + 1.0, 1.15, 3.0, arch=True)
    def finish(F, L, hs, top=None):
        wall(F, 0, L, g - 0.3, yt, 'brick', hs, depth, top=top)
        for h in hs: window(F, h, depth, cols=3, rows=(5, 5), head='arch')
        water_table(F, 0, L, g - 0.3, g + 0.8)
    gt = lambda L: gable_top(L, yt, ye, ridge, over, L / 2)
    for side, x in (('+x', nx1), ('-x', nx0)):          # nave sides beyond the transepts
        n = (1, 0, 0) if side == '+x' else (-1, 0, 0)
        for za, zb, zs in ((nz0, tz0, (286.95,)), (tz1, nz1, (295.9, 298.1))):
            F = Frame(b, (x, 0, zb if side == '+x' else za), n)
            finish(F, zb - za, [win(F.u_of(x, z)) for z in zs])
    for side, x in (('+x', tx1), ('-x', tx0)):          # transept ends, with a round window in the gable
        n = (1, 0, 0) if side == '+x' else (-1, 0, 0)
        F = Frame(b, (x, 0, tz1 if side == '+x' else tz0), n); L = tz1 - tz0
        finish(F, L, [win(F.u_of(x, z)) for z in (289.8, 292.6)], gt(L))
        oculus(F, L / 2, yt + 1.3, 0.4)
        rake_boards(b, F, L, ye, ridge, over, 0.3)
    for side, z in (('+z', tz1), ('-z', tz0)):          # transept sides
        n = (0, 0, 1) if side == '+z' else (0, 0, -1)
        for xa, xb in ((tx0, nx0), (nx1, tx1)):
            F = Frame(b, (xa if side == '+z' else xb, 0, z), n)
            finish(F, xb - xa, [win((xb - xa) / 2)])
    F = Frame(b, (nx1, 0, nz0), (0, 0, -1)); L = nx1 - nx0   # east (chancel) end
    h = Hole(L / 2, g + 0.9, 1.5, 3.35, arch=True)
    wall(F, 0, L, g - 0.3, yt, 'brick', [h], depth, top=gt(L))
    window(F, h, depth, cols=4, rows=(6, 6), head='arch'); water_table(F, 0, L, g - 0.3, g + 0.8)
    oculus(F, L / 2, yt + 1.35, 0.4)
    rake_boards(b, F, L, ye, ridge, over, 0.3)
    F = Frame(b, (nx0, 0, nz1), (0, 0, 1))                   # west end, mostly behind the tower
    wall(F, 0, L, g - 0.3, yt, 'brick', [], depth, top=gt(L)); water_table(F, 0, L, g - 0.3, g + 0.8)
    rake_boards(b, F, L, ye, ridge, over, 0.3)
    inside = (cx, 291.2)
    for p0, p1 in (((nx1, tz1), (nx1, nz1)), ((nx1, nz0), (nx1, tz0)), ((nx0, nz1), (nx0, tz1)), ((nx0, tz0), (nx0, nz0)),
                   ((tx1, tz1), (nx1, tz1)), ((nx0, tz1), (tx0, tz1)), ((tx0, tz0), (nx0, tz0)), ((nx1, tz0), (tx1, tz0))):
        inner_end = lambda p: (p[0] in (nx0, nx1) and p[1] in (tz0, tz1))
        e = (0.0 if inner_end(p0) else 0.55, 0.0 if inner_end(p1) else 0.55)
        cornice(b, p0, p1, yt, inside, over=0.4, ext=e, dentils=False)
    gable_roof(b, nx0, nx1, nz0, nz1, ye, ridge, 'z', over=over, rake=0.3, split=True, underside='trim')
    gable_roof(b, tx0, tx1, tz0, tz1, ye, ridge - 0.05, 'x', over=over, rake=0.3, split=True, underside='trim')
    # the tower: three brick stages with string courses and arched openings
    T0, T1, Z0, Z1 = cx - 1.7, cx + 1.7, 299.3, 302.7
    tw = rect_walls(b, T0, T1, Z0, Z1)
    for side in ('+z', '+x', '-x', '-z'):
        F = tw[side]; L = 3.4
        hs, dh = [], None
        if side == '+z':
            dh = Hole(L / 2, g + 0.35, 1.3, 3.1, arch=True)
        elif side != '-z':
            hs.append(Hole(L / 2, 3.9, 0.9, 2.0, arch=True))
        hs += [Hole(L / 2, 6.95, 0.85, 1.85, arch=True), Hole(L / 2, 9.4, 0.8, 1.6, arch=True)]
        if side == '-z': hs = hs[-1:]
        wall(F, 0, L, g - 0.3, 11.3, 'brick', hs + ([dh] if dh else []), 0.6)
        for h in hs: window(F, h, 0.6, cols=2, rows=(3, 3), head='arch')
        if dh: door(F, dh, 0.6, leaves=2, surround='arch', fanlight='arch', steps=2, ground=g - 0.05, step_w=2.0)
        water_table(F, 0, L, g - 0.3, g + 0.8)
        for y in (6.5, 9.0):
            F.box(-0.08, L + 0.08, y - 0.08, y + 0.08, 0, 0.07, 'brick_rubbed', skip=('k',))
        F.box(-0.2, L + 0.2, 11.1, 11.3, 0, 0.18, 'trim', skip=('k',))
        F.box(-0.28, L + 0.28, 11.3, 11.42, 0, 0.26, 'trim', skip=('k', 't'))
    b.box(T0 - 0.28, T1 + 0.28, 11.42, 11.5, Z0 - 0.28, Z1 + 0.28, 'lead', skip=('-y',))
    tz = (Z0 + Z1) / 2
    # white wooden steeple: octagonal stage with windows, louvred belfry, shingled spire
    oct_stage(b, cx, tz, 1.4, 11.5, 13.9, 'window')
    c8 = 1 / math.cos(math.pi / 8)
    b.ring(cx, tz, [(1.45 * c8, 13.9), (1.62 * c8, 14.05), (1.62 * c8, 14.15), (1.0 * c8, 14.2)], 8, 'trim', rot=math.pi / 8, cap=False)
    oct_stage(b, cx, tz, 1.05, 14.15, 16.2, 'louver')
    b.ring(cx, tz, [(1.1 * c8, 16.2), (1.27 * c8, 16.35), (1.27 * c8, 16.45)], 8, 'trim', rot=math.pi / 8, cap=True)
    spire(b, cx, tz, 1.02, 16.45, 21.6)
    weathervane(b, cx, tz, 21.55, 1.2)
    return b


def oculus(F, u, v, r, m='trim'):
    n = 16
    pts = [(u + r * math.cos(2 * math.pi * k / n), v + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    out = [(u + (r + 0.22) * math.cos(2 * math.pi * k / n), v + (r + 0.22) * math.sin(2 * math.pi * k / n)) for k in range(n)]
    F.b.face([F.P(*p, 0.01) for p in pts], 'glass', F.n)
    for k in range(n):
        j = (k + 1) % n
        F.b.face([F.P(*pts[k], 0.05), F.P(*out[k], 0.05), F.P(*out[j], 0.05), F.P(*pts[j], 0.05)], 'brick_rubbed', F.n)
        F.b.face([F.P(*pts[k], 0.01), F.P(*pts[j], 0.01), F.P(*pts[j], 0.05), F.P(*pts[k], 0.05)], 'brick_rubbed',
                 F.D(u - (pts[k][0] + pts[j][0]) / 2, v - (pts[k][1] + pts[j][1]) / 2, 0))
    F.bar((u - r, v), (u + r, v), 0.035, 0.0, 0.04, m); F.bar((u, v - r), (u, v + r), 0.035, 0.0, 0.04, m)


def oct_faces(b, cx, cz, ap):
    R = ap / math.cos(math.pi / 8)
    for k in range(8):
        a = 2 * math.pi * k / 8
        c0 = (cx + R * math.cos(a + math.pi / 8), 0, cz + R * math.sin(a + math.pi / 8))
        c1 = (cx + R * math.cos(a - math.pi / 8), 0, cz + R * math.sin(a - math.pi / 8))
        F, L = Frame.between(b, c0, c1)
        if dot(F.n, (math.cos(a), 0, math.sin(a))) < 0: F, L = Frame.between(b, c1, c0)
        yield k, F, L


def oct_stage(b, cx, cz, ap, y0, y1, kind):
    for k, F, L in oct_faces(b, cx, cz, ap):
        if kind == 'window' and k % 2 == 0:
            h = Hole(L / 2, y0 + 0.55, 0.5, 1.15)
            wall(F, 0, L, y0, y1, 'trim', [h], 0.15)
            window(F, h, 0.15, cols=2, rows=(2, 2), sill='trim', casing=True)
        elif kind == 'window':
            wall(F, 0, L, y0, y1, 'trim')
            F.box(L / 2 - 0.22, L / 2 + 0.22, y0 + 0.45, y1 - 0.45, 0, 0.03, 'trim', skip=('k',))
            F.box(L / 2 - 0.16, L / 2 + 0.16, y0 + 0.51, y1 - 0.51, 0.03, 0.045, 'trim', skip=('k',))
        else:
            h = Hole(L / 2, y0 + 0.35, 0.5, 1.45, arch=True)
            wall(F, 0, L, y0, y1, 'trim', [h], 0.2)
            yy = h.v + 0.05
            while yy < h.vt:
                b.face([F.P(h.u0, yy, -0.02), F.P(h.u1, yy, -0.02), F.P(h.u1, yy + 0.08, -0.12), F.P(h.u0, yy + 0.08, -0.12)], 'trim', add(F.n, (0, -1.2, 0)))
                yy += 0.09
        F.box(-0.03, 0.09, y0, y1, 0, 0.05, 'trim', skip=('k',))
    c8 = 1 / math.cos(math.pi / 8)
    b.ring(cx, cz, [((ap + 0.02) * c8, y0), ((ap + 0.08) * c8, y0 + 0.12)], 8, 'trim', rot=math.pi / 8, cap=False)


def spire(b, cx, cz, ap, y0, y1, m='shingle'):
    R = ap / math.cos(math.pi / 8)
    corners = [(cx + R * math.cos(math.pi / 8 + 2 * math.pi * k / 8), y0, cz + R * math.sin(math.pi / 8 + 2 * math.pi * k / 8)) for k in range(8)]
    apex = (cx, y1, cz)
    for k in range(8):
        plane_from(b, corners[k], corners[(k + 1) % 8], (apex, apex), m, exposure=0.14, lift=0.02, split=True)
        b.cap_line(corners[k], apex, m, w=0.05, h=0.03)


# =============================================================== the Magazine
def magazine():
    b = Builder('magazine')
    g = 1.9
    cx, cz = -125.9, 263.6
    ap = 3.65                                    # apothem of the octagon
    yt = 7.3
    for k, F, L in oct_faces(b, cx, cz, ap):
        a = 2 * math.pi * k / 8
        if abs(math.cos(a) + 1) < 1e-6:          # west face: the door
            h = Hole(L / 2, g + 0.45, 1.15, 2.3)
            wall(F, 0, L, g - 0.3, yt, 'brick', [h], 0.6)
            door(F, h, 0.6, leaves=2, steps=2, ground=g - 0.05)
            dress(F, h, 'jack', False)
        elif k % 2 == 1:
            h = Hole(L / 2, 5.0, 0.6, 1.25, arch=True)
            wall(F, 0, L, g - 0.3, yt, 'brick', [h], 0.6)
            window(F, h, 0.6, cols=2, rows=(2, 2), head='arch')
        else:
            wall(F, 0, L, g - 0.3, yt, 'brick', [], 0.6)
        water_table(F, 0, L, g - 0.3, g + 0.75)
        c0, c1 = F.P(0, 0), F.P(L, 0)
        cornice(b, (c0[0], c0[2]), (c1[0], c1[2]), yt, (cx, cz), over=0.35, ext=0.16, modillions=False)
    R = (ap + 0.47) / math.cos(math.pi / 8)
    ye = yt + 0.4
    corners = [(cx + R * math.cos(math.pi / 8 + 2 * math.pi * k / 8), ye, cz + R * math.sin(math.pi / 8 + 2 * math.pi * k / 8)) for k in range(8)]
    apex = (cx, 11.4, cz)
    for k in range(8):
        plane_from(b, corners[k], corners[(k + 1) % 8], (apex, apex), 'shingle', split=True)
        b.cap_line(corners[k], apex, 'shingle', w=0.08, h=0.04)
    weathervane(b, cx, cz, 11.35, 1.3)
    # the high brick wall around it, with a gateway to the west
    Rw = 10.7
    rot = math.pi / 8
    for k in range(8):
        a0 = rot + 2 * math.pi * k / 8; a1 = rot + 2 * math.pi * (k + 1) / 8
        p0 = (cx + Rw * math.cos(a0), cz + Rw * math.sin(a0)); p1 = (cx + Rw * math.cos(a1), cz + Rw * math.sin(a1))
        mid = ((a0 + a1) / 2) % (2 * math.pi)
        segs = [(0, 1)]
        if abs(mid - math.pi) < 0.1: segs = [(0, 0.36), (0.64, 1)]
        for s0, s1 in segs:
            q0 = (p0[0] + (p1[0] - p0[0]) * s0, p0[1] + (p1[1] - p0[1]) * s0)
            q1 = (p0[0] + (p1[0] - p0[0]) * s1, p0[1] + (p1[1] - p0[1]) * s1)
            wall_seg(b, q0, q1, g - 0.3, 4.6, 0.4, 'brick')
            coping(b, q0, q1, 4.6, 0.52)
        if len(segs) > 1:
            for s in (0.36, 0.64):
                q = (p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s)
                b.box(q[0] - 0.42, q[0] + 0.42, g - 0.3, 5.3, q[1] - 0.42, q[1] + 0.42, 'brick', skip=('-y',))
                b.box(q[0] - 0.5, q[0] + 0.5, 5.3, 5.45, q[1] - 0.5, q[1] + 0.5, 'stone')
                b.ring(q[0], q[1], [(0.28, 5.45), (0.32, 5.65), (0.2, 5.9), (0.001, 5.95)], 12, 'stone', cap=False)
    return b


def wall_seg(b, p0, p1, y0, y1, th, m):
    F, L = Frame.between(b, (p0[0], 0, p0[1]), (p1[0], 0, p1[1]))
    F.box(-th / 2, L + th / 2, y0, y1, -th / 2, th / 2, m, skip=('b', 't'))


def coping(b, p0, p1, y, w, m='brick_rubbed'):
    F, L = Frame.between(b, (p0[0], 0, p0[1]), (p1[0], 0, p1[1]))
    F.box(-w / 2, L + w / 2, y, y + 0.1, -w / 2, w / 2, m, skip=('t',))
    for s in (1, -1):
        b.face([F.P(-w / 2, y + 0.1, s * w / 2), F.P(L + w / 2, y + 0.1, s * w / 2), F.P(L + w / 2, y + 0.3, 0), F.P(-w / 2, y + 0.3, 0)], m, F.D(0, 1, s))
    for uu, s in ((-w / 2, -1), (L + w / 2, 1)):
        b.face([F.P(uu, y + 0.1, -w / 2), F.P(uu, y + 0.1, w / 2), F.P(uu, y + 0.3, 0)], m, F.D(s, 0, 0))


# =============================================================== Peyton Randolph House
def randolph():
    b = Builder('randolph')
    g = 2.1
    x0, x1, z0, z1 = -161.0, -154.9, 221.3, 235.8
    fnd = g + 0.6
    yt = 8.05
    depth = 0.2
    W = rect_walls(b, x0, x1, z0, z1)
    bays = [222.45 + i * 1.95 for i in range(7)]
    lower = lambda u: Hole(u, fnd + 0.65, 0.95, 1.85)
    upper = lambda u: Hole(u, fnd + 3.35, 0.95, 1.55)
    for side, F in W.items():
        L = wall_len(side, x0, x1, z0, z1)
        edge = {'+x': x1, '-x': x0, '+z': z1, '-z': z0}[side]
        uf = (lambda z: F.u_of(edge, z)) if side in ('+x', '-x') else (lambda x: F.u_of(x, edge))
        dh = None
        if side == '+x':
            hs_up = [upper(uf(z)) for z in bays]
            hs_lo = [lower(uf(z)) for i, z in enumerate(bays) if i != 3]
            dh = Hole(uf(bays[3]), fnd + 0.1, 1.15, 2.35)
        elif side == '-x':
            zs = [223.4, 226.6, 230.5, 233.7]
            hs_up = [upper(uf(z)) for z in zs]; hs_lo = [lower(uf(z)) for z in zs]
        else:
            xs = [-159.6, -156.3]
            hs_up = [upper(uf(x)) for x in xs]; hs_lo = [lower(uf(x)) for x in xs]
        wall(F, 0, L, fnd, yt, 'clapboard_red', hs_up + hs_lo + ([dh] if dh else []), depth, reveal='trim')
        F.box(-0.05, L + 0.05, g - 0.3, fnd, 0, 0.06, 'brick', skip=('k', 't'))          # brick foundation
        F.box(-0.05, L + 0.05, fnd, fnd + 0.12, 0, 0.09, 'trim', skip=('k',))            # water table board
        F.box(-0.02, 0.14, fnd, yt, 0, 0.05, 'trim', skip=('k',)); F.box(L - 0.14, L + 0.02, fnd, yt, 0, 0.05, 'trim', skip=('k',))
        for h in hs_lo: window(F, h, depth, cols=3, rows=(3, 3), sill='trim', casing=True, shutters='panel')
        for h in hs_up: window(F, h, depth, cols=3, rows=(3, 3), sill='trim', casing=True, shutters='louver')
        if dh: door(F, dh, depth, surround='pediment', fanlight='transom', steps=3, ground=g - 0.05, step_w=1.8)
    cornice_loop(b, [(x1, z1), (x1, z0), (x0, z0), (x0, z1)], yt, ((x0 + x1) / 2, (z0 + z1) / 2), over=0.45, dentils=False)
    hip_roof(b, x0, x1, z0, z1, yt + 0.4, 10.9, 0.56, split=True)
    xm = (x0 + x1) / 2
    for zz in (223.4, 233.7):
        chimney(b, xm - 0.75, xm + 0.75, zz - 0.45, zz + 0.45, 8.2, 12.4, flues=2)
    return b


# =============================================================== ordinary houses
CLAP = {'Siding': 'clap_white', 'Siding 1': 'clap_red', 'Siding 2': 'clap_white', 'Siding 3': 'clap_sage',
        'Siding 4': 'clap_brown', 'Material_007': 'clap_ochre'}
SHUT = ['shutter', 'shutter', 'shutter_red', None, 'shutter']


def houses():
    b = Builder('houses')
    seen = []
    for i, hs in enumerate(WORLD['houses']):
        key = (round(hs['box'][0][0], 1), round(hs['box'][0][2], 1))
        if key in seen: continue
        seen.append(key)
        house(b, hs, i)
    return b


def house(b, hs, idx):
    r = random.Random(idx * 7 + 3)
    lo, hi = hs['box']
    x0, x1, z0, z1 = lo[0], hi[0], lo[2], hi[2]
    g = lo[1]
    side = hs['side'] or ('+x' if hs['ridge'] == 'z' else '+z')
    # the ridge runs parallel to the front, as on the Williamsburg streets
    ridge_axis = 'z' if side in ('+x', '-x') else 'x'
    depth_ = (x1 - x0) if ridge_axis == 'z' else (z1 - z0)
    front_len = (z1 - z0) if ridge_axis == 'z' else (x1 - x0)
    fnd = g + 0.5
    two = (hs['eave'] - g) > 4.2
    yt = fnd + (4.9 if two else 2.75)
    ye, over, rake = yt + 0.4, 0.42, 0.22
    ridge = ye + depth_ / 2 * (0.95 if two else 1.1)
    mat = CLAP.get(hs['mat'], 'clap_white')
    if hs['mat'] == 'Siding 2': mat = r.choice(['clap_white', 'clap_blue', 'clap_white'])
    shut = SHUT[idx % len(SHUT)]
    W = rect_walls(b, x0, x1, z0, z1)
    gables = ('+z', '-z') if ridge_axis == 'z' else ('+x', '-x')
    back = {'+x': '-x', '-x': '+x', '+z': '-z', '-z': '+z'}[side]
    def end_dist(s, c):
        e = W[s].P(wall_len(s, x0, x1, z0, z1) / 2, 0)
        return math.hypot(e[0] - c[0], e[2] - c[1])
    ch = hs['chimneys']
    chim = min(gables, key=lambda s: min(end_dist(s, c) for c in ch)) if ch else gables[r.randint(0, 1)]
    both = two and front_len > 6.5
    for s, F in W.items():
        L = wall_len(s, x0, x1, z0, z1)
        holes, wins, dh = [], [], None
        if s in (side, back):
            nb = (max(3, int(front_len / 1.7)) | 1) if s == side else max(2, int(front_len / 2.2))
            span = L - 1.3
            for k in range(nb):
                u = 0.65 + span * (k + 0.5) / nb
                if s == side and k == nb // 2:
                    dh = Hole(u, fnd + 0.05, 1.0, 2.25); holes.append(dh)
                else:
                    h = Hole(u, fnd + 0.6, 0.85, 1.65); holes.append(h); wins.append(h)
                if two:
                    h = Hole(u, fnd + 2.95, 0.85, 1.4); holes.append(h); wins.append(h)
        elif s != chim and not both:
            h = Hole(L / 2, fnd + 0.6, 0.8, 1.55); holes.append(h); wins.append(h)
            if ridge - ye > 1.6:
                gh = Hole(L / 2, ye + 0.15, 0.55, 0.85); holes.append(gh); wins.append(gh)
        top = gable_top(L, yt, ye, ridge, over, depth_ / 2) if s in gables else None
        wall(F, 0, L, fnd, yt, mat, [h for h in holes if h.top <= yt], 0.16, reveal='trim', top=top)
        high = [h for h in holes if h.top > yt]
        for h in high:   # openings in the gable triangle, framed by boards on the face
            F.box(h.u0, h.u1, h.v, h.top, -0.02, 0.0, 'dark', skip=('k', 'l', 'r', 't', 'b'))
        F.box(-0.05, L + 0.05, g - 0.4, fnd, 0, 0.05, 'brick', skip=('k', 't'))
        F.box(-0.04, L + 0.04, fnd, fnd + 0.11, 0, 0.08, 'trim', skip=('k',))
        F.box(-0.02, 0.13, fnd, yt, 0, 0.045, 'trim', skip=('k',)); F.box(L - 0.13, L + 0.02, fnd, yt, 0, 0.045, 'trim', skip=('k',))
        for h in wins:
            window(F, h, 0.16 if h.top <= yt else 0.0, cols=3 if h.w > 0.7 else 2, rows=(3, 3) if h.h > 1.2 else (2, 2), sill='trim', casing=True,
                   shutters=(('panel' if h.v < fnd + 1 else 'louver') if shut and s in (side, back) else None), shutter_m=shut or 'shutter')
        if dh:
            door(F, dh, 0.16, fanlight='transom', surround='casing', steps=2, ground=g - 0.05, step_w=1.6)
        if s in gables:
            rake_boards(b, F, L, ye, ridge, over, rake)
    eaves = [((x1, z0), (x1, z1)), ((x0, z1), (x0, z0))] if ridge_axis == 'z' else [((x1, z1), (x0, z1)), ((x0, z0), (x1, z0))]
    for p0, p1 in eaves:
        cornice(b, p0, p1, yt, ((x0 + x1) / 2, (z0 + z1) / 2), over=0.32, ext=rake + 0.02, modillions=False, dentils=False)
    gable_roof(b, x0, x1, z0, z1, ye, ridge, ridge_axis, over=over, rake=rake, underside='trim')
    if not two and front_len > 4.2:
        F = W[side]; L = wall_len(side, x0, x1, z0, z1)
        n = 2 if front_len < 7 else 3
        for k in range(n):
            dormer(b, F, L * (k + 0.5) / n, ye, ridge, over, depth_, mat)
    F = W[chim]; L = wall_len(chim, x0, x1, z0, z1)
    end_chimney(b, F, L / 2, g - 0.3, yt - (0.4 if two else 0.8), ridge + 0.9, wb=1.9 if two else 1.6, ws=1.05, proj=0.85)
    if both:
        other = [s for s in gables if s != chim][0]
        F = W[other]; L = wall_len(other, x0, x1, z0, z1)
        end_chimney(b, F, L / 2, g - 0.3, yt - 0.4, ridge + 0.9, wb=1.9, ws=1.05, proj=0.85)


def dormer(b, F, u, ye, ridge, over, depth_, mat):
    """Gabled dormer on the front slope: cheeks, a sash window and its own little roof."""
    pitch = (ridge - ye) / (depth_ / 2 + over)
    yroof = lambda d: ye + (over - d) * pitch          # main roof height at distance d out from the wall
    df = -0.25                                         # dormer face, set back from the wall line
    w = 1.15
    v0 = yroof(df) + 0.04
    v1 = v0 + 1.05
    vr = v1 + 0.42
    dback = over - (vr + 0.05 - ye) / pitch            # where the dormer ridge meets the main roof
    Fd = Frame(b, F.P(u - w / 2, 0, df), F.n)
    h = Hole(w / 2, v0 + 0.1, 0.66, 0.85)
    wall(Fd, 0, w, v0 - 0.2, v1, mat, [h], 0.1, reveal='trim', top=[(w + 0.02, v1), (w / 2, vr - 0.04), (-0.02, v1)])
    window(Fd, h, 0.1, cols=3, rows=(2, 2), sill='trim')
    Fd.box(-0.03, 0.08, v0 - 0.2, v1, 0, 0.04, 'trim', skip=('k',)); Fd.box(w - 0.08, w + 0.03, v0 - 0.2, v1, 0, 0.04, 'trim', skip=('k',))
    for s in (-1, 1):   # cheeks down to the main roof
        uu = u + s * w / 2
        b.face([F.P(uu, yroof(df) - 0.05, df), F.P(uu, v1, df), F.P(uu, v1, dback), F.P(uu, yroof(dback) - 0.05, dback)], mat, F.D(s, 0, 0))
    for s in (-1, 1):
        e0 = F.P(u + s * (w / 2 + 0.14), v1 - 0.06, df + 0.2); e1 = F.P(u + s * (w / 2 + 0.14), v1 - 0.06, dback)
        r0 = F.P(u, vr, df + 0.2); r1 = F.P(u, vr, dback)
        plane_from(b, e0, e1, (r0, r1), 'shingle', underside='trim', exposure=0.15)
    b.cap_line(F.P(u, vr, df + 0.2), F.P(u, vr, dback), 'shingle', w=0.07, h=0.04)
    for s in (-1, 1):
        Fd.bar((w / 2 + s * (w / 2 + 0.16), v1 - 0.08), (w / 2, vr + 0.02), 0.14, 0.1, 0.2, 'trim')


# =============================================================== export
bpy.ops.wm.read_factory_settings(use_empty=True)
for fn in (church, courthouse, magazine, randolph, houses):
    fn().build()
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=False, export_apply=True,
                          export_normals=True, export_materials='EXPORT',
                          export_texcoords=False, export_yup=True)
json.dump(CHIMNEYS, open(os.path.join(ROOT, 'assets', 'chimneys.json'), 'w'))
print('wrote', OUT, os.path.getsize(OUT) // 1024, 'KB,', len(CHIMNEYS), 'chimneys')
