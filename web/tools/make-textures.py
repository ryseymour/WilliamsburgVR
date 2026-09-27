#!/usr/bin/env python3
"""Procedural PBR textures for the remastered Williamsburg.

Brick, clapboard, shingles and grass come from Ryan's own photographs of the
real surfaces, which shipped inside the 2018 build (web/assets/src, written by
export-scene.py). Normal, roughness and occlusion maps are derived from them.
Surfaces the build had no photo for (the sandy street, painted trim, weathered
wood, tent canvas, gravestones) are generated from filtered noise, which tiles
seamlessly because it is made in the frequency domain.

Writes web/assets/rm/<name>_albedo.jpg, _normal.jpg and _orm.jpg
(R = ambient occlusion, G = roughness, B = metalness, as three.js expects).
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'rm')
os.makedirs(OUT, exist_ok=True)
N = 1024
rng = np.random.default_rng(1699)  # the year Williamsburg became the capital


def noise(scale, n=N, seed=None, aniso=(1, 1)):
    """Tileable noise with features about `scale` pixels wide, normalised to 0..1."""
    r = np.random.default_rng(seed) if seed is not None else rng
    w = r.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None] * aniso[1]
    fx = np.fft.fftfreq(n)[None, :] * aniso[0]
    f = np.sqrt(fx ** 2 + fy ** 2)
    k = np.exp(-(f * scale) ** 2 * 4)
    out = np.real(np.fft.ifft2(np.fft.fft2(w) * k))
    out -= out.min(); out /= out.max() + 1e-9
    return out


def fbm(base, octaves=5, seed=None, aniso=(1, 1)):
    s, amp, tot = np.zeros((N, N)), 1.0, 0
    for o in range(octaves):
        s += noise(base / 2 ** o, seed=None if seed is None else seed + o, aniso=aniso) * amp
        tot += amp; amp *= 0.5
    return s / tot


def blur_wrap(a, r):
    f = np.fft.fftfreq(a.shape[0])
    k = np.exp(-(f[:, None] ** 2 + f[None, :] ** 2) * (r * np.pi) ** 2 * 2)
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack([-dx, dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def save(name, albedo, height, rough, ao=None, metal=None, nstrength=4.0, size=N):
    def im(a, mode='RGB'):
        a = np.clip(a, 0, 1)
        img = Image.fromarray((a * 255 + 0.5).astype(np.uint8), mode if a.ndim == 3 else 'L')
        return img.resize((size, size), Image.LANCZOS) if size != N else img
    im(albedo).save(os.path.join(OUT, f'{name}_albedo.jpg'), quality=86)
    im(normal_from_height(height, nstrength)).save(os.path.join(OUT, f'{name}_normal.jpg'), quality=90)
    full = lambda v, d: np.full((N, N), d) if v is None else np.broadcast_to(v, (N, N))
    ao, rough, metal = full(ao, 1.0), full(rough, 0.8), full(metal, 0.0)
    orm = Image.fromarray((np.clip(np.dstack([ao, rough, metal]), 0, 1) * 255).astype(np.uint8))
    orm.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, f'{name}_orm.jpg'), quality=86)
    print('wrote', name)


def rgb(hexs):
    return np.array([int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


yy, xx = np.mgrid[0:N, 0:N]

# ---------------------------------------------------------------- photographs
SRC = os.path.join(ROOT, 'assets', 'src')


def from_photo(name, src, detail=2.5, broad=40, strength=5, rough=(0.55, 0.9), tint=None, size=N, invert=False):
    img = Image.open(os.path.join(SRC, src)).convert('RGB').resize((N, N), Image.LANCZOS)
    col = np.asarray(img).astype(np.float64) / 255
    lum = col @ [0.299, 0.587, 0.114]
    # height: bright = raised (mortar recessed, lap shadows low), band-passed
    h = blur_wrap(lum, detail) - blur_wrap(lum, broad)
    if invert: h = -h
    h = (h - h.min()) / (np.ptp(h) + 1e-9)
    cav = np.clip((blur_wrap(h, 6) - h) * 4 + 0.5, 0, 1)      # crevices
    ao = np.clip(1.15 - cav * 0.7, 0.35, 1)
    rgh = rough[0] + (rough[1] - rough[0]) * np.clip(1 - (lum - lum.mean()) * 1.5 - 0.5 + cav * 0.4, 0, 1)
    if tint is not None:
        g = lum[..., None] / (lum.mean() + 1e-9)
        col = np.clip(tint[None, None, :] * g * 0.85 + col * 0.15, 0, 1)
    save(name, col, h, rgh, ao, nstrength=strength, size=size)


def photos():
    from_photo('brick', 'brick.png', detail=2, broad=30, strength=6, rough=(0.6, 0.92))
    from_photo('clapboard', 'clapboard-grey.png', detail=2, broad=60, strength=7, rough=(0.5, 0.75))
    from_photo('clapboard-brown', 'clapboard-brown.png', detail=2, broad=60, strength=7, rough=(0.55, 0.8))
    from_photo('shingle', 'shingles.png', detail=2, broad=40, strength=6, rough=(0.75, 0.95))
    from_photo('grass', 'grass.png', detail=1.5, broad=30, strength=3, rough=(0.8, 0.97))
    from_photo('boards', 'boards.png', detail=2, broad=40, strength=4, rough=(0.6, 0.85))


# ---------------------------------------------------------------- street
# Williamsburg's streets are packed sand and clay with crushed oyster shell.
def street():
    base = fbm(120, 5)
    sand = lerp(np.tile(rgb('#9c8a6a'), (N, N, 1)), np.tile(rgb('#b9a782'), (N, N, 1)), base)
    ruts = fbm(60, 4, aniso=(0.12, 1))
    grit = noise(1.2)
    pebbles = np.clip((noise(3.5, seed=5) - 0.72) * 6, 0, 1)
    shell = np.clip((noise(2.5, seed=9) - 0.8) * 8, 0, 1)
    col = sand * (0.85 + grit[..., None] * 0.3) * (0.9 + ruts[..., None] * 0.15)
    col = lerp(col, np.tile(rgb('#7a6d5c'), (N, N, 1)), pebbles * 0.7)
    col = lerp(col, np.tile(rgb('#e6e0d2'), (N, N, 1)), shell * 0.85)
    h = base * 0.3 + ruts * 0.3 + pebbles * 0.5 + shell * 0.3 + grit * 0.1
    rough = 0.92 - shell * 0.2
    save('street', col, h, rough, 0.8 + h * 0.2, nstrength=4)


# ---------------------------------------------------------------- weathered wood
def wood():
    grain = fbm(30, 5, aniso=(0.05, 1))
    rings = np.sin(grain * 60) * 0.5 + 0.5
    col = lerp(np.tile(rgb('#4d4034'), (N, N, 1)), np.tile(rgb('#7b6b58'), (N, N, 1)), grain * 0.7 + rings * 0.3)
    silver = np.clip((fbm(150, 4) - 0.4) * 2, 0, 1)
    col = lerp(col, np.tile(rgb('#8b8479'), (N, N, 1)), silver * 0.5)
    h = grain * 0.5 + rings * 0.2
    save('wood', col, h, 0.78 + rings * 0.12, 0.85 + rings * 0.15, nstrength=5)


# ---------------------------------------------------------------- painted trim
def paint():
    brush = fbm(12, 4, aniso=(0.1, 1))
    wear = np.clip((fbm(100, 4) - 0.7) * 4, 0, 1)
    col = np.dstack([np.full((N, N), 0.95)] * 3) * (0.97 + brush[..., None] * 0.04)
    col = lerp(col, np.tile(rgb('#9b907f'), (N, N, 1)), wear * 0.5)
    save('paint', col, brush * 0.3 - wear * 0.2, 0.45 + brush * 0.1 + wear * 0.3, None, nstrength=2)


# ---------------------------------------------------------------- canvas
def canvas():
    weave = (np.sin(xx * np.pi / 2.0) * np.sin(yy * np.pi / 2.0)) * 0.5 + 0.5
    stain = fbm(140, 4)
    col = np.dstack([np.full((N, N), 0.9), np.full((N, N), 0.87), np.full((N, N), 0.8)])
    col *= (0.92 + weave[..., None] * 0.08) * (0.9 + stain[..., None] * 0.1)
    save('canvas', col, weave * 0.4 + stain * 0.2, 0.9, None, nstrength=2, size=512)


# ---------------------------------------------------------------- stone
def stone():
    b = fbm(60, 6)
    lichen = np.clip((fbm(40, 4, seed=21) - 0.62) * 4, 0, 1)
    col = lerp(np.tile(rgb('#7c7a74'), (N, N, 1)), np.tile(rgb('#b4b0a6'), (N, N, 1)), b)
    col = lerp(col, np.tile(rgb('#a8a878'), (N, N, 1)), lichen * 0.45)
    save('stone', col, b, 0.85, 0.85 + b * 0.15, nstrength=4, size=512)


for f in (photos, street, wood, paint, canvas, stone):
    f()
