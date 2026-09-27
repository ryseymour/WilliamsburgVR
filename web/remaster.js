// Remastered edition of the Williamsburg tour.
//
// Everything here is layered on top of the faithful 2018 scene built by
// tour.js, and can be switched off again at any moment:
//   - physically based materials built from Ryan's own photos of the brick,
//     weatherboard, shingles and grass (projected in world space, so the
//     original models need no new UVs)
//   - the church, courthouse, magazine and Randolph house rebuilt in Blender
//     (tools/build-landmarks.py) in place of the 2018 models
//   - grown oaks, elms and boxwood (tools/build-trees.py) in place of the
//     stock 2018 palms, and lettered wayside panels in place of the sign boxes
//   - an atmospheric sky with drifting clouds that also lights the scene
//   - sandy oyster-shell streets painted into the ground, wind-blown grass,
//     swaying trees, chimney smoke from every chimney, birds and dust motes
//   - ambient occlusion, bloom and a filmic grade
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RM } from './data/remaster.js';
import MODELS, { CHIMNEYS, TREES } from './data/models.js';

const loader = new THREE.TextureLoader();
const b64buf = (s) => { const bin = atob(s); const a = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return a.buffer; };
const inflate = (s) => new Response(new Blob([b64buf(s)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();

export async function createRemaster(ctx) {
  const { scene, renderer, camera, WORLD, heightAt, sun, hemi, sky: oldSky, town, terrain, trees, landmarkNodes, roadMeshes, flagParts, stops = [], art = {} } = ctx;
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  const coarse = matchMedia('(pointer: coarse)').matches;

  function map(name, srgb = true) {
    const t = loader.load(RM[name]);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = maxAniso;
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    return t;
  }
  const sets = {};
  function set(name) {
    return (sets[name] ||= { albedo: map(name + '_albedo'), normal: map(name + '_normal', false), orm: map(name + '_orm', false) });
  }

  // shared uniforms
  const U = { time: { value: 0 }, wind: { value: 1 } };

  // ------------------------------------------------------------ triplanar PBR
  // World-space projection: brick courses and weatherboards stay level and
  // true to scale on every wall, whatever UVs the 2018 models shipped with.
  function triplanar({ tex, scale = 1, tint = '#ffffff', roughness = 1, metalness = 0, normalScale = 1, roofRows = false, side = THREE.FrontSide }) {
    const s = set(tex);
    const m = new THREE.MeshStandardMaterial({ color: tint, roughness, metalness, side, envMapIntensity: 0.9 });
    m.userData.remaster = true;
    m.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, {
        tA: { value: s.albedo }, tN: { value: s.normal }, tO: { value: s.orm },
        tScale: { value: 1 / scale }, tNS: { value: normalScale },
      });
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN;')
        .replace('#include <fog_vertex>', '#include <fog_vertex>\nvWP = (modelMatrix * vec4(transformed, 1.0)).xyz; vWN = normalize(mat3(modelMatrix) * objectNormal);');
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>', `#include <common>
          varying vec3 vWP; varying vec3 vWN;
          uniform sampler2D tA, tN, tO; uniform float tScale, tNS;
          vec3 triW(vec3 n){ vec3 w = pow(abs(n), vec3(6.0)); return w / (w.x + w.y + w.z); }
          vec2 roofUV(vec3 p, vec3 n){ return ${roofRows ? '(abs(n.x) > abs(n.z) ? p.zx : p.xz)' : 'p.xz'}; }
          vec4 tri(sampler2D t, vec3 p, vec3 n){ vec3 w = triW(n);
            return texture2D(t, p.zy) * w.x + texture2D(t, roofUV(p, n)) * w.y + texture2D(t, p.xy) * w.z; }`)
        .replace('#include <map_fragment>', `
          vec3 wn = normalize(vWN) * (gl_FrontFacing ? 1.0 : -1.0);
          vec3 tp = vWP * tScale;
          vec4 triAlb = tri(tA, tp, wn);
          vec4 triORM = tri(tO, tp, wn);
          diffuseColor.rgb *= triAlb.rgb * mix(1.0, triORM.r, 0.85);`)
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = roughness * triORM.g;')
        .replace('#include <metalnessmap_fragment>', 'float metalnessFactor = metalness;')
        .replace('#include <normal_fragment_maps>', `{
          vec3 w = triW(wn);
          vec3 nx = texture2D(tN, tp.zy).xyz * 2.0 - 1.0; nx.xy *= tNS;
          vec2 ry = roofUV(tp, wn);
          vec3 ny = texture2D(tN, ry).xyz * 2.0 - 1.0; ny.xy *= tNS;
          vec3 nz = texture2D(tN, tp.xy).xyz * 2.0 - 1.0; nz.xy *= tNS;
          // whiteout blend (Golus), then back to view space
          vec3 bx = vec3(nx.xy + wn.zy, abs(nx.z) * wn.x);
          vec3 by = vec3(ny.xy + ${roofRows ? '(abs(wn.x) > abs(wn.z) ? wn.zx : wn.xz)' : 'wn.xz'}, abs(ny.z) * wn.y);
          vec3 bz = vec3(nz.xy + wn.xy, abs(nz.z) * wn.z);
          vec3 wy = ${roofRows ? '(abs(wn.x) > abs(wn.z) ? by.yzx : by.xzy)' : 'by.xzy'};
          vec3 nW = normalize(bx.zyx * w.x + wy * w.y + bz.xyz * w.z);
          normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
        }`);
    };
    m.customProgramCacheKey = () => 'tri-' + tex + (roofRows ? '-roof' : '');
    return m;
  }

  const M = {
    brick: triplanar({ tex: 'brick', scale: 0.95, tint: '#d99a86', roughness: 1, normalScale: 1.2 }),
    brickRubbed: triplanar({ tex: 'brick', scale: 0.95, tint: '#c98a70', roughness: 0.95 }),
    clapWhite: triplanar({ tex: 'clapboard', scale: 1.0, tint: '#f1ede4', roughness: 0.9 }),
    clapRed: triplanar({ tex: 'clapboard', scale: 1.0, tint: '#9a4a38', roughness: 0.9 }),     // Spanish brown
    clapBlue: triplanar({ tex: 'clapboard', scale: 1.0, tint: '#b3bcc2', roughness: 0.9 }),
    clapSage: triplanar({ tex: 'clapboard', scale: 1.0, tint: '#c7c7a6', roughness: 0.9 }),
    clapOchre: triplanar({ tex: 'clapboard-brown', scale: 1.8, tint: '#e2cf9e', roughness: 0.9 }),
    clapBrown: triplanar({ tex: 'clapboard-brown', scale: 1.8, roughness: 0.9 }),
    shingle: triplanar({ tex: 'shingle', scale: 1.7, roughness: 1, roofRows: true, normalScale: 1.3, side: THREE.DoubleSide }),
    wood: triplanar({ tex: 'wood', scale: 1.4, roughness: 1 }),
    fence: triplanar({ tex: 'wood', scale: 1.2, tint: '#9a8f82', roughness: 1 }),
    boards: triplanar({ tex: 'boards', scale: 1.6, roughness: 1 }),
    paint: triplanar({ tex: 'paint', scale: 1.5, tint: '#f4f1ea', roughness: 0.75, side: THREE.DoubleSide }),
    shutter: triplanar({ tex: 'paint', scale: 1.5, tint: '#2c3a30', roughness: 0.6, side: THREE.DoubleSide }),
    door: triplanar({ tex: 'wood', scale: 1.2, tint: '#6a4a36', roughness: 0.7, side: THREE.DoubleSide }),
    canvas: triplanar({ tex: 'canvas', scale: 1.5, tint: '#d8cfb9', roughness: 1, side: THREE.DoubleSide }),
    stone: triplanar({ tex: 'stone', scale: 1.2, roughness: 1 }),
    glass: new THREE.MeshPhysicalMaterial({ color: '#1d2527', roughness: 0.04, metalness: 0.0, reflectivity: 0.6, envMapIntensity: 1.6, side: THREE.DoubleSide }),
    dark: new THREE.MeshStandardMaterial({ color: '#141210', roughness: 0.9, side: THREE.DoubleSide }),
    lead: new THREE.MeshStandardMaterial({ color: '#8d9594', roughness: 0.45, metalness: 0.7, side: THREE.DoubleSide }),
    gilt: new THREE.MeshStandardMaterial({ color: '#d6ad52', roughness: 0.25, metalness: 1 }),
    iron: new THREE.MeshStandardMaterial({ color: '#1d1e1f', roughness: 0.6, metalness: 0.35 }),
  };

  M.postPaint = triplanar({ tex: 'paint', scale: 1.5, tint: '#26282a', roughness: 0.6 });
  M.ironBlack = new THREE.MeshStandardMaterial({ color: '#1b1c1d', roughness: 0.55, metalness: 0.6 });
  // 2018 material name -> remastered material (unlisted ones keep their look)
  const REMAP = {
    'brick': M.brick, 'brick 2': M.brick, 'brick 3': M.brick, 'New Material 2': M.brick,
    'Siding': M.clapWhite, 'Siding 1': M.clapRed, 'Siding 2': M.clapBlue, 'Siding 3': M.clapSage, 'Siding 4': M.clapBrown,
    'Material_007': M.clapOchre,
    'shingles': M.shingle, 'Material_003': M.shingle, 'Material.003': M.ironBlack,
    'T19_Dark_Chocolate': M.fence, 'cherry': M.postPaint, 'Material.001': M.wood, 'Material_002': M.wood,
    'Material.006': M.wood, 'Material.007': M.wood, 'woodpanel': M.boards,
    'New Material 1': M.paint, 'Material.001 Diffuse Color': M.paint, 'Material.002': M.paint,
    'Material.009': M.paint, 'Default-Material': M.paint,
    'Material': M.shutter,
    'Material.008': M.glass, 'glassMaterial': M.glass, 'glassMaterial 1': M.glass, 'Material.004': M.glass,
    'Material.005': M.iron, 'black': M.dark,
    'No Name': M.canvas, 'hourse': null, 'grey.gravestone': M.stone,
  };
  M.shutterWhite = triplanar({ tex: 'paint', scale: 1.5, tint: '#ece8de', roughness: 0.7, side: THREE.DoubleSide });
  M.shutterRed = triplanar({ tex: 'paint', scale: 1.5, tint: '#5e231c', roughness: 0.6, side: THREE.DoubleSide });
  M.clapRandolph = triplanar({ tex: 'clapboard', scale: 1.0, tint: '#6d3326', roughness: 0.85 });
  const LMAP = {
    brick: M.brick, brick_rubbed: M.brickRubbed, shingle: M.shingle, trim: M.paint,
    glass: M.glass, door: M.door, door_white: M.paint, shutter: M.shutter, shutter_white: M.shutterWhite, shutter_red: M.shutterRed,
    stone: M.stone, lead: M.lead, gilt: M.gilt, dark: M.dark,
    clapboard_red: M.clapRandolph, clap_white: M.clapWhite, clap_red: M.clapRed, clap_blue: M.clapBlue,
    clap_sage: M.clapSage, clap_brown: M.clapBrown, clap_ochre: M.clapOchre,
  };

  // ------------------------------------------------------------ landmarks
  const lm = (await new GLTFLoader().parseAsync(await inflate(MODELS), '')).scene;
  lm.traverse((o) => {
    if (!o.isMesh) return;
    o.material = LMAP[o.material.name] || M.paint;
    o.castShadow = o.receiveShadow = true;
    if (o.material === M.glass) o.castShadow = false;
  });
  lm.visible = false;
  scene.add(lm);

  // ------------------------------------------------------------ wayside signs
  // The 2018 boards were big white boxes with the photo pasted on one face.
  // In their place: painted wayside panels on two posts, lettered like the
  // real Colonial Williamsburg markers, each facing the spot the tour stands.
  const signGroup = new THREE.Group(); signGroup.visible = false; scene.add(signGroup);
  const oldSigns = [];
  town.traverse((o) => { if (o.isMesh && /sign|church2material/i.test(o.material.name)) oldSigns.push(o); });
  // the 2018 sign posts are merged into shared town meshes; give those meshes a
  // copy without the triangles that stand on a sign's footprint
  const signPts = Object.values(WORLD.signs).map((sg) => [sg.pos[0], sg.pos[2]]);
  const postless = [];
  town.traverse((o) => {
    if (!o.isMesh || oldSigns.includes(o) || landmarkNodes.some((n) => n === o || o.parent === n)) return;
    const g = o.geometry, pos = g.attributes.position, idx = g.index;
    if (!idx) return;
    const v = new THREE.Vector3(), near = new Uint8Array(pos.count);
    let any = false;
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
      if (signPts.some(([x, z]) => Math.hypot(v.x - x, v.z - z) < 0.45)) { near[i] = 1; any = true; }
    }
    if (!any) return;
    const keep = [];
    for (let i = 0; i < idx.count; i += 3) {
      const a = idx.getX(i), b = idx.getX(i + 1), c = idx.getX(i + 2);
      if (!(near[a] && near[b] && near[c])) keep.push(a, b, c);
    }
    if (keep.length === idx.count) return;
    const ng = g.clone(); ng.setIndex(keep);
    postless.push([o, g, ng]);
  });
  const postMat = triplanar({ tex: 'paint', scale: 1.5, tint: '#3a3128', roughness: 0.7 });
  const loadImg = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
  function wrap(g, text, x, y, w, lh, maxY) {
    const words = text.split(' '); let line = '';
    for (const wd of words) {
      const t = line ? line + ' ' + wd : wd;
      if (g.measureText(t).width > w && line) { if (y + lh > maxY) { g.fillText(line + '…', x, y); return; } g.fillText(line, x, y); line = wd; y += lh; } else line = t;
    }
    g.fillText(line, x, y);
  }
  for (const st of stops) {
    const sg = WORLD.signs[st.sign], site = WORLD.sites[st.site];
    if (!sg || !site) continue;
    const c = document.createElement('canvas'); c.width = 1400; c.height = 900;
    const g = c.getContext('2d');
    g.fillStyle = '#2d2620'; g.fillRect(0, 0, 1400, 900);
    g.strokeStyle = '#c9b68a'; g.lineWidth = 6; g.strokeRect(26, 26, 1348, 848);
    g.fillStyle = '#efe4c8'; g.font = '600 76px Georgia, "Times New Roman", serif'; g.fillText(st.title, 70, 138);
    g.fillStyle = '#c9b68a'; g.font = '30px Georgia, serif'; g.fillText(st.sub.toUpperCase(), 72, 190);
    g.fillRect(70, 215, 1260, 3);
    const img = await loadImg(art[st.photo]);
    if (img) {
      const w = 620, h = Math.min(560, w * img.height / img.width);
      g.filter = 'sepia(0.35) contrast(1.05)'; g.drawImage(img, 70, 250, w, h); g.filter = 'none';
      g.strokeStyle = '#c9b68a'; g.lineWidth = 3; g.strokeRect(70, 250, w, h);
    }
    g.fillStyle = '#efe4c8'; g.font = 'italic 31px Georgia, serif';
    wrap(g, '\u201c' + st.text + '\u201d', 730, 278, 600, 42, 790);
    g.fillStyle = '#c9b68a'; g.font = '26px Georgia, serif'; g.fillText('\u2014 ' + st.credit, 730, 836);
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = maxAniso;
    const face = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55, emissive: '#ffffff', emissiveMap: tex, emissiveIntensity: 0.12 });
    const [lo, hi] = sg.box, cx = (lo[0] + hi[0]) / 2, cz = (lo[2] + hi[2]) / 2, gy = heightAt(cx, cz);
    const W = 2.8, H = W * 900 / 1400, base = 1.05;
    const s = new THREE.Group();
    const panel = new THREE.Mesh(new THREE.BoxGeometry(W, H, 0.06), [postMat, postMat, postMat, postMat, face, postMat]);
    panel.position.y = base + H / 2;
    const back = new THREE.Mesh(new THREE.BoxGeometry(W + 0.16, H + 0.16, 0.05), postMat);
    back.position.set(0, base + H / 2, -0.05);
    const cap = new THREE.Mesh(new THREE.BoxGeometry(W + 0.36, 0.08, 0.3), postMat);
    cap.position.y = base + H + 0.12;
    s.add(panel, back, cap);
    for (const x of [-W / 2 - 0.02, W / 2 + 0.02]) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.16, base + H + 0.3, 0.16), postMat);
      p.position.set(x, (base + H + 0.3) / 2 - 0.2, -0.12); s.add(p);
      const ball = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), postMat);
      ball.position.set(x, base + H + 0.26, -0.12); s.add(ball);
    }
    s.traverse((o) => { if (o.isMesh) o.castShadow = o.receiveShadow = true; });
    s.position.set(cx, gy, cz);
    s.rotation.y = Math.atan2(site.pos ? site.pos[0] - cx : site[0] - cx, site.pos ? site.pos[2] - cz : site[2] - cz);
    signGroup.add(s);
  }

  // ------------------------------------------------------------ sky & light
  const skyObj = new Sky();
  skyObj.scale.setScalar(4000);
  const su = skyObj.material.uniforms;
  su.turbidity.value = 3.2; su.rayleigh.value = 1.6; su.mieCoefficient.value = 0.003; su.mieDirectionalG.value = 0.82;
  // late afternoon, sun in the south-west
  const sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - 32), THREE.MathUtils.degToRad(-128));
  su.sunPosition.value.copy(sunDir);
  skyObj.visible = false;
  scene.add(skyObj);

  // cloud layer: a slow fbm sheet high above the town
  const clouds = new THREE.Mesh(
    new THREE.PlaneGeometry(6000, 6000, 1, 1).rotateX(Math.PI / 2),
    new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false, side: THREE.DoubleSide,
      uniforms: { time: U.time, sunDir: { value: sunDir } },
      vertexShader: 'varying vec3 vP; void main(){ vP = (modelMatrix * vec4(position,1.)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vP,1.); }',
      fragmentShader: `varying vec3 vP; uniform float time; uniform vec3 sunDir;
        float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
        float n(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.-2.*f);
          return mix(mix(h(i), h(i+vec2(1,0)), f.x), mix(h(i+vec2(0,1)), h(i+vec2(1,1)), f.x), f.y); }
        float fbm(vec2 p){ float s = 0., a = .5; for(int i=0;i<6;i++){ s += a*n(p); p = p*2.03 + 17.1; a *= .5; } return s; }
        void main(){
          vec2 p = vP.xz * 0.0011 + vec2(time * 0.004, time * 0.0015);
          float c = fbm(p); c = smoothstep(0.48, 0.78, c + fbm(p * 3.1) * 0.12);
          float d = length(vP.xz - cameraPosition.xz);
          float fade = 1. - smoothstep(500., 1100., d);
          float lit = 0.75 + 0.25 * fbm(p * 2. + sunDir.xz);
          vec3 col = mix(vec3(.78,.8,.84), vec3(1.,.97,.92), lit);
          gl_FragColor = vec4(col, c * fade * .85);
        }`,
    }));
  clouds.position.y = 420;
  clouds.visible = false;
  scene.add(clouds);

  // image-based lighting from the sky itself, so glass and metal reflect it
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  const envSky = new Sky(); envSky.scale.setScalar(1000);
  Object.entries(su).forEach(([k, v]) => { if (envSky.material.uniforms[k]) envSky.material.uniforms[k].value = v.value; });
  envScene.add(envSky);
  const envTex = pmrem.fromScene(envScene, 0.02).texture;

  const fogRemaster = new THREE.FogExp2(new THREE.Color('#b3c5d6'), 0.0013);

  // ------------------------------------------------------------ terrain
  const grass = set('grass'), street = set('street');
  const roadMask = loader.load(RM.roadmask); roadMask.flipY = false; roadMask.colorSpace = THREE.NoColorSpace;
  const terrainMat = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0, envMapIntensity: 0.95 });
  terrainMat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, { gA: { value: grass.albedo }, gN: { value: grass.normal }, sA: { value: street.albedo }, sN: { value: street.normal }, sO: { value: street.orm }, road: { value: roadMask } });
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec2 vTUv;')
      .replace('#include <uv_vertex>', '#include <uv_vertex>\nvTUv = uv;')
      .replace('#include <fog_vertex>', '#include <fog_vertex>\nvWP = (modelMatrix * vec4(transformed,1.)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec3 vWP; varying vec2 vTUv; uniform sampler2D gA, gN, sA, sN, sO, road;
        float hh(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
        float vn(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.-2.*f);
          return mix(mix(hh(i), hh(i+vec2(1,0)), f.x), mix(hh(i+vec2(0,1)), hh(i+vec2(1,1)), f.x), f.y); }
        float fb(vec2 p){ return vn(p)*.5 + vn(p*2.1)*.25 + vn(p*4.3)*.125 + vn(p*8.7)*.0625; }`)
      .replace('#include <map_fragment>', `
        vec2 gp = vWP.xz / 2.6;
        // two scales and a rotation hide the grass tile; broad noise adds dry and lush patches
        vec3 g1 = texture2D(gA, gp).rgb, g2 = texture2D(gA, gp * 0.37 + vec2(.31,.77)).rgb;
        float macro = fb(vWP.xz * 0.035);
        vec3 gcol = mix(g1, g2, 0.45) * mix(vec3(.82,.86,.7), vec3(1.08,1.05,.92), macro);
        gcol = mix(gcol, gcol * vec3(1.15,1.02,.72), smoothstep(.55,.8, fb(vWP.xz*.012+4.)) * .6);
        float edgeN = fb(vWP.xz * 0.6);
        float r = texture2D(road, vTUv).r;
        float rm = smoothstep(0.25, 0.65, r + (edgeN - .5) * .45);
        vec2 sp = vWP.xz / 3.2;
        vec3 scol = texture2D(sA, sp).rgb * mix(.92, 1.06, fb(vWP.xz*.08));
        // crushed shell and pebbles: fine speckle that fades out with distance
        float dcam = length(vWP - cameraPosition);
        float grit = mix(.84, 1.14, vn(vWP.xz * 11.)) * mix(.9, 1.1, vn(vWP.xz * 43.));
        scol *= mix(grit, 1., smoothstep(12., 45., dcam));
        // wheel ruts: two darker, smoother tracks where the mask is strongest
        scol *= 1. - smoothstep(.85, 1., r) * .08 * vn(vWP.xz * .5 + 3.);
        // worn verge between street and grass
        vec3 verge = mix(gcol, scol * vec3(.85,.8,.72), .55);
        vec3 col = mix(gcol, verge, smoothstep(0.05, 0.35, r + (edgeN-.5)*.3) * (1. - rm));
        col = mix(col, scol, rm);
        diffuseColor.rgb = col;
        float rmS = rm;`)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = mix(0.95, texture2D(sO, sp).g, rmS);')
      .replace('#include <normal_fragment_maps>', `{
        vec3 ng = texture2D(gN, gp).xyz * 2. - 1.;
        vec3 ns = texture2D(sN, sp).xyz * 2. - 1.;
        vec3 tn = normalize(mix(ng * vec3(.8,.8,1.), ns, rmS));
        vec3 wn = normalize(vec3(tn.x, tn.z, -tn.y));
        normal = normalize((viewMatrix * vec4(wn, 0.)).xyz);
      }`);
  };
  terrainMat.customProgramCacheKey = () => 'rm-terrain';
  const terrainOrig = terrain.material;

  // ------------------------------------------------------------ grass blades
  // Instanced tufts in 16 m chunks around the village; the vertex shader bends
  // them in gusts. Skipped on the streets.
  const maskImg = await new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.src = RM.roadmask; });
  const mc = document.createElement('canvas'); mc.width = mc.height = 512;
  const mctx = mc.getContext('2d'); mctx.drawImage(maskImg, 0, 0, 512, 512);
  const maskPx = mctx.getImageData(0, 0, 512, 512).data;
  const roadAt = (x, z) => { const u = Math.floor((-x / 500) * 511), v = Math.floor((z / 500) * 511); return u < 0 || v < 0 || u > 511 || v > 511 ? 0 : maskPx[(v * 512 + u) * 4] / 255; };
  const lmBoxes = [...Object.values(WORLD.landmarks), ...WORLD.houses.map((h) => [[h.box[0][0] - 1, 0, h.box[0][2] - 1], [h.box[1][0] + 1, 0, h.box[1][2] + 1]])];
  const inBuilding = (x, z) => lmBoxes.some(([lo, hi]) => x > lo[0] - 0.4 && x < hi[0] + 0.4 && z > lo[2] - 0.4 && z < hi[2] + 0.4) && !(x > -137 && x < -115 && z > 253 && z < 274 && Math.hypot(x + 125.9, z - 263.6) > 5);

  const tuft = (() => {
    const pos = [], col = [], blades = 7;
    for (let b = 0; b < blades; b++) {
      const a = (b / blades) * Math.PI * 2 + Math.random() * 0.8, r = Math.random() * 0.12;
      const bx = Math.cos(a) * r, bz = Math.sin(a) * r, h = 0.13 + Math.random() * 0.17, w = 0.012 + Math.random() * 0.01;
      const lean = 0.08 + Math.random() * 0.12, dx = Math.cos(a) * lean, dz = Math.sin(a) * lean;
      const px = -Math.sin(a) * w, pz = Math.cos(a) * w;
      const p = [[bx - px, 0, bz - pz], [bx + px, 0, bz + pz], [bx + dx * 0.55 + px * 0.6, h * 0.55, bz + dz * 0.55 + pz * 0.6],
                 [bx + dx * 0.55 - px * 0.6, h * 0.55, bz + dz * 0.55 - pz * 0.6], [bx + dx, h, bz + dz]];
      const tri = [[0, 1, 2], [0, 2, 3], [3, 2, 4]];
      for (const t of tri) for (const k of t) { pos.push(...p[k]); const y = p[k][1] / h; col.push(0.25 + y * 0.75, 0, 0); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    // soft upward normals so the blades light like a lawn, not like paper
    const n = g.attributes.normal; for (let i = 0; i < n.count; i++) n.setXYZ(i, n.getX(i) * 0.3, 1, n.getZ(i) * 0.3);
    return g;
  })();
  const bladeMat = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: 0.85, side: THREE.DoubleSide, envMapIntensity: 0.4 });
  bladeMat.onBeforeCompile = (sh) => {
    sh.uniforms.time = U.time; sh.uniforms.wind = U.wind;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float time, wind; varying float vH; varying vec3 vTint;')
      .replace('#include <color_vertex>', '#include <color_vertex>\nvH = color.r;')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        vec3 ip = vec3(instanceMatrix[3][0], 0., instanceMatrix[3][2]);
        float k = color.r * color.r;
        float gust = sin(ip.x * .12 + time * 1.3) * .5 + sin(ip.z * .09 - time * .9 + ip.x * .03) * .5;
        float flutter = sin(time * 4.2 + ip.x * 3.1 + ip.z * 2.3) * .25;
        transformed.x += (gust * .16 + flutter * .05 + .06) * k * wind;
        transformed.z += (gust * .07 + flutter * .04) * k * wind;
        float hsh = fract(sin(dot(ip.xz, vec2(12.9898,78.233))) * 43758.5453);
        vTint = mix(vec3(.30,.46,.16), vec3(.52,.58,.24), hsh);`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vH; varying vec3 vTint;')
      .replace('#include <color_fragment>', 'diffuseColor.rgb = mix(vTint * .38, vTint * 1.25 + vec3(.06,.05,0.), vH);');
  };
  bladeMat.customProgramCacheKey = () => 'rm-blades';
  const grassGroup = new THREE.Group(); grassGroup.visible = false; scene.add(grassGroup);
  const CH = 16, area = { x0: -240, x1: -60, z0: 170, z1: 380 };
  const density = coarse ? 2 : 5;
  const chunks = [];
  const dummy = new THREE.Object3D();
  for (let cx = area.x0; cx < area.x1; cx += CH) for (let cz = area.z0; cz < area.z1; cz += CH) {
    const n = Math.round(CH * CH * density), mats = [];
    for (let i = 0; i < n; i++) {
      const x = cx + Math.random() * CH, z = cz + Math.random() * CH;
      if (roadAt(x, z) > 0.2 || inBuilding(x, z)) continue;
      dummy.position.set(x, heightAt(x, z) - 0.02, z);
      dummy.rotation.set(0, Math.random() * Math.PI * 2, 0);
      const s = 0.7 + Math.random() * 0.6; dummy.scale.set(s, s * (0.7 + Math.random() * 0.6), s);
      dummy.updateMatrix(); mats.push(dummy.matrix.clone());
    }
    if (!mats.length) continue;
    const im = new THREE.InstancedMesh(tuft, bladeMat, mats.length);
    mats.forEach((m, i) => im.setMatrixAt(i, m));
    im.receiveShadow = true;
    im.computeBoundingSphere();
    im.userData.center = new THREE.Vector3(cx + CH / 2, 0, cz + CH / 2);
    grassGroup.add(im); chunks.push(im);
  }

  // ------------------------------------------------------------ trees
  // The 2018 SpeedTree palms and broadleafs give way to grown deciduous trees
  // (tools/build-trees.py): spreading oaks, vase-shaped elms, small ornamentals
  // and clipped boxwood, each fitted to the height of the tree it replaces.
  const treeSrc = (await new GLTFLoader().parseAsync(await inflate(TREES), '')).scene;
  const kinds = {};
  const leafMats = [];
  treeSrc.children.slice().forEach((n) => {
    const k = n.name.replace(/^tree_/, '').replace(/\d+$/, '');
    n.userData.h = new THREE.Box3().setFromObject(n).max.y;
    n.traverse((o) => {
      if (!o.isMesh) return;
      const m = o.material;
      m.vertexColors = true;
      if (/leaves/.test(m.name)) { m.alphaTest = 0.5; m.side = THREE.DoubleSide; m.roughness = 0.75; m.envMapIntensity = 0.7; leafMats.includes(m) || leafMats.push(m); o.userData.leaves = true; }
      else { m.roughness = 0.95; m.envMapIntensity = 0.5; }
    });
    (kinds[k] ||= []).push(n);
  });
  const newTrees = new THREE.Group(); newTrees.visible = false; scene.add(newTrees);
  const leafMeshes = [];
  const hash = (x, z) => { const v = Math.sin(x * 12.9898 + z * 78.233) * 43758.5453; return v - Math.floor(v); };
  trees.forEach((g) => {
    const box = new THREE.Box3().setFromObject(g), h = box.max.y - box.min.y;
    const r = hash(g.position.x, g.position.z), kindOf = g.userData.kind || '';
    const k = /bush/.test(kindOf) ? 'box' : /Desktop/.test(kindOf) ? (r < 0.8 ? 'oak' : 'elm') : (r < 0.45 ? 'elm' : r < 0.8 ? 'oak' : 'round');
    const src = kinds[k][Math.floor(hash(g.position.z, g.position.x) * kinds[k].length)];
    const t = src.clone();
    const sc = THREE.MathUtils.clamp(h / src.userData.h, 0.75, 1.35) * (0.92 + r * 0.16);
    t.scale.setScalar(sc);
    t.position.copy(g.position).y -= 0.05;
    t.rotation.y = r * Math.PI * 2;
    t.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; if (o.userData.leaves) leafMeshes.push(o); } });
    newTrees.add(t);
  });

  // ------------------------------------------------------------ trees sway
  const treeMats = new Set();
  trees.forEach((g) => g.traverse((o) => { if (o.isMesh) treeMats.add(o.material); }));
  newTrees.traverse((o) => { if (o.isMesh) treeMats.add(o.material); });
  treeMats.forEach((m) => {
    const prev = m.onBeforeCompile;
    m.onBeforeCompile = (sh, r) => {
      prev && prev(sh, r);
      sh.uniforms.time = U.time; sh.uniforms.treeWind = U.treeWind ||= { value: 0 };
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nuniform float time, treeWind;')
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          { vec3 root = (modelMatrix * vec4(0.,0.,0.,1.)).xyz;
            float hgt = max(position.y, 0.) / 12.;
            float sway = sin(time * .9 + root.x * .1) * .5 + sin(time * 1.7 + root.z * .13) * .25;
            float leaf = sin(time * 5.3 + position.x * 2.1 + position.z * 1.7) * .04 * hgt;
            transformed.x += (sway * .35 * hgt * hgt + leaf) * treeWind;
            transformed.z += (sway * .15 * hgt * hgt + leaf) * treeWind; }`);
    };
    m.customProgramCacheKey = () => 'tree-' + m.uuid;
    m.needsUpdate = true;
  });
  U.treeWind ||= { value: 0 };

  // ------------------------------------------------------------ smoke
  const smokeTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    for (let i = 0; i < 26; i++) {
      const x = 64 + (Math.random() - .5) * 50, y = 64 + (Math.random() - .5) * 50, r = 14 + Math.random() * 26;
      const gr = g.createRadialGradient(x, y, 0, x, y, r);
      gr.addColorStop(0, 'rgba(255,255,255,0.22)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  // smoke from most of the rebuilt chimneys (not every hearth is lit)
  const uniq = CHIMNEYS.filter((c, i) => i % 3 !== 2);
  const smokeGroup = new THREE.Group(); smokeGroup.visible = false; scene.add(smokeGroup);
  const puffs = [];
  const emitters = uniq.map((p, i) => ({ p, acc: Math.random(), rate: i % 3 === 0 ? 0.9 : 0.45 }));
  function tickSmoke(dt, t) {
    const wx = 0.9 + Math.sin(t * 0.1) * 0.3, wz = 0.35;
    for (const e of emitters) {
      e.acc += dt * e.rate;
      while (e.acc > 1) {
        e.acc -= 1;
        const m = new THREE.SpriteMaterial({ map: smokeTex, color: '#d9d6d0', transparent: true, depthWrite: false, opacity: 0, fog: true });
        const s = new THREE.Sprite(m);
        s.position.set(e.p[0] + (Math.random() - .5) * .3, e.p[1] + 0.1, e.p[2] + (Math.random() - .5) * .3);
        s.userData = { age: 0, life: 9 + Math.random() * 4, spin: (Math.random() - .5) * .5, rise: 0.9 + Math.random() * 0.5 };
        m.rotation = Math.random() * 6.28;
        smokeGroup.add(s); puffs.push(s);
      }
    }
    for (let i = puffs.length - 1; i >= 0; i--) {
      const s = puffs[i], u = s.userData; u.age += dt;
      const k = u.age / u.life;
      if (k >= 1) { smokeGroup.remove(s); s.material.dispose(); puffs.splice(i, 1); continue; }
      s.position.y += u.rise * dt * (1 - k * .6);
      s.position.x += wx * dt * k * 1.6; s.position.z += wz * dt * k;
      s.material.rotation += u.spin * dt;
      const size = 0.6 + k * 4.2; s.scale.set(size, size, 1);
      s.material.opacity = 0.55 * Math.min(1, k * 6) * (1 - k) ** 1.5;
      s.material.color.setScalar(0.85 - k * 0.1);
    }
  }

  // ------------------------------------------------------------ birds
  const birdGeo = new THREE.BufferGeometry();
  birdGeo.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0.18, -0.55, 0, -0.05, 0, 0, -0.12, 0, 0, 0.18, 0, 0, -0.12, 0.55, 0, -0.05], 3));
  birdGeo.setAttribute('wing', new THREE.Float32BufferAttribute([0, 1, 0, 0, 0, 1], 1));
  const birdMat = new THREE.ShaderMaterial({
    side: THREE.DoubleSide, uniforms: { time: U.time },
    vertexShader: `attribute float wing; uniform float time; attribute vec3 instanceColor;
      void main(){ vec3 p = position; float ph = instanceMatrix[3][0] * 3.1 + instanceMatrix[3][2];
        p.y += wing * sin(time * 11. + ph) * .38; gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(p, 1.); }`,
    fragmentShader: 'void main(){ gl_FragColor = vec4(.12,.11,.1,1.); }',
  });
  const NB = 14;
  const birds = new THREE.InstancedMesh(birdGeo, birdMat, NB); birds.visible = false; birds.frustumCulled = false;
  const flock = Array.from({ length: NB }, (_, i) => ({ r: 22 + Math.random() * 30, h: 26 + Math.random() * 14, s: 0.18 + Math.random() * 0.08, o: Math.random() * 6.28, c: i < 8 ? [-150, 270] : [-175, 310] }));
  scene.add(birds);
  function tickBirds(t) {
    flock.forEach((b, i) => {
      const a = t * b.s + b.o;
      dummy.position.set(b.c[0] + Math.cos(a) * b.r, b.h + Math.sin(t * .7 + i) * 1.5, b.c[1] + Math.sin(a) * b.r);
      dummy.rotation.set(0, -a, Math.sin(t + i) * .2);
      dummy.scale.setScalar(1.3);
      dummy.updateMatrix(); birds.setMatrixAt(i, dummy.matrix);
    });
    birds.instanceMatrix.needsUpdate = true;
  }

  // ------------------------------------------------------------ dust motes in the light
  const NM = coarse ? 300 : 900;
  const moteGeo = new THREE.BufferGeometry();
  const mp = new Float32Array(NM * 3); for (let i = 0; i < NM; i++) { mp[i * 3] = (Math.random() - .5) * 40; mp[i * 3 + 1] = Math.random() * 8; mp[i * 3 + 2] = (Math.random() - .5) * 40; }
  moteGeo.setAttribute('position', new THREE.BufferAttribute(mp, 3));
  const motes = new THREE.Points(moteGeo, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { time: U.time, cam: { value: new THREE.Vector3() } },
    vertexShader: `uniform float time; uniform vec3 cam; varying float a;
      void main(){ vec3 p = position; p.x += sin(time*.3 + position.z) * 1.5 + time * .4; p.y += sin(time*.5 + position.x) * .6; p.z += cos(time*.25 + position.y) * 1.5;
        p = mod(p - cam + vec3(20., 0., 20.), vec3(40., 8., 40.)) + cam - vec3(20., 1.5, 20.);
        vec4 mv = modelViewMatrix * vec4(p, 1.); a = smoothstep(18., 2., -mv.z) * (.5 + .5 * sin(time * 2. + position.x * 7.));
        gl_PointSize = 2.2 * (8. / -mv.z) + 1.; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: 'varying float a; void main(){ float d = length(gl_PointCoord - .5); gl_FragColor = vec4(1.,.93,.75, a * .45 * smoothstep(.5,.0,d)); }',
  }));
  motes.frustumCulled = false; motes.visible = false; scene.add(motes);

  // ------------------------------------------------------------ post-processing
  const size = renderer.getDrawingBufferSize(new THREE.Vector2());
  const rt = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: coarse ? 0 : 4 });
  const composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  let gtao = null;
  if (!coarse) {
    gtao = new GTAOPass(scene, camera, size.x, size.y);
    gtao.output = GTAOPass.OUTPUT.Default;
    gtao.blendIntensity = 0.85;
    gtao.updateGtaoMaterial({ radius: 0.9, distanceExponent: 1.4, thickness: 1.2, scale: 1.1, samples: 12 });
    gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 12 });
    composer.addPass(gtao);
    // keep see-through things (clouds, smoke, motes) out of the occlusion pass
    const gtaoRender = gtao.render.bind(gtao);
    const skip = () => [clouds, smokeGroup, motes, birds, skyObj, ...leafMeshes];
    gtao.render = (...a) => {
      const vis = skip().map((o) => o.visible);
      skip().forEach((o) => (o.visible = false));
      try { gtaoRender(...a); } finally { skip().forEach((o, i) => (o.visible = vis[i])); }
    };
  }
  const bloom = new UnrealBloomPass(new THREE.Vector2(size.x, size.y), 0.22, 0.6, 0.92);
  composer.addPass(bloom);
  const grade = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, time: U.time },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }',
    fragmentShader: `uniform sampler2D tDiffuse; uniform float time; varying vec2 vUv;
      void main(){ vec4 c = texture2D(tDiffuse, vUv);
        // warm highlights, cool shadows, gentle vignette
        float l = dot(c.rgb, vec3(.2126,.7152,.0722));
        c.rgb = mix(c.rgb * vec3(.97,.99,1.04), c.rgb * vec3(1.05,1.01,.94), smoothstep(.1,.9,l));
        c.rgb = mix(vec3(l), c.rgb, 1.06);
        vec2 q = vUv - .5; c.rgb *= 1. - dot(q, q) * .55;
        gl_FragColor = c; }`,
  });
  composer.addPass(grade);
  composer.addPass(new OutputPass());

  // ------------------------------------------------------------ switching
  const swapped = [];
  town.traverse((o) => {
    if (!o.isMesh) return;
    const r = REMAP[o.material.name];
    if (r) swapped.push([o, o.material, r]);
  });
  const signs = [];
  town.traverse((o) => { if (o.isMesh && o.material.emissiveMap && !signs.includes(o.material)) signs.push(o.material); });
  const saved = {};
  let on = false;

  function enable() {
    if (on) return; on = true;
    swapped.forEach(([o, , r]) => (o.material = r));
    landmarkNodes.forEach((n) => (n.visible = false));
    roadMeshes.forEach((m) => (m.visible = false));
    lm.visible = true;
    trees.forEach((g) => (g.visible = false)); newTrees.visible = true;
    oldSigns.forEach((o) => (o.visible = false)); signGroup.visible = true;
    postless.forEach(([o, , ng]) => (o.geometry = ng));
    terrain.material = terrainMat;
    Object.assign(saved, { fog: scene.fog, env: scene.environment, exp: renderer.toneMappingExposure, sunI: sun.intensity, sunC: sun.color.clone(), hemiI: hemi.intensity, shadow: sun.shadow.mapSize.x });
    scene.fog = fogRemaster;
    scene.environment = envTex;
    renderer.toneMappingExposure = 0.72;
    sun.color.set('#ffe2b8'); sun.intensity = 3.6;
    hemi.intensity = 0.55;
    oldSky.visible = false; skyObj.visible = true; clouds.visible = true;
    grassGroup.visible = true; smokeGroup.visible = true; birds.visible = true; motes.visible = true;
    ctx.setOldSmoke(false);
    signs.forEach((m) => (m.emissiveIntensity = 0.12));
    U.treeWind.value = 1;
    setShadow(4096);
    if (flagParts) flagParts.forEach((p) => p.material.envMap = envTex);
  }
  function disable() {
    if (!on) return; on = false;
    swapped.forEach(([o, orig]) => (o.material = orig));
    landmarkNodes.forEach((n) => (n.visible = true));
    roadMeshes.forEach((m) => (m.visible = true));
    lm.visible = false;
    trees.forEach((g) => (g.visible = true)); newTrees.visible = false;
    oldSigns.forEach((o) => (o.visible = true)); signGroup.visible = false;
    postless.forEach(([o, g]) => (o.geometry = g));
    terrain.material = terrainOrig;
    scene.fog = saved.fog; scene.environment = saved.env;
    renderer.toneMappingExposure = saved.exp;
    sun.color.copy(saved.sunC); sun.intensity = saved.sunI; hemi.intensity = saved.hemiI;
    oldSky.visible = true; skyObj.visible = false; clouds.visible = false;
    grassGroup.visible = false; smokeGroup.visible = false; birds.visible = false; motes.visible = false;
    ctx.setOldSmoke(true);
    signs.forEach((m) => (m.emissiveIntensity = 0.45));
    U.treeWind.value = 0;
    setShadow(saved.shadow);
  }
  function setShadow(n) {
    if (sun.shadow.mapSize.x === n) return;
    sun.shadow.mapSize.set(n, n);
    if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
    const r = n > 2048 ? 70 : 90;
    Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r });
    sun.shadow.camera.updateProjectionMatrix();
  }

  const tmp = new THREE.Vector3();
  function update(dt, t) {
    U.time.value = t;
    if (!on) return;
    // sun follows the camera so its shadow map stays sharp around the viewer
    tmp.copy(sunDir).multiplyScalar(160);
    sun.position.copy(camera.position).add(tmp);
    sun.target.position.copy(camera.position);
    skyObj.position.copy(camera.position);
    clouds.position.x = camera.position.x; clouds.position.z = camera.position.z;
    motes.material.uniforms.cam.value.copy(camera.position);
    for (const c of chunks) c.visible = c.userData.center.distanceTo(tmp.set(camera.position.x, 0, camera.position.z)) < (coarse ? 55 : 85);
    tickSmoke(dt, t);
    tickBirds(t);
  }
  function render() { composer.render(); }
  function resize(w, h) {
    const px = renderer.getPixelRatio();
    composer.setPixelRatio(px);
    composer.setSize(w, h);
    if (gtao) gtao.setSize(w * px, h * px);
  }

  return { enable, disable, update, render, resize, get on() { return on; } };
}
