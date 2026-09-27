// Williamsburg: a browser edition of the 2018 WilliamsburgVR tour.
// The town, terrain, trees, signs, photos and fife music all come from the
// original WebGL build (see tools/export-scene.py).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import TOWN from './data/town.js';
import MUSIC from './data/music.js';
import { WORLD, ART } from './data/art.js';
import { createRemaster } from './remaster.js';

// The four stops, in the order the original playerspawner cycled through them
// (Site1..Site4). Quotes are the ones printed on the in-game sign boards.
const STOPS = [
  {
    site: 'Site1', sign: 'Church_Sign', photo: 'photo-church',
    title: 'Bruton Parish Church', sub: 'Built 1711 to 1715',
    text: 'Bruton Parish Church is located in the restored area of Colonial Williamsburg in Williamsburg, Virginia, United States. It was established in 1674 by the consolidation of two previous parishes in the Virginia Colony, and remains an active Episcopal parish. The building, constructed 1711-15, was designated a National Historic Landmark in 1970 as a well-preserved early example of colonial religious architecture. The roots of Bruton Parish Church trace back to both the Church of England and the new settlement of the Colony of Virginia at Jamestown in the early 17th century.',
    credit: 'Wikipedia',
  },
  {
    site: 'Site2', sign: 'Courthouse_Sign', photo: 'photo-courthouse',
    title: 'The Courthouse', sub: 'Built 1770 to 1771',
    text: 'The Colonial Williamsburg Courthouse was constructed from 1770 to 1771 in the Georgian style. The courthouse was built with red bricks with white wooden trim-boards and long arched windows with white shutters. A projected portico is located over one of the entrances and is unique in Georgian architecture. The hipped roof rests on an entablature with dentil moldings. The roof is pierced on both sides by a chimney and a central octagonal drum capped with a dome and a spire.',
    credit: 'Wikipedia',
  },
  {
    site: 'Site3', sign: 'Armory_Sign', photo: 'photo-magazine',
    title: 'The Magazine', sub: 'Armory of the colony, 1715',
    text: 'In 1714, the General Assembly had asked Governor Alexander Spotswood to build "a good substantial house of brick" to protect the colony\'s arms and munitions. The occasion was the shipment of powder and muskets from Queen Anne\'s government in England. The city\'s 17th-century magazine, if it still stood, seems to have been inadequate.',
    credit: 'Colonial Williamsburg',
  },
  {
    site: 'Site4', sign: 'Residence_Sign', photo: 'photo-residence',
    title: 'Peyton Randolph House', sub: 'Oldest portion about 1715',
    text: 'The Peyton Randolph House, also known as the Randolph-Peachy House, is a historic house museum at Nicholson and North England Streets in Colonial Williamsburg, Virginia. Its oldest portion dating to about 1715, it is one of the museum\'s oldest surviving buildings. It was designated a National Historic Landmark in 1973 as the home of Peyton Randolph (1721-1775), first President of the Continental Congress.',
    credit: 'Wikipedia',
  },
];

const $ = (id) => document.getElementById(id);
const root = $('wb');
const canvas = $('wb-canvas');
const EYE = 1.7;

// ---------------------------------------------------------------- renderer
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const SKY_TOP = new THREE.Color('#6f9fd2'), SKY_BOTTOM = new THREE.Color('#dfe7e4');
scene.fog = new THREE.Fog(SKY_BOTTOM.clone(), 90, 420);
const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 1200);
camera.rotation.order = 'YXZ';

// sky dome
{
  const g = new THREE.SphereGeometry(800, 32, 16);
  const m = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: SKY_TOP }, bottom: { value: SKY_BOTTOM }, sun: { value: new THREE.Vector3() } },
    vertexShader: 'varying vec3 v; void main(){ v = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }',
    fragmentShader: `uniform vec3 top, bottom, sun; varying vec3 v;
      void main(){ float h = clamp(v.y*1.6+.08, 0., 1.);
        vec3 c = mix(bottom, top, pow(h, .7));
        float s = max(dot(v, normalize(sun)), 0.);
        c += vec3(1.,.86,.62) * (pow(s, 600.)*2. + pow(s, 12.)*.18);
        gl_FragColor = vec4(c, 1.); }`,
  });
  var sky = new THREE.Mesh(g, m);
  sky.renderOrder = -1;
  scene.add(sky);
}

// lights: a late-afternoon sun, as in the original's directional light
const hemi = new THREE.HemisphereLight('#dfeaff', '#6b5a3c', 0.85);
scene.add(hemi);
const sun = new THREE.DirectionalLight('#fff1d6', 2.2);
sun.position.set(-60, 90, -50);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -90, right: 90, top: 90, bottom: -90, near: 10, far: 400 });
sun.shadow.bias = -0.0006;
sun.shadow.normalBias = 0.04;
scene.add(sun, sun.target);
sky.material.uniforms.sun.value.copy(sun.position).normalize();

// ---------------------------------------------------------------- helpers
const b64buf = (s) => { const bin = atob(s); const a = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return a.buffer; };
const texLoader = new THREE.TextureLoader();
function tex(name, repeat) {
  const t = texLoader.load(ART[name]);
  t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return t;
}
function loadImage(src) { return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; }); }

// ---------------------------------------------------------------- terrain
const T = WORLD.terrain;
let heights, hRes, terrainMesh;
async function buildTerrain() {
  const img = await loadImage(ART.height);
  hRes = img.width;
  const c = document.createElement('canvas'); c.width = c.height = hRes;
  const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, hRes, hRes).data;
  heights = new Float32Array(hRes * hRes);
  for (let i = 0; i < heights.length; i++) heights[i] = T.hmin + (px[i * 4] / 255) * (T.hmax - T.hmin);

  const seg = 256;
  const g = new THREE.PlaneGeometry(T.size[0], T.size[2], seg, seg);
  g.rotateX(-Math.PI / 2);
  // Unity terrain covers x 0..500 (flipped to -500..0 here) and z 0..500
  g.translate(-T.size[0] / 2, 0, T.size[2] / 2);
  const pos = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    pos.setY(i, heightAt(x, z));
    uv.setXY(i, -x / T.size[0], z / T.size[2]);
  }
  g.computeVertexNormals();

  const splat = tex('splat'); splat.colorSpace = THREE.NoColorSpace; splat.flipY = false;
  const layers = T.layers.map((l, i) => tex('layer' + i, true));
  const mat = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0 });
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.splat = { value: splat };
    layers.forEach((t, i) => (sh.uniforms['L' + i] = { value: t }));
    sh.uniforms.tiles = { value: new THREE.Vector4(...T.layers.map((l) => T.size[0] / l.tile[0])) };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec2 vTUv;')
      .replace('#include <uv_vertex>', '#include <uv_vertex>\nvTUv = uv;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec2 vTUv; uniform sampler2D splat, L0, L1, L2, L3; uniform vec4 tiles;')
      .replace('#include <map_fragment>', `
        vec4 w = texture2D(splat, vTUv);
        w /= max(w.r + w.g + w.b + w.a, 1e-3);
        vec3 col = texture2D(L0, vTUv * tiles.x).rgb * w.r + texture2D(L1, vTUv * tiles.y).rgb * w.g
                 + texture2D(L2, vTUv * tiles.z).rgb * w.b + texture2D(L3, vTUv * tiles.w).rgb * w.a;
        diffuseColor.rgb *= col;`);
  };
  const mesh = new THREE.Mesh(g, mat);
  mesh.receiveShadow = true;
  scene.add(mesh);
  terrainMesh = mesh;
}
function heightAt(x, z) {
  if (!heights) return 0;
  const u = (-x / T.size[0]) * (hRes - 1), v = (z / T.size[2]) * (hRes - 1);
  const x0 = Math.max(0, Math.min(hRes - 2, Math.floor(u))), z0 = Math.max(0, Math.min(hRes - 2, Math.floor(v)));
  const fx = Math.min(1, Math.max(0, u - x0)), fz = Math.min(1, Math.max(0, v - z0));
  const h = (xx, zz) => heights[zz * hRes + xx];
  return (h(x0, z0) * (1 - fx) + h(x0 + 1, z0) * fx) * (1 - fz) + (h(x0, z0 + 1) * (1 - fx) + h(x0 + 1, z0 + 1) * fx) * fz;
}

// ---------------------------------------------------------------- town
let walkMeshes = [], townRoot, treeGroups = [];
async function buildTown() {
  const loader = new GLTFLoader();
  const glb = await new Response(new Blob([b64buf(TOWN)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  // The artifact sandbox blocks fetch() of blob: URLs, which GLTFLoader's
  // ImageBitmapLoader uses; hiding createImageBitmap makes it fall back to <img>.
  const cib = window.createImageBitmap;
  window.createImageBitmap = undefined;
  let gltf;
  try { gltf = await loader.parseAsync(glb, ''); }
  finally { window.createImageBitmap = cib; }
  const protos = {};
  gltf.scene.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true; o.receiveShadow = true;
      const m = o.material;
      if (m.map) m.map.anisotropy = 8;
      // the sign boards face every which way; light them a little so the
      // printed photos and quotes stay readable on the shaded side
      if (/sign|church2material/i.test(m.name) && m.map) { m.emissive = new THREE.Color(1, 1, 1); m.emissiveMap = m.map; m.emissiveIntensity = 0.45; }
      if (m.transparent) { o.castShadow = false; m.depthWrite = false; }
    }
  });
  // GLTFLoader strips ':' from node names, so 'tree:bush06' arrives as 'treebush06'
  for (const node of [...gltf.scene.children]) {
    if (/^tree/.test(node.name)) { protos[node.name.slice(4)] = node; gltf.scene.remove(node); }
  }
  scene.add(gltf.scene);
  townRoot = gltf.scene;
  gltf.scene.updateMatrixWorld(true);
  walkMeshes = [];
  gltf.scene.traverse((o) => { if (o.isMesh && /road/.test(o.material.name)) walkMeshes.push(o); });

  // terrain trees
  for (const t of WORLD.trees) {
    const p = protos[t.p]; if (!p) continue;
    const g = new THREE.Group();
    const c = p.clone(); c.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.material.side = THREE.DoubleSide; } });
    g.add(c);
    g.position.set(t.x, heightAt(t.x, t.z), t.z);
    g.rotation.y = -t.r;
    g.scale.set(t.w, t.h, t.w);
    scene.add(g);
    treeGroups.push(g);
  }
}

// ---------------------------------------------------------------- flag, smoke, dust
let flag, flagBase, flagParts = [];
const FLAG_H = 1.5, MAST = 6.5;
function buildFlag() {
  // The build's cloth flag hangs off a 2 m stub on the courthouse roof and its
  // pole is a 9 cm cylinder you can barely see, so give it a proper mast.
  const pole = WORLD.flag.pole;
  const base = pole[1] - 1.11;
  const wood = new THREE.MeshStandardMaterial({ color: '#e9e4d8', roughness: 0.6 });
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.07, MAST, 12), wood);
  mast.position.set(pole[0], base + MAST / 2, pole[2]);
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 12), new THREE.MeshStandardMaterial({ color: '#c9a24a', metalness: 0.8, roughness: 0.3 }));
  ball.position.set(pole[0], base + MAST + 0.08, pole[2]);
  mast.castShadow = ball.castShadow = true;
  scene.add(mast, ball);
  flagParts.push(mast, ball);

  const g = new THREE.PlaneGeometry(FLAG_H * 1.6, FLAG_H, 24, 12);
  g.translate(FLAG_H * 0.8 + 0.05, -FLAG_H / 2, 0);
  flagBase = g.attributes.position.array.slice();
  const m = new THREE.MeshStandardMaterial({ map: tex('flag'), side: THREE.DoubleSide, roughness: 0.9 });
  flag = new THREE.Mesh(g, m);
  flag.castShadow = true;
  flag.position.set(pole[0], base + MAST - 0.15, pole[2]);
  flag.rotation.y = Math.PI * 0.62;
  scene.add(flag);
}
function waveFlag(t) {
  const p = flag.geometry.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = flagBase[i * 3], y = flagBase[i * 3 + 1];
    const k = x / (FLAG_H * 1.6);
    p.setZ(i, Math.sin(x * 2.2 - t * 5 + y * 0.4) * 0.28 * k + Math.sin(x * 4.1 - t * 7.3) * 0.06 * k);
    p.setY(i, y - k * k * 0.12);
  }
  p.needsUpdate = true;
  flag.geometry.computeVertexNormals();
}

const puffs = [];
function buildSmoke() {
  const map = tex('smoke');
  const spawners = [
    ...WORLD.smoke.map((p) => ({ p, chimney: true, rate: 0.35, size: 1.4, grow: 2.4, life: 7, alpha: 0.5, rise: 1.3, color: '#dedad3' })),
    ...WORLD.dust.map((p) => ({ p: [p[0], Math.min(p[1], 3), p[2]], rate: 0.12, size: 6, grow: 5, life: 12, alpha: 0.14, rise: 0.25, color: '#d8c7a3', drift: 1.4 })),
  ];
  for (const s of spawners) {
    s.acc = Math.random();
    s.mat = new THREE.SpriteMaterial({ map, color: s.color, transparent: true, depthWrite: false, opacity: 0 });
  }
  return spawners;
}
let smokeSpawners = [], chimneySmoke = true;
function tickSmoke(dt) {
  for (const s of smokeSpawners) {
    if (s.chimney && !chimneySmoke) continue;
    s.acc += dt * s.rate;
    while (s.acc > 1) {
      s.acc -= 1;
      const sp = new THREE.Sprite(s.mat.clone());
      sp.position.set(s.p[0] + (Math.random() - 0.5) * (s.drift ? 20 : 0.3), s.p[1], s.p[2] + (Math.random() - 0.5) * (s.drift ? 20 : 0.3));
      sp.userData = { s, age: 0, spin: (Math.random() - 0.5) * 0.4 };
      sp.material.rotation = Math.random() * 6.28;
      scene.add(sp); puffs.push(sp);
    }
  }
  for (let i = puffs.length - 1; i >= 0; i--) {
    const sp = puffs[i], u = sp.userData, s = u.s;
    u.age += dt;
    const k = u.age / s.life;
    if (k >= 1) { scene.remove(sp); sp.material.dispose(); puffs.splice(i, 1); continue; }
    sp.position.y += s.rise * dt;
    sp.position.x += (s.drift || 0.5) * dt * 0.6;
    sp.material.rotation += u.spin * dt;
    const size = s.size + s.grow * k;
    sp.scale.set(size, size, 1);
    sp.material.opacity = s.alpha * Math.sin(Math.PI * Math.min(1, k * 1.2));
  }
}

// ---------------------------------------------------------------- tour state
const player = { pos: new THREE.Vector3(), yaw: 0, pitch: 0 };
let current = -1, busy = false, started = false;
const visited = new Set();

function stopView(i) {
  const s = STOPS[i];
  const site = WORLD.sites[s.site], sign = WORLD.signs[s.sign];
  // Stand where the original dropped you (the Site trigger), backed off far
  // enough to read the whole board instead of staring up at it.
  const [lo, hi] = sign.box;
  const target = new THREE.Vector3((lo[0] + hi[0]) / 2, hi[1] - 2.6, (lo[2] + hi[2]) / 2);
  const dir = new THREE.Vector3(site[0] - target.x, 0, site[2] - target.z).normalize();
  const pos = new THREE.Vector3(target.x, 0, target.z).addScaledVector(dir, 8.5);
  pos.y = groundAt(pos.x, pos.z);
  const yaw = Math.atan2(-(target.x - pos.x), -(target.z - pos.z));
  const pitch = Math.atan2(target.y - (pos.y + EYE), 8.5) * 0.85;
  return { pos, yaw, pitch };
}

function goTo(i) {
  if (busy) return;
  busy = true;
  hidePanel();
  const fade = $('wb-fade');
  fade.classList.add('on');
  setTimeout(() => {
    const v = stopView(i);
    player.pos.copy(v.pos); player.yaw = v.yaw; player.pitch = v.pitch;
    current = i;
    fade.classList.remove('on');
    setTimeout(() => { showPanel(i); busy = false; }, 450);
  }, 420);
}
const nextStop = () => goTo((current + 1) % STOPS.length);
const prevStop = () => goTo((current - 1 + STOPS.length) % STOPS.length);

function showPanel(i) {
  const s = STOPS[i];
  visited.add(i);
  $('wb-photo').src = ART[s.photo];
  $('wb-photo').alt = s.title;
  $('wb-ptitle').textContent = s.title;
  $('wb-psub').textContent = `Stop ${i + 1} of ${STOPS.length} · ${s.sub}`;
  $('wb-ptext').textContent = '“' + s.text + '”';
  $('wb-pcredit').textContent = s.credit;
  $('wb-next').textContent = visited.size === STOPS.length && i === STOPS.length - 1 ? 'Finish the tour' : 'Next stop';
  $('wb-panel').classList.add('on');
  renderDots();
}
function hidePanel() { $('wb-panel').classList.remove('on'); }
function renderDots() {
  $('wb-dots').innerHTML = STOPS.map((s, i) =>
    `<button class="dot${visited.has(i) ? ' seen' : ''}${i === current ? ' here' : ''}" data-i="${i}" title="${s.title}" aria-label="Go to ${s.title}"><span>${i + 1}</span></button>`).join('');
  $('wb-count').textContent = `${visited.size} / ${STOPS.length} visited`;
}

function finish() {
  hidePanel();
  $('wb-done').classList.add('on');
}

// ---------------------------------------------------------------- input
const keys = new Set();
addEventListener('keydown', (e) => {
  if (!started && e.key.toLowerCase() === 'v') { setEra(era === 'rm' ? '2018' : 'rm'); return; }
  if (!started) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); begin(); } return; }
  const k = e.key.toLowerCase();
  if ([' ', 'enter', 'n'].includes(k) && !e.repeat) { e.preventDefault(); onNext(); return; }
  if (k === 'p' || k === 'b') { prevStop(); return; }
  if (k === 'm') { toggleMusic(); return; }
  if (k === 'v' && !e.repeat) { setEra(era === 'rm' ? '2018' : 'rm'); return; }
  if (k === 'escape') { hidePanel(); $('wb-done').classList.remove('on'); return; }
  if (k === 'i' && current >= 0) { $('wb-panel').classList.contains('on') ? hidePanel() : showPanel(current); return; }
  keys.add(k);
  if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd'].includes(k)) e.preventDefault();
});
addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
addEventListener('blur', () => keys.clear());

function onNext() {
  if ($('wb-done').classList.contains('on')) return;
  if (visited.size === STOPS.length && current === STOPS.length - 1 && $('wb-panel').classList.contains('on')) finish();
  else nextStop();
}

// drag to look (mouse and touch)
let drag = null;
canvas.addEventListener('pointerdown', (e) => {
  if (e.target !== canvas) return;
  drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: 0 };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener('pointermove', (e) => {
  if (!drag || drag.id !== e.pointerId) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
  const s = 0.0042 * (e.pointerType === 'touch' ? 1.3 : 1);
  player.yaw += dx * s;
  player.pitch = Math.max(-1.2, Math.min(1.2, player.pitch + dy * s));
});
const endDrag = (e) => { if (drag && drag.id === e.pointerId) drag = null; };
canvas.addEventListener('pointerup', endDrag);
canvas.addEventListener('pointercancel', endDrag);

// on-screen stick for touch walking
const stick = { x: 0, y: 0, id: null };
{
  const pad = $('wb-stick'), knob = pad.querySelector('i');
  const set = (e) => {
    const r = pad.getBoundingClientRect();
    let x = (e.clientX - r.left - r.width / 2) / (r.width / 2), y = (e.clientY - r.top - r.height / 2) / (r.height / 2);
    const l = Math.hypot(x, y); if (l > 1) { x /= l; y /= l; }
    stick.x = x; stick.y = y;
    knob.style.transform = `translate(${x * 28}px, ${y * 28}px)`;
  };
  pad.addEventListener('pointerdown', (e) => { stick.id = e.pointerId; pad.setPointerCapture(e.pointerId); set(e); });
  pad.addEventListener('pointermove', (e) => { if (e.pointerId === stick.id) set(e); });
  const up = (e) => { if (e.pointerId !== stick.id) return; stick.id = null; stick.x = stick.y = 0; knob.style.transform = ''; };
  pad.addEventListener('pointerup', up); pad.addEventListener('pointercancel', up);
}

$('wb-next').addEventListener('click', onNext);
$('wb-nextfab').addEventListener('click', onNext);
$('wb-close').addEventListener('click', hidePanel);
$('wb-info').addEventListener('click', () => { if (current >= 0) showPanel(current); });
$('wb-dots').addEventListener('click', (e) => { const b = e.target.closest('.dot'); if (b) goTo(+b.dataset.i); });
$('wb-again').addEventListener('click', () => { $('wb-done').classList.remove('on'); visited.clear(); current = -1; renderDots(); goTo(0); });
$('wb-roam').addEventListener('click', () => $('wb-done').classList.remove('on'));
$('wb-sound').addEventListener('click', toggleMusic);
$('wb-begin').addEventListener('click', begin);

// ---------------------------------------------------------------- 2018 / remastered
let rm = null, era = 'rm';
try { if (localStorage.getItem('wb-era') === '2018') era = '2018'; } catch {}
function setEra(e) {
  era = e;
  try { localStorage.setItem('wb-era', e); } catch {}
  document.querySelectorAll('[data-era]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.era === e)));
  if (!rm) return;
  if (e === 'rm') rm.enable(); else rm.disable();
}
document.querySelectorAll('[data-era]').forEach((b) => b.addEventListener('click', () => setEra(b.dataset.era)));
setEra(era);

// ---------------------------------------------------------------- music
const music = new Audio(MUSIC);
music.loop = true; music.volume = 0.55;
let musicOn = true;
function toggleMusic() {
  musicOn = !musicOn;
  if (musicOn) music.play().catch(() => {}); else music.pause();
  $('wb-sound').setAttribute('aria-pressed', String(musicOn));
  $('wb-sound').textContent = musicOn ? 'Music on' : 'Music off';
}

function begin() {
  if (started || !ready) return;
  started = true;
  if (musicOn) music.play().catch(() => {});
  $('wb-title').classList.add('gone');
  root.classList.add('touring');
  goTo(0);
}

// ---------------------------------------------------------------- walking
const ray = new THREE.Raycaster();
const DOWN = new THREE.Vector3(0, -1, 0);
function groundAt(x, z) {
  let y = heightAt(x, z);
  if (walkMeshes.length) {
    ray.set(new THREE.Vector3(x, 60, z), DOWN); ray.far = 80;
    const hit = ray.intersectObjects(walkMeshes, false)[0];
    if (hit && hit.point.y > y) y = hit.point.y;
  }
  return y;
}
const LIMIT = { minX: -330, maxX: -20, minZ: 120, maxZ: 460 };
let groundTimer = 0, groundY = 0;
function walk(dt) {
  let f = 0, s = 0;
  if (keys.has('w') || keys.has('arrowup')) f += 1;
  if (keys.has('s') || keys.has('arrowdown')) f -= 1;
  if (keys.has('a')) s -= 1;
  if (keys.has('d')) s += 1;
  if (keys.has('arrowleft') || keys.has('q')) player.yaw += dt * 1.8;
  if (keys.has('arrowright') || keys.has('e')) player.yaw -= dt * 1.8;
  f -= stick.y; s += stick.x;
  const moving = Math.hypot(f, s) > 0.05;
  if (moving) {
    if ($('wb-panel').classList.contains('on')) hidePanel();
    const speed = (keys.has('shift') ? 9 : 4.5) * Math.min(1, Math.hypot(f, s));
    const l = Math.hypot(f, s) || 1;
    const sin = Math.sin(player.yaw), cos = Math.cos(player.yaw);
    const dx = (-sin * f + cos * s) / l, dz = (-cos * f - sin * s) / l;
    player.pos.x = Math.max(LIMIT.minX, Math.min(LIMIT.maxX, player.pos.x + dx * speed * dt));
    player.pos.z = Math.max(LIMIT.minZ, Math.min(LIMIT.maxZ, player.pos.z + dz * speed * dt));
    groundTimer -= dt;
    if (groundTimer <= 0) { groundY = groundAt(player.pos.x, player.pos.z); groundTimer = 0.08; }
    player.pos.y += (groundY - player.pos.y) * Math.min(1, dt * 10);
    bob += dt * speed * 1.6;
  }
  return moving;
}
let bob = 0;

// ---------------------------------------------------------------- loop
const clock = new THREE.Clock();
let ready = false, titleT = 0;
const titleSpot = new THREE.Vector3(...WORLD.start);
function frame() {
  const dt = Math.min(0.05, clock.getDelta()), t = clock.elapsedTime;
  if (!started) {
    // slow orbit over the town behind the title card
    titleT += dt;
    const a = titleT * 0.05 + 2.2;
    camera.position.set(-150 + Math.cos(a) * 70, 34, 268 + Math.sin(a) * 70);
    camera.lookAt(-150, 4, 266);
  } else {
    walk(dt);
    camera.position.set(player.pos.x, player.pos.y + EYE + Math.sin(bob) * 0.04, player.pos.z);
    camera.rotation.set(player.pitch, player.yaw, 0);
  }
  sun.position.set(camera.position.x - 60, 90, camera.position.z - 50);
  sun.target.position.set(camera.position.x, 0, camera.position.z);
  sky.position.copy(camera.position);
  if (flag) waveFlag(t);
  tickSmoke(dt);
  if (rm) rm.update(dt, t);
  if (rm && rm.on) rm.render(); else renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
function resize() {
  const w = root.clientWidth, h = root.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h; camera.updateProjectionMatrix();
  if (rm) rm.resize(w, h);
}
addEventListener('resize', resize);

// ---------------------------------------------------------------- boot
(async () => {
  resize();
  $('wb-titleimg').src = ART.title;
  const step = (msg) => ($('wb-load').textContent = msg);
  try {
    step('Laying out the streets…');
    await buildTerrain();
    step('Raising the buildings…');
    await buildTown();
    buildFlag();
    smokeSpawners = buildSmoke();
    step('Restoring the landmarks…');
    try {
      rm = await createRemaster({
        scene, renderer, camera, WORLD, heightAt, sun, hemi, sky,
        town: townRoot, terrain: terrainMesh, trees: treeGroups, flagParts,
        landmarkNodes: ['lmchurch', 'lmcourthouse', 'lmmagazine', 'lmrandolph', 'lmhouses'].map((n) => townRoot.getObjectByName(n)).filter(Boolean),
        roadMeshes: walkMeshes,
        setOldSmoke: (on) => (chimneySmoke = on),
      });
      rm.resize(root.clientWidth, root.clientHeight);
      setEra(era);
    } catch (err) {
      // the 2018 version still works on its own
      console.error(err);
      document.querySelectorAll('.era').forEach((el) => (el.hidden = true));
    }
    renderDots();
    ready = true;
    $('wb-load').textContent = '';
    $('wb-begin').disabled = false;
    $('wb-begin').focus({ preventScroll: true });
  } catch (err) {
    console.error(err);
    step('Could not load the town: ' + err.message);
  }
  requestAnimationFrame(frame);
})();

window.__wb = { scene, camera, player, goTo, STOPS, WORLD, setEra, get rm() { return rm; }, get current() { return current; } };
