#!/usr/bin/env python3
"""Rebuild the four tour landmarks in Blender for the remastered edition.

Run with Blender's Python module (pip install bpy) or `blender -b -P`:
    python3 web/tools/build-landmarks.py
Writes web/assets/landmarks.glb.

Each building is modelled in the page's world coordinates (three.js: x east,
y up, z south), on the footprint of the 2018 model it replaces, so the signs
and tour stops still line up. Proportions and details follow the real buildings
and the reference photos in the 2018 build:

  Bruton Parish Church  cruciform brick church, round-arched windows, west
                        tower of three brick stages with a white octagonal
                        wooden steeple and spire
  Courthouse (1770)     T-plan brick, hipped roof, arched windows with white
                        shutters, pedimented projection over the door, octagonal
                        cupola with dome and spire
  Magazine (1715)       octagonal brick powder house with a pyramidal roof,
                        inside a high octagonal brick wall
  Peyton Randolph House two-storey weatherboarded house in Spanish brown,
                        gable roof, brick end chimneys, sash windows with shutters

Surfaces are named by material ('brick', 'clapboard_red', 'shingle', 'trim',
'glass', 'door', 'shutter', 'stone', 'lead', 'gilt', 'dark'); the page maps them
to textured PBR materials with world-space (triplanar) projection, so no UVs are
needed beyond a simple planar set.
"""
import math, os
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'landmarks.glb')


class Builder:
    """Accumulates flat-shaded polygons per material, in three.js coordinates."""
    def __init__(self, name):
        self.name = name
        self.verts, self.faces, self.mats = [], [], []
        self.mat_names = []

    def mat(self, m):
        if m not in self.mat_names: self.mat_names.append(m)
        return self.mat_names.index(m)

    def poly(self, pts, m):
        base = len(self.verts)
        self.verts += [tuple(p) for p in pts]
        self.faces.append(tuple(range(base, base + len(pts))))
        self.mats.append(self.mat(m))

    def box(self, x0, x1, y0, y1, z0, z1, m, skip=()):
        x0, x1 = min(x0, x1), max(x0, x1); y0, y1 = min(y0, y1), max(y0, y1); z0, z1 = min(z0, z1), max(z0, z1)
        f = {
            '+x': [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
            '-x': [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
            '+y': [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)],
            '-y': [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            '+z': [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
            '-z': [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
        }
        for k, pts in f.items():
            if k not in skip: self.poly(pts, m)

    def prism(self, cx, cz, r, y0, y1, sides, m, rot=0.0, top=True, bottom=False, r1=None):
        """Regular polygon prism (or frustum when r1 is given)."""
        r1 = r if r1 is None else r1
        ring = lambda rr, y: [(cx + rr * math.cos(rot + 2 * math.pi * i / sides), y,
                               cz + rr * math.sin(rot + 2 * math.pi * i / sides)) for i in range(sides)]
        a, b = ring(r, y0), ring(r1, y1)
        for i in range(sides):
            j = (i + 1) % sides
            self.poly([a[j], a[i], b[i], b[j]], m)
        if top: self.poly(list(reversed(b)), m)
        if bottom: self.poly(a, m)

    def pyramid(self, cx, cz, r, y0, y1, sides, m, rot=0.0):
        a = [(cx + r * math.cos(rot + 2 * math.pi * i / sides), y0, cz + r * math.sin(rot + 2 * math.pi * i / sides)) for i in range(sides)]
        apex = (cx, y1, cz)
        for i in range(sides):
            self.poly([a[(i + 1) % sides], a[i], apex], m)

    def gable_roof(self, x0, x1, z0, z1, y0, ridge, axis, m, over=0.35, thick=0.18, end_m=None):
        """Gable roof whose ridge runs along `axis` ('x' or 'z'); gable ends get end_m walls."""
        if axis == 'z':
            xm = (x0 + x1) / 2; Z0, Z1 = z0 - over, z1 + over; X0, X1 = x0 - over, x1 + over
            drop = (ridge - y0) * over / ((x1 - x0) / 2)
            e = y0 - drop
            for s, xe in ((1, X1), (-1, X0)):
                top = [(xe, e, Z0), (xe, e, Z1), (xm, ridge, Z1), (xm, ridge, Z0)] if s > 0 else [(xe, e, Z1), (xe, e, Z0), (xm, ridge, Z0), (xm, ridge, Z1)]
                self.poly(top, m)
                under = [(p[0], p[1] - thick, p[2]) for p in top[::-1]]
                self.poly(under, 'trim')
                self.poly([(xe, e - thick, Z0), (xe, e - thick, Z1), (xe, e, Z1), (xe, e, Z0)] if s > 0 else [(xe, e - thick, Z1), (xe, e - thick, Z0), (xe, e, Z0), (xe, e, Z1)], 'trim')
            for zz, sgn in ((Z0, -1), (Z1, 1)):
                tri = [(X0, e, zz), (X1, e, zz), (xm, ridge, zz)]
                self.poly(tri if sgn > 0 else tri[::-1], 'trim')
            if end_m:
                for zz, sgn in ((z0, -1), (z1, 1)):
                    tri = [(x0, y0, zz), (x1, y0, zz), (xm, ridge - 0.02, zz)]
                    self.poly(tri if sgn > 0 else tri[::-1], end_m)
        else:
            zm = (z0 + z1) / 2; X0, X1 = x0 - over, x1 + over; Z0, Z1 = z0 - over, z1 + over
            drop = (ridge - y0) * over / ((z1 - z0) / 2)
            e = y0 - drop
            for s, ze in ((1, Z1), (-1, Z0)):
                top = [(X1, e, ze), (X0, e, ze), (X0, ridge, zm), (X1, ridge, zm)] if s > 0 else [(X0, e, ze), (X1, e, ze), (X1, ridge, zm), (X0, ridge, zm)]
                self.poly(top, m)
                self.poly([(p[0], p[1] - thick, p[2]) for p in top[::-1]], 'trim')
            for xx, sgn in ((X0, -1), (X1, 1)):
                tri = [(xx, e, Z1), (xx, e, Z0), (xx, ridge, zm)]
                self.poly(tri if sgn > 0 else tri[::-1], 'trim')
            if end_m:
                for xx, sgn in ((x0, -1), (x1, 1)):
                    tri = [(xx, y0, z1), (xx, y0, z0), (xx, ridge - 0.02, zm)]
                    self.poly(tri if sgn > 0 else tri[::-1], end_m)

    def hip_roof(self, x0, x1, z0, z1, y0, ridge, m, over=0.4):
        X0, X1, Z0, Z1 = x0 - over, x1 + over, z0 - over, z1 + over
        w, d = X1 - X0, Z1 - Z0
        run = min(w, d) / 2
        e = y0 - (ridge - y0) * over / (min(x1 - x0, z1 - z0) / 2)
        if w >= d:
            zm = (Z0 + Z1) / 2; a, b = (X0 + run, ridge, zm), (X1 - run, ridge, zm)
            self.poly([(X0, e, Z1), (X1, e, Z1), b, a], m)
            self.poly([(X1, e, Z0), (X0, e, Z0), a, b], m)
            self.poly([(X0, e, Z0), (X0, e, Z1), a], m)
            self.poly([(X1, e, Z1), (X1, e, Z0), b], m)
        else:
            xm = (X0 + X1) / 2; a, b = (xm, ridge, Z0 + run), (xm, ridge, Z1 - run)
            self.poly([(X1, e, Z0), (X1, e, Z1), b, a], m)
            self.poly([(X0, e, Z1), (X0, e, Z0), a, b], m)
            self.poly([(X1, e, Z1), (X0, e, Z1), b], m)
            self.poly([(X0, e, Z0), (X1, e, Z0), a], m)
        self.box(X0, X1, e - 0.22, e, Z0, Z1, 'trim', skip=('+y',))

    # ---- openings, in a wall's own frame -----------------------------------
    def frame(self, o, n):
        """F(u, v, d) -> world point on the wall through o with outward normal n:
        u runs along the wall (t = up x n, so faces built in F wind toward n),
        v is height, d is distance out from the wall."""
        t = (n[2], 0, -n[0])
        return lambda u, v, d: (o[0] + t[0] * u + n[0] * d, v, o[2] + t[2] * u + n[2] * d)

    def wall(self, axis, at, sign):
        """Frame for an axis-aligned wall at x=at (axis 'x') or z=at, facing +/-.
        Returns (F, U) where U(world coordinate along the wall) -> u."""
        n = (sign, 0, 0) if axis == 'x' else (0, 0, sign)
        o = (at, 0, 0) if axis == 'x' else (0, 0, at)
        t = (n[2], 0, -n[0])
        U = (lambda z: z * t[2]) if axis == 'x' else (lambda x: x * t[0])
        return self.frame(o, n), U

    def quad_on(self, F, u0, u1, v0, v1, d, m):
        self.poly([F(u0, v0, d), F(u1, v0, d), F(u1, v1, d), F(u0, v1, d)], m)

    def slab_on(self, F, u0, u1, v0, v1, d0, d1, m):
        """A small box on the wall (trim, muntins, sills), front at d1."""
        p = lambda u, v, d: F(u, v, d)
        c = [p(u0, v0, d0), p(u1, v0, d0), p(u1, v1, d0), p(u0, v1, d0), p(u0, v0, d1), p(u1, v0, d1), p(u1, v1, d1), p(u0, v1, d1)]
        for q in ((4, 5, 6, 7), (1, 0, 3, 2), (0, 4, 7, 3), (5, 1, 2, 6), (7, 6, 2, 3), (0, 1, 5, 4)):
            self.poly([c[i] for i in q], m)

    def sash_window(self, F, u, v, w, h, cols=3, rows=4, arch=False, shutters=False, lintel='brick'):
        """Sash window centred at u, sill at v: recessed glass, white frame, muntins, sill."""
        fw = 0.09; rec = -0.12
        arc_h = w / 2 if arch else 0
        body = h - arc_h
        # dark reveal + glass
        self.quad_on(F, u - w / 2, u + w / 2, v, v + body, rec - 0.05, 'dark')
        self.quad_on(F, u - w / 2 + fw, u + w / 2 - fw, v + fw, v + body, rec, 'glass')
        for s in (-1, 1):  # jambs
            self.slab_on(F, u + s * w / 2 - (fw if s > 0 else 0), u + s * w / 2 + (0 if s > 0 else fw), v, v + body, rec, 0.02, 'trim')
        self.slab_on(F, u - w / 2 - 0.06, u + w / 2 + 0.06, v - 0.08, v, -0.02, 0.1, 'stone' if lintel == 'brick' else 'trim')  # sill
        # meeting rail and muntins
        self.slab_on(F, u - w / 2, u + w / 2, v + body / 2 - 0.03, v + body / 2 + 0.03, rec, rec + 0.05, 'trim')
        for i in range(1, cols):
            x = u - w / 2 + w * i / cols
            self.slab_on(F, x - 0.015, x + 0.015, v, v + body, rec, rec + 0.035, 'trim')
        for j in range(1, rows):
            y = v + body * j / rows
            self.slab_on(F, u - w / 2, u + w / 2, y - 0.015, y + 0.015, rec, rec + 0.035, 'trim')
        if arch:
            segs = 10; r = w / 2; cy = v + body
            ring = [(u + r * math.cos(math.pi * k / segs), cy + r * math.sin(math.pi * k / segs)) for k in range(segs + 1)]
            ri = [(u + (r - fw) * math.cos(math.pi * k / segs), cy + (r - fw) * math.sin(math.pi * k / segs)) for k in range(segs + 1)]
            for k in range(segs):
                self.poly([F(*ri[k + 1], rec), F(*ri[k], rec), F(u, cy, rec)], 'glass')
                a, b, c2, d2 = ring[k + 1], ring[k], ri[k], ri[k + 1]
                self.poly([F(*b, 0.02), F(*a, 0.02), F(*d2, 0.02), F(*c2, 0.02)], 'trim')
                self.poly([F(*b, rec - 0.05), F(*a, rec - 0.05), F(*a, 0.0), F(*b, 0.0)], 'dark')
                # gauged-brick arch head
                ro = [(u + (r + 0.28) * math.cos(math.pi * kk / segs), cy + (r + 0.28) * math.sin(math.pi * kk / segs)) for kk in (k, k + 1)]
                self.poly([F(*ring[k], 0.01), F(*ro[0], 0.01), F(*ro[1], 0.01), F(*ring[k + 1], 0.01)][::-1], 'brick_rubbed')
        else:
            if lintel == 'brick':  # flat gauged-brick lintel
                self.slab_on(F, u - w / 2 - 0.12, u + w / 2 + 0.12, v + body, v + body + 0.28, -0.01, 0.015, 'brick_rubbed')
            else:
                self.slab_on(F, u - w / 2 - 0.08, u + w / 2 + 0.08, v + body, v + body + 0.14, 0, 0.08, 'trim')
                self.slab_on(F, u - w / 2 - 0.12, u + w / 2 + 0.12, v + body + 0.14, v + body + 0.2, 0, 0.12, 'trim')
            if lintel != 'brick':
                for s in (-1, 1):  # casing
                    self.slab_on(F, u + s * (w / 2 + 0.04) - 0.05, u + s * (w / 2 + 0.04) + 0.05, v, v + body, 0, 0.05, 'trim')
        if shutters:
            sw = w / 2
            for s in (-1, 1):
                x0 = u + s * (w / 2 + 0.02); x1 = x0 + s * sw
                self.slab_on(F, min(x0, x1), max(x0, x1), v, v + h, 0.03, 0.08, 'shutter')
                for k in range(2):  # raised panels
                    yy0 = v + 0.12 + k * (h - 0.24) / 2; yy1 = yy0 + (h - 0.24) / 2 - 0.1
                    self.slab_on(F, min(x0, x1) + 0.07, max(x0, x1) - 0.07, yy0, yy1, 0.08, 0.1, 'shutter')

    def door(self, F, u, v, w, h, arch=False, pediment=False, transom=True):
        rec = -0.18
        body = h - (w / 2 if arch else 0)
        self.quad_on(F, u - w / 2, u + w / 2, v, v + body, rec, 'door')
        for i in range(2):  # six-panel door, two leaves
            for j in range(3):
                x0 = u - w / 2 + 0.08 + i * w / 2; x1 = x0 + w / 2 - 0.16
                y0 = v + 0.15 + j * (body - 0.4) / 3; y1 = y0 + (body - 0.4) / 3 - 0.1
                self.slab_on(F, x0, x1, y0, y1, rec, rec + 0.03, 'door')
        for s in (-1, 1):
            self.slab_on(F, u + s * (w / 2 + 0.07) - 0.09, u + s * (w / 2 + 0.07) + 0.09, v, v + body + (0.1 if not arch else 0), -0.02, 0.1, 'trim')
        if arch:
            segs = 10; r = w / 2; cy = v + body
            for k in range(segs):
                a0, a1 = math.pi * k / segs, math.pi * (k + 1) / segs
                p0 = (u + r * math.cos(a0), cy + r * math.sin(a0)); p1 = (u + r * math.cos(a1), cy + r * math.sin(a1))
                self.poly([F(*p1, rec), F(*p0, rec), F(u, cy, rec)], 'glass')
                q0 = (u + (r + 0.3) * math.cos(a0), cy + (r + 0.3) * math.sin(a0)); q1 = (u + (r + 0.3) * math.cos(a1), cy + (r + 0.3) * math.sin(a1))
                self.poly([F(*p1, 0.01), F(*p0, 0.01), F(*q0, 0.01), F(*q1, 0.01)], 'brick_rubbed')
        elif transom:
            self.quad_on(F, u - w / 2, u + w / 2, v + body + 0.05, v + body + 0.45, rec, 'glass')
            self.slab_on(F, u - w / 2 - 0.16, u + w / 2 + 0.16, v + body + 0.45, v + body + 0.6, -0.02, 0.12, 'trim')
        if pediment:
            top = v + h + (0.6 if transom else 0.2)
            pw = w / 2 + 0.45
            self.slab_on(F, u - pw, u + pw, top, top + 0.14, 0, 0.3, 'trim')
            self.poly([F(u - pw, top + 0.14, 0.3), F(u + pw, top + 0.14, 0.3), F(u, top + 0.8, 0.3)], 'trim')
            self.poly([F(u + pw, top + 0.14, 0.0), F(u - pw, top + 0.14, 0.0), F(u, top + 0.8, 0.0)], 'trim')
            for s in (-1, 1):
                a = F(u + s * pw, top + 0.14, 0.0); b = F(u + s * pw, top + 0.14, 0.3); c = F(u, top + 0.8, 0.3); d = F(u, top + 0.8, 0.0)
                self.poly([a, b, c, d] if s < 0 else [b, a, d, c], 'shingle')
        # stone step
        self.slab_on(F, u - w / 2 - 0.3, u + w / 2 + 0.3, v - 0.35, v, 0, 0.7, 'stone')

    def chimney(self, x0, x1, z0, z1, y0, y1, m='brick'):
        self.box(x0, x1, y0, y1, z0, z1, m)
        self.box(x0 - 0.08, x1 + 0.08, y1 - 0.35, y1 - 0.2, z0 - 0.08, z1 + 0.08, m)
        self.box(x0 + 0.15, x1 - 0.15, y1, y1 + 0.02, z0 + 0.15, z1 - 0.15, 'dark')

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
        return ob


# =============================================================== the buildings
def church():
    b = Builder('church')
    g = 2.2                                   # foundation line (a little below the 2018 floor)
    cx = -163.85
    nave = (cx - 2.8, cx + 2.8, 285.6, 299.4)   # x0, x1, z0, z1
    tr = (-169.3, -158.4, 288.4, 294.0)         # transepts
    eave, ridge = 7.2, 10.2
    # walls with a projecting water table
    b.box(nave[0], nave[1], g, eave, nave[2], nave[3], 'brick')
    b.box(tr[0], tr[1], g, eave, tr[2], tr[3], 'brick')
    b.box(nave[0] - 0.1, nave[1] + 0.1, g, g + 0.8, nave[2] - 0.1, nave[3] + 0.1, 'brick_rubbed', skip=('-y',))
    b.box(tr[0] - 0.1, tr[1] + 0.1, g, g + 0.8, tr[2] - 0.1, tr[3] + 0.1, 'brick_rubbed', skip=('-y',))
    # modillion cornice
    b.box(nave[0] - 0.15, nave[1] + 0.15, eave - 0.3, eave, nave[2] - 0.15, nave[3] + 0.15, 'trim', skip=('-y',))
    b.box(tr[0] - 0.15, tr[1] + 0.15, eave - 0.3, eave, tr[2] - 0.15, tr[3] + 0.15, 'trim', skip=('-y',))
    b.gable_roof(nave[0], nave[1], nave[2], nave[3], eave, ridge, 'z', 'shingle', end_m='brick')
    b.gable_roof(tr[0], tr[1], tr[2], tr[3], eave, ridge - 0.05, 'x', 'shingle', end_m='brick')
    # round-arched windows: nave sides between transept and ends, transept ends, chancel end
    for side, x in ((1, nave[1]), (-1, nave[0])):
        F, U = b.wall('x', x, side)
        for z in (286.9, 296.8):
            b.sash_window(F, U(z), g + 1.3, 1.2, 3.4, cols=3, rows=5, arch=True)
    for side, x in ((1, tr[1]), (-1, tr[0])):
        F, U = b.wall('x', x, side)
        b.sash_window(F, U((tr[2] + tr[3]) / 2), g + 1.3, 1.3, 3.5, cols=3, rows=5, arch=True)
    for side, z in ((1, tr[3]), (-1, tr[2])):   # transept side walls beside the nave
        F, U = b.wall('z', z, side)
        for x in (tr[0] + 1.35, tr[1] - 1.35):
            b.sash_window(F, U(x), g + 1.3, 1.1, 3.3, cols=3, rows=5, arch=True)
    F, U = b.wall('z', nave[2], -1)   # chancel end
    b.sash_window(F, U(cx), g + 1.3, 1.5, 3.8, cols=3, rows=5, arch=True)
    # tower: three brick stages with belt courses, then the white octagonal steeple
    t = (cx - 1.7, cx + 1.7, 299.3, 302.7)
    stages = [(g, 6.2), (6.2, 8.8), (8.8, 11.0)]
    for i, (y0, y1) in enumerate(stages):
        inset = 0.12 * i
        b.box(t[0] + inset, t[1] - inset, y0, y1, t[2] + inset, t[3] - inset, 'brick')
        b.box(t[0] + inset - 0.1, t[1] - inset + 0.1, y1 - 0.18, y1, t[2] + inset - 0.1, t[3] - inset + 0.1, 'trim')
    Fn, Un = b.wall('z', t[3], 1)
    b.door(Fn, Un(cx), g + 0.35, 1.4, 3.1, arch=True, transom=False)
    b.sash_window(Fn, Un(cx), 6.7, 0.9, 1.7, cols=2, rows=3, arch=True)
    b.sash_window(Fn, Un(cx), 9.2, 0.8, 1.4, cols=2, rows=2, arch=True)
    for side in (1, -1):
        Fs, Us = b.wall('x', t[1] if side > 0 else t[0], side)
        zc = (t[2] + t[3]) / 2
        b.sash_window(Fs, Us(zc), 6.7, 0.9, 1.7, cols=2, rows=3, arch=True)
        b.sash_window(Fs, Us(zc), 9.2, 0.8, 1.4, cols=2, rows=2, arch=True)
    tz = (t[2] + t[3]) / 2
    # balustrade platform
    b.box(t[0], t[1], 11.0, 11.25, t[2], t[3], 'trim')
    # octagonal belfry, lantern, spire, ball and weathervane
    b.prism(cx, tz, 1.25, 11.25, 13.2, 8, 'trim', rot=math.pi / 8)
    for k in range(8):
        a = math.pi / 8 + 2 * math.pi * k / 8 + math.pi / 8
        px, pz = cx + 1.2 * math.cos(a), tz + 1.2 * math.sin(a)
        b.box(px - 0.22, px + 0.22, 11.7, 12.9, pz - 0.22, pz + 0.22, 'dark')   # louvred openings
    b.prism(cx, tz, 1.35, 13.2, 13.4, 8, 'trim', rot=math.pi / 8)
    b.prism(cx, tz, 0.85, 13.4, 14.9, 8, 'trim', rot=math.pi / 8)
    b.prism(cx, tz, 0.95, 14.9, 15.05, 8, 'trim', rot=math.pi / 8)
    b.pyramid(cx, tz, 0.9, 15.05, 18.4, 8, 'lead', rot=math.pi / 8)
    b.prism(cx, tz, 0.12, 18.3, 18.6, 12, 'gilt')
    b.box(cx - 0.02, cx + 0.02, 18.6, 19.3, tz - 0.02, tz + 0.02, 'gilt')
    b.box(cx - 0.35, cx + 0.35, 19.05, 19.12, tz - 0.01, tz + 0.01, 'gilt')
    return b


def courthouse():
    b = Builder('courthouse')
    g = 2.0
    main = (-160.8, -154.8, 261.9, 274.7)
    wing = (-166.8, -160.6, 265.3, 271.1)
    eave = 6.9
    for r in (main, wing):
        b.box(r[0], r[1], g, eave, r[2], r[3], 'brick')
        b.box(r[0] - 0.1, r[1] + 0.1, g, g + 0.7, r[2] - 0.1, r[3] + 0.1, 'brick_rubbed', skip=('-y',))
        b.box(r[0] - 0.18, r[1] + 0.18, eave - 0.35, eave, r[2] - 0.18, r[3] + 0.18, 'trim', skip=('-y',))
    b.hip_roof(main[0], main[1], main[2], main[3], eave, 9.4, 'shingle')
    b.gable_roof(wing[0] - 0.3, wing[1] + 0.8, wing[2], wing[3], eave, 9.0, 'x', 'shingle', over=0.3)
    zc = 268.2
    # front (east, +x): arched windows with white shutters, pedimented projection
    F, U = b.wall('x', main[1], 1)
    for z in (263.5, 265.6, 270.8, 272.9):
        b.sash_window(F, U(z), g + 1.1, 1.15, 3.3, cols=3, rows=5, arch=True, shutters=True)
    pj = (main[1], main[1] + 0.75, zc - 2.2, zc + 2.2)
    b.box(pj[0], pj[1], g, eave, pj[2], pj[3], 'brick')
    b.box(pj[0] - 0.05, pj[1] + 0.18, eave - 0.35, eave, pj[2] - 0.18, pj[3] + 0.18, 'trim')
    # pediment facing +x
    ped_y = eave; ped_top = eave + 1.5
    b.poly([(pj[1] + 0.18, ped_y, pj[3] + 0.18), (pj[1] + 0.18, ped_y, pj[2] - 0.18), (pj[1] + 0.18, ped_top, zc)], 'trim')
    b.poly([(pj[1] + 0.18, ped_y, pj[2] - 0.18), (pj[0] - 0.3, ped_y + 0.2, pj[2] - 0.18), (pj[0] - 0.3, ped_top, zc), (pj[1] + 0.18, ped_top, zc)], 'shingle')
    b.poly([(pj[0] - 0.3, ped_y + 0.2, pj[3] + 0.18), (pj[1] + 0.18, ped_y, pj[3] + 0.18), (pj[1] + 0.18, ped_top, zc), (pj[0] - 0.3, ped_top, zc)], 'shingle')
    Fp, Up = b.wall('x', pj[1], 1)
    b.door(Fp, Up(zc), g + 0.4, 1.5, 3.4, arch=True, transom=False)
    # sides and rear
    for side in (1, -1):
        Fs, Us = b.wall('z', main[3] if side > 0 else main[2], side)
        b.sash_window(Fs, Us(-157.8), g + 1.1, 1.15, 3.3, cols=3, rows=5, arch=True, shutters=True)
        Fw, Uw = b.wall('z', wing[3] if side > 0 else wing[2], side)
        for x in (-165.2, -162.4):
            b.sash_window(Fw, Uw(x), g + 1.1, 1.1, 3.2, cols=3, rows=5, arch=True, shutters=True)
    Fr, Ur = b.wall('x', wing[0], -1)
    b.sash_window(Fr, Ur(zc), g + 1.1, 1.2, 3.3, cols=3, rows=5, arch=True, shutters=True)
    # octagonal cupola with dome and spire, over the crossing
    cx, cz = -159.6, zc
    b.box(cx - 0.9, cx + 0.9, 8.6, 9.9, cz - 0.9, cz + 0.9, 'trim')
    b.prism(cx, cz, 0.75, 9.9, 11.2, 8, 'trim', rot=math.pi / 8)
    for k in range(8):
        a = math.pi / 4 + 2 * math.pi * k / 8
        px, pz = cx + 0.72 * math.cos(a), cz + 0.72 * math.sin(a)
        b.box(px - 0.13, px + 0.13, 10.2, 10.95, pz - 0.13, pz + 0.13, 'glass')
    b.prism(cx, cz, 0.85, 11.2, 11.35, 8, 'trim', rot=math.pi / 8)
    for k in range(5):  # ogee dome in rings
        r0 = 0.8 * math.cos(k / 5 * math.pi / 2); r1 = 0.8 * math.cos((k + 1) / 5 * math.pi / 2)
        y0 = 11.35 + 0.7 * math.sin(k / 5 * math.pi / 2); y1 = 11.35 + 0.7 * math.sin((k + 1) / 5 * math.pi / 2)
        b.prism(cx, cz, r0, y0, y1, 16, 'lead', r1=max(r1, 0.12), top=(k == 4))
    b.pyramid(cx, cz, 0.12, 12.05, 13.0, 8, 'lead')
    b.box(cx - 0.015, cx + 0.015, 13.0, 13.6, cz - 0.015, cz + 0.015, 'gilt')
    b.box(cx - 0.3, cx + 0.3, 13.35, 13.42, cz - 0.01, cz + 0.01, 'gilt')
    return b


def magazine():
    b = Builder('magazine')
    g = 1.9
    cx, cz = -125.9, 263.6
    R = 3.95                                     # octagon circumradius (7.6 m across flats)
    rot = math.pi / 8
    b.prism(cx, cz, R, g, 7.6, 8, 'brick', rot=rot, top=False)
    b.prism(cx, cz, R + 0.1, g, g + 0.7, 8, 'brick_rubbed', rot=rot, top=True)
    b.prism(cx, cz, R + 0.22, 7.35, 7.6, 8, 'trim', rot=rot)
    b.pyramid(cx, cz, R + 0.55, 7.45, 11.3, 8, 'shingle', rot=rot)
    b.prism(cx, cz, 0.14, 11.2, 11.6, 8, 'gilt')
    b.box(cx - 0.015, cx + 0.015, 11.6, 12.3, cz - 0.015, cz + 0.015, 'gilt')
    b.box(cx - 0.28, cx + 0.28, 12.05, 12.12, cz - 0.01, cz + 0.01, 'gilt')
    # door on the west face, small windows high on the others
    ap = R * math.cos(math.pi / 8)
    for k in range(8):
        a = 2 * math.pi * k / 8 + math.pi   # face normals start at west (-x)
        n = (math.cos(a), 0, math.sin(a))
        F = b.frame((cx + n[0] * ap, 0, cz + n[2] * ap), n)
        if k == 0:
            b.door(F, 0, g + 0.35, 1.2, 2.6, transom=False)
            b.slab_on(F, -1.0, 1.0, g + 3.0, g + 3.15, 0, 0.5, 'trim')     # hood
        elif k % 2 == 0:
            b.sash_window(F, 0, 5.6, 0.7, 1.1, cols=2, rows=2, arch=True)
    # the high octagonal wall around it, with a gateway to the west
    Rw = 10.7
    for k in range(8):
        a0 = rot + 2 * math.pi * k / 8; a1 = rot + 2 * math.pi * (k + 1) / 8
        p0 = (cx + Rw * math.cos(a0), cz + Rw * math.sin(a0)); p1 = (cx + Rw * math.cos(a1), cz + Rw * math.sin(a1))
        mid = ((a0 + a1) / 2) % (2 * math.pi)
        segs = [(0, 1)]
        if abs(mid - math.pi) < 0.1: segs = [(0, 0.36), (0.64, 1)]    # gate opening facing west
        for s0, s1 in segs:
            q0 = (p0[0] + (p1[0] - p0[0]) * s0, p0[1] + (p1[1] - p0[1]) * s0)
            q1 = (p0[0] + (p1[0] - p0[0]) * s1, p0[1] + (p1[1] - p0[1]) * s1)
            wall_seg(b, q0, q1, g, 5.9, 0.35, 'brick')
            wall_seg(b, q0, q1, 5.9, 6.1, 0.5, 'brick_rubbed')
        if len(segs) > 1:
            for s in (0.36, 0.64):
                q = (p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s)
                b.box(q[0] - 0.4, q[0] + 0.4, g, 6.5, q[1] - 0.4, q[1] + 0.4, 'brick')
                b.box(q[0] - 0.47, q[0] + 0.47, 6.5, 6.7, q[1] - 0.47, q[1] + 0.47, 'stone')
    return b


def wall_seg(b, p0, p1, y0, y1, th, m):
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]; L = math.hypot(dx, dz)
    nx, nz = -dz / L * th / 2, dx / L * th / 2
    a = (p0[0] + nx, p0[1] + nz); bb = (p1[0] + nx, p1[1] + nz); c = (p1[0] - nx, p1[1] - nz); d = (p0[0] - nx, p0[1] - nz)
    q = lambda p, y: (p[0], y, p[1])
    for u, v in ((a, bb), (bb, c), (c, d), (d, a)):
        b.poly([q(u, y0), q(v, y0), q(v, y1), q(u, y1)][::-1], m)
    b.poly([q(a, y1), q(bb, y1), q(c, y1), q(d, y1)][::-1], m)


def randolph():
    b = Builder('randolph')
    g = 2.1
    x0, x1, z0, z1 = -159.5, -154.9, 221.3, 235.8
    eave, ridge = 8.3, 10.6
    b.box(x0 - 0.05, x1 + 0.05, g, g + 0.55, z0 - 0.05, z1 + 0.05, 'brick')        # brick foundation
    b.box(x0, x1, g + 0.55, eave, z0, z1, 'clapboard_red')
    b.box(x0 - 0.12, x1 + 0.12, eave - 0.25, eave, z0 - 0.12, z1 + 0.12, 'trim', skip=('-y',))
    for zz in (z0, z1):   # corner boards
        for xx in (x0, x1):
            b.box(xx - 0.06, xx + 0.06, g + 0.55, eave - 0.25, zz - 0.06, zz + 0.06, 'trim')
    b.gable_roof(x0, x1, z0, z1, eave, ridge, 'z', 'shingle', over=0.3, end_m='clapboard_red')
    # exterior brick end chimneys, stepped with weatherings
    for zc, s in ((z0 - 0.55, -1), (z1 + 0.55, 1)):
        b.box(-158.5, -156.0, g, 6.4, zc - 0.55, zc + 0.55, 'brick')
        b.box(-158.1, -156.4, 6.4, 7.4, zc - 0.5, zc + 0.5, 'brick')
        b.chimney(-157.8, -156.7, zc - 0.45, zc + 0.45, 7.4, 11.5)
    # front: seven bays, shuttered sash windows, pedimented door
    F, U = b.wall('x', x1, 1)
    bays = [222.6, 224.6, 226.5, 230.5, 232.4, 234.4]
    for z in bays:
        b.sash_window(F, U(z), g + 1.35, 0.95, 1.75, cols=3, rows=3, shutters=True, lintel='wood')
        b.sash_window(F, U(z), g + 3.95, 0.95, 1.55, cols=3, rows=3, shutters=True, lintel='wood')
    b.door(F, U(228.5), g + 0.6, 1.15, 2.4, pediment=True)
    b.sash_window(F, U(228.5), g + 3.95, 0.95, 1.55, cols=3, rows=3, shutters=True, lintel='wood')
    Fr, Ur = b.wall('x', x0, -1)
    for z in (223.6, 227.0, 230.0, 233.4):
        b.sash_window(Fr, Ur(z), g + 1.35, 0.95, 1.75, cols=3, rows=3, lintel='wood')
        b.sash_window(Fr, Ur(z), g + 3.95, 0.95, 1.55, cols=3, rows=3, lintel='wood')
    return b


# =============================================================== export
bpy.ops.wm.read_factory_settings(use_empty=True)
for fn in (church, courthouse, magazine, randolph):
    fn().build()
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=False, export_apply=True,
                          export_normals=True, export_materials='EXPORT',
                          export_texcoords=False, export_yup=True)
print('wrote', OUT, os.path.getsize(OUT) // 1024, 'KB')
