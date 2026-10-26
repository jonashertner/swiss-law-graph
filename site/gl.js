// GPU side of the 3D map: sphere impostors, glowing ribbons, article points.
// Every sphere is a camera-facing quad whose fragment shader ray-traces the
// sphere, so 11,000 spheres cost 11,000 quads and stay perfectly round at any
// zoom. Positions are uploaded relative to a floating origin (main.js) so that
// deep zoom does not run out of float32 precision.
import * as THREE from "three";

// Two looks share one set of shaders: "light" (ink on paper, premultiplied alpha over the
// page) and "dark" (light on a night sky, additive). THEME's uniforms are shared by every
// material; setTheme() flips them and each material's blending.
export const THEME = { light: { value: 1 }, paper: { value: new THREE.Vector3(0.953, 0.945, 0.925) },
  fog: { value: new THREE.Vector3(1e9, 2e9, 0) } };   // depth fade: near, far (view-space depth), strength
const MATS = [];
function themed(mat) {
  mat.uniforms.uLight = THEME.light; mat.uniforms.uPaper = THEME.paper; mat.uniforms.uFog = THEME.fog;
  mat.userData.dark = { blending: mat.blending, blendSrc: mat.blendSrc, blendDst: mat.blendDst };
  MATS.push(mat);
  applyBlend(mat);
  return mat;
}
function applyBlend(m) {
  if (THEME.light.value > 0.5) { m.blending = THREE.CustomBlending; m.blendSrc = THREE.OneFactor; m.blendDst = THREE.OneMinusSrcAlphaFactor; }
  else Object.assign(m, m.userData.dark);
}
export function setTheme(light, paper) {
  THEME.light.value = light ? 1 : 0;
  if (paper) THEME.paper.value.set(...paper);
  for (const m of MATS) applyBlend(m);
}
export function setFog(near, far, strength) { THEME.fog.value.set(near, far, strength); }
// GLSL: the paper colour and the ink a display colour becomes on it (deeper, more saturated).
const INK = /* glsl */ `
  uniform float uLight; uniform vec3 uPaper; uniform vec3 uFog;
  vec3 ink(vec3 c) { return pow(max(c, vec3(0.0)), vec3(1.6)) * 0.8; }
  // atmospheric perspective: what lies behind the focus recedes (the far side of the tree)
  float fogA(float depth) { return 1.0 - uFog.z * smoothstep(uFog.x, uFog.y, depth); }
  const vec3 NIGHT = vec3(0.06, 0.08, 0.11);`;

const QUAD = new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0]);
const QUAD_INDEX = [0, 1, 2, 0, 2, 3];

function instancedQuad(n, attrs) {
  const g = new THREE.InstancedBufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(QUAD, 3));
  g.setIndex(QUAD_INDEX);
  for (const [name, size] of attrs) g.setAttribute(name, new THREE.InstancedBufferAttribute(new Float32Array(n * size), size));
  g.instanceCount = n;
  return g;
}

// Shared vertex stage: billboard large enough to hold the sphere's perspective silhouette.
const SPHERE_VERT = /* glsl */ `
  attribute vec3 iCenter; attribute float iRadius; attribute vec3 iColor; attribute vec4 iState;
  varying vec3 vCenter; varying float vRadius; varying vec3 vPos; varying vec3 vColor; varying vec4 vState;
  varying float vPix;
  uniform float uPixelScale; uniform float uMinPx;
  void main() {
    vec4 c = modelViewMatrix * vec4(iCenter, 1.0);
    float d = length(c.xyz);
    float r = max(iRadius, uMinPx * max(-c.z, 1e-9) / uPixelScale);   // never smaller than uMinPx on screen
    float grow = d > r * 1.0001 ? d / sqrt(max(d * d - r * r, 1e-20)) : 1e4;
    vec3 p = c.xyz + vec3(position.xy * r * min(grow, 40.0), 0.0);
    vCenter = c.xyz; vRadius = r; vPos = p; vColor = iColor; vState = iState;
    vPix = r / max(-c.z, 1e-9) * uPixelScale;           // projected radius in pixels
    gl_Position = projectionMatrix * vec4(p, 1.0);
  }`;

const RAYCAST = /* glsl */ `
  // ray from the eye through this fragment against the sphere (view space)
  bool hitSphere(out vec3 hit, out vec3 n) {
    vec3 dir = normalize(vPos);
    float b = dot(dir, vCenter);
    float cc = dot(vCenter, vCenter) - vRadius * vRadius;
    float disc = b * b - cc;
    if (disc < 0.0) return false;
    float t = b - sqrt(disc);
    if (t < 0.0) t = b + sqrt(disc);
    hit = dir * t;
    n = (hit - vCenter) / vRadius;
    return true;
  }`;

// Containers (SR areas, domains, cantons): flat discs on the SR plane, a fine bright rim
// over a faint fill. The plane is the ground plan; case law arcs above it, legislation below.
export function makeShells(n) {
  const geo = instancedQuad(n, [["iCenter", 3], ["iRadius", 1], ["iColor", 3], ["iState", 4]]);
  const mat = themed(new THREE.ShaderMaterial({
    uniforms: { uPixelScale: { value: 500 }, uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute vec3 iCenter; attribute float iRadius; attribute vec3 iColor; attribute vec4 iState;
      varying vec2 vUv; varying vec3 vColor; varying vec4 vState; varying float vPix; varying float vDepth;
      uniform float uPixelScale;
      void main() {
        vec4 c = modelViewMatrix * vec4(iCenter, 1.0);
        vPix = iRadius / max(length(c.xyz), 1e-9) * uPixelScale;      // apparent radius in pixels
        vUv = position.xy * 1.02;
        vColor = iColor; vState = iState;
        vec4 mv = modelViewMatrix * vec4(iCenter + vec3(vUv.x, 0.0, vUv.y) * iRadius, 1.0);
        vDepth = -mv.z;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      varying vec2 vUv; varying vec3 vColor; varying vec4 vState; varying float vPix; varying float vDepth;
      ${INK}
      void main() {
        float d = length(vUv);
        float aa = max(fwidth(d), 1e-5);
        float rim = (1.0 - smoothstep(0.0, 1.6 * aa, abs(d - 1.0 + 1.2 * aa)));       // ~1.5 px line
        float inner = exp((d - 1.0) / max(aa * 18.0, 0.02)) * step(d, 1.0);            // glow just inside the rim
        float fill = step(d, 1.0) * 0.022;
        float tiny = smoothstep(2.0, 7.0, vPix);
        float big = 1.0 - smoothstep(2500.0, 9000.0, vPix) * 0.85;                  // enormous discs recede
        if (uLight > 0.5) {         // paper: an ink outline over a faint wash; nesting deepens the wash
          float a = vState.x * vState.y * tiny * (rim * 0.5 + inner * 0.04 + fill * 1.7 * big) * fogA(vDepth);
          if (a < 0.002) discard;
          gl_FragColor = vec4(ink(vColor) * a, a);
          return;
        }
        float a = vState.x * vState.y * tiny * (rim * 0.75 + inner * 0.16 + fill * big) * fogA(vDepth);
        if (a < 0.002) discard;
        gl_FragColor = vec4(vColor * a, a);
      }`,
    extensions: { derivatives: true },
    transparent: true, depthWrite: false, depthTest: true, side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  }));
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 1;
  return mesh;
}

// Acts: solid luminous orbs with correct depth.
export function makeOrbs(n) {
  const geo = instancedQuad(n, [["iCenter", 3], ["iRadius", 1], ["iColor", 3], ["iState", 4]]);
  const mat = themed(new THREE.ShaderMaterial({
    uniforms: { uPixelScale: { value: 500 }, uTime: { value: 0 }, uMinPx: { value: 0 } },
    vertexShader: SPHERE_VERT,
    fragmentShader: /* glsl */ `
      varying vec3 vCenter; varying float vRadius; varying vec3 vPos; varying vec3 vColor; varying vec4 vState;
      varying float vPix;
      uniform float uTime;
      uniform mat4 projectionMatrix;   // three.js declares it for the vertex stage only
      ${INK}
      ${RAYCAST}
      void main() {
        if (dot(vCenter, vCenter) < vRadius * vRadius) discard;   // the eye is inside: show the articles
        vec3 hit, n;
        if (!hitSphere(hit, n)) discard;
        // state: x = visibility, y = brightness (citations), z = opened (articles shown), w = highlight
        vec3 v = normalize(-hit);
        vec3 l = normalize(vec3(0.35, 0.8, 0.45));
        float diff = clamp(dot(n, l), 0.0, 1.0);
        float facing = clamp(dot(n, v), 0.0, 1.0);
        float rim = pow(1.0 - facing, mix(2.2, 5.0, smoothstep(40.0, 500.0, vPix)));   // big spheres: thin rim
        float b = vState.y;
        float open = vState.z;
        if (uLight > 0.5) {          // paper: a matte body, deeper the more it is cited; selection = dark ring
          vec3 body = mix(uPaper, ink(vColor), 0.7 + 0.3 * b);      // even an uncited act reads as ink, not paper
          float spec = pow(max(dot(n, normalize(l + v)), 0.0), 36.0);
          float edge = mix(0.55, 0.3, smoothstep(3.0, 24.0, vPix));   // small spheres: a darker outline to stand out
          vec3 c = body * (0.66 + 0.4 * diff) * (1.0 - edge * rim) + vec3(0.3) * spec;
          c = mix(c, NIGHT, clamp(vState.w * 2.4 * smoothstep(0.45, 0.8, 1.0 - facing), 0.0, 1.0));
          float a = vState.x * smoothstep(0.35, 1.2, vPix) * mix(1.0, 0.05 + 0.3 * rim * rim, open);
          a *= mix(1.0, fogA(-vCenter.z), 0.85);
          gl_FragColor = vec4(c * a, a);
          vec4 clip = projectionMatrix * vec4(hit, 1.0);
          gl_FragDepthEXT = clamp((clip.z / clip.w) * 0.5 + 0.5, 0.0, 1.0);
          return;
        }
        vec3 col = vColor * (0.2 + 0.6 * diff) * (0.5 + 0.65 * b)        // lit body, brighter when cited more
                 + vColor * rim * (0.45 + 0.75 * b)                      // luminous rim
                 + vec3(1.0) * vState.w * (0.04 + 0.7 * rim * rim);     // selection / hover: a white rim
        float a = vState.x * smoothstep(0.35, 1.6, vPix) * mix(1.0, 0.04 + 0.3 * rim * rim, open) * mix(1.0, fogA(-vCenter.z), 0.85);
        gl_FragColor = vec4(col * a, a);
        vec4 clip = projectionMatrix * vec4(hit, 1.0);
        gl_FragDepthEXT = clamp((clip.z / clip.w) * 0.5 + 0.5, 0.0, 1.0);
      }`,
    extensions: { fragDepth: true },
    transparent: true, depthWrite: true, depthTest: true,
    blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
  }));
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 2;
  return mesh;
}

// Article dots: round glowing points over the act's floor plan; each rises to its
// height (iCenter.y, decisions citing the article) as the act opens (uFade).
export function makeDots(positions, radii, colors, levels) {
  const n = radii.length;
  const geo = instancedQuad(n, [["iCenter", 3], ["iRadius", 1], ["iColor", 3], ["iState", 4]]);
  geo.attributes.iCenter.array.set(positions);
  geo.attributes.iRadius.array.set(radii);
  geo.attributes.iColor.array.set(colors);
  geo.attributes.iState.array.set(levels);
  const mat = themed(new THREE.ShaderMaterial({
    uniforms: { uPixelScale: { value: 500 }, uFade: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute vec3 iCenter; attribute float iRadius; attribute vec3 iColor; attribute vec4 iState;
      varying vec2 vUv; varying vec3 vColor; varying vec4 vState; varying float vPix;
      uniform float uPixelScale;
      uniform float uFade;
      void main() {
        vec4 c = modelViewMatrix * vec4(iCenter.x, iCenter.y * uFade, iCenter.z, 1.0);
        float pix = iRadius / max(-c.z, 1e-9) * uPixelScale;
        float r = iRadius * max(1.0, 1.2 / max(pix, 1e-6));          // never thinner than ~1 px
        c.xy += position.xy * r * 1.8;                                 // room for the halo
        vUv = position.xy * 1.8; vColor = iColor; vState = iState; vPix = pix;
        gl_Position = projectionMatrix * c;
      }`,
    fragmentShader: /* glsl */ `
      varying vec2 vUv; varying vec3 vColor; varying vec4 vState; varying float vPix;
      uniform float uFade;
      ${INK}
      void main() {
        // state: x = citations share (0 = uncited), y = repealed, z = highlight, w = dim
        float d = length(vUv);
        float core = 1.0 - smoothstep(0.82, 1.0, d);
        float halo = exp(-d * d * 2.2) * 0.55;
        float ring = smoothstep(0.7, 0.85, d) * (1.0 - smoothstep(0.9, 1.0, d));
        float cited = step(0.0001, vState.x);
        float body = vState.y > 0.5 ? ring * 0.6 : mix(core * 0.3, core * (0.55 + 0.45 * vState.x) + halo * (0.3 + 1.2 * vState.x), cited);
        body = max(body, vState.z * (ring * 1.6 + halo * 0.8));          // selected: bright ring and halo
        vec3 col = mix(vColor, vec3(1.0), 0.2 * vState.x + vState.z * 0.8);
        if (uLight > 0.5) {
          body = vState.y > 0.5 ? ring * 0.7 : mix(core * 0.35, core * (0.7 + 0.3 * vState.x) + halo * 0.25 * vState.x, cited);
          body = max(body, vState.z * (ring * 1.6 + halo * 0.3));
          col = mix(ink(vColor), NIGHT, vState.z * 0.85);
        }
        float a = body * uFade * vState.w;
        if (a < 0.003) discard;
        gl_FragColor = vec4(col * a, a);
      }`,
    transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending,
  }));
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 3;
  return mesh;
}

// Thin vertical stems from the floor to each risen article dot.
export function makeStems(positions, colors) {
  const n = positions.length / 3;
  const pos = new Float32Array(n * 6), col = new Float32Array(n * 6), top = new Float32Array(n * 2);
  for (let k = 0; k < n; k++) {
    const x = positions[k * 3], y = positions[k * 3 + 1], z = positions[k * 3 + 2];
    pos.set([x, 0, z, x, y, z], k * 6);
    col.set([colors[k * 3], colors[k * 3 + 1], colors[k * 3 + 2], colors[k * 3], colors[k * 3 + 1], colors[k * 3 + 2]], k * 6);
    top.set([0, 1], k * 2);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aColor", new THREE.BufferAttribute(col, 3));
  g.setAttribute("aTop", new THREE.BufferAttribute(top, 1));
  const mat = themed(new THREE.ShaderMaterial({
    uniforms: { uFade: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute vec3 aColor; attribute float aTop; varying vec3 vColor; varying float vTop; uniform float uFade;
      void main() { vColor = aColor; vTop = aTop; gl_Position = projectionMatrix * modelViewMatrix * vec4(position.x, position.y * uFade, position.z, 1.0); }`,
    fragmentShader: /* glsl */ `
      varying vec3 vColor; varying float vTop; uniform float uFade;
      ${INK}
      void main() {
        float a = uFade * (0.08 + 0.32 * vTop);
        gl_FragColor = uLight > 0.5 ? vec4(ink(vColor) * a * 1.3, a * 1.3) : vec4(vColor * a, a);
      }`,
    transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending,
  }));
  const m = new THREE.LineSegments(g, mat);
  m.frustumCulled = false;
  m.renderOrder = 3;
  return m;
}

// Glowing ribbons along precomputed polylines; pulses travel from source to target.
export function makeRibbons() {
  const mat = themed(new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uViewport: { value: new THREE.Vector2(1, 1) }, uGlobal: { value: 1 } },
    vertexShader: /* glsl */ `
      attribute vec3 aNext; attribute float aSide; attribute float aT; attribute float aWidth;
      attribute vec3 aColor; attribute float aAlpha; attribute float aFlow;
      varying float vSide; varying float vT; varying vec3 vColor; varying float vAlpha; varying float vFlow;
      varying float vDepth;
      uniform vec2 uViewport;
      void main() {
        vDepth = -(modelViewMatrix * vec4(position, 1.0)).z;
        vec4 a = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        vec4 b = projectionMatrix * modelViewMatrix * vec4(aNext, 1.0);
        vec2 sa = a.xy / max(a.w, 1e-9) * uViewport, sb = b.xy / max(b.w, 1e-9) * uViewport;
        vec2 dir = normalize(sb - sa + vec2(1e-6, 0.0));
        vec2 nrm = vec2(-dir.y, dir.x);
        a.xy += nrm * aSide * aWidth / uViewport * a.w;
        gl_Position = a;
        vSide = aSide; vT = aT; vColor = aColor; vAlpha = aAlpha; vFlow = aFlow;
      }`,
    fragmentShader: /* glsl */ `
      varying float vSide; varying float vT; varying vec3 vColor; varying float vAlpha; varying float vFlow;
      varying float vDepth;
      uniform float uTime; uniform float uGlobal;
      ${INK}
      void main() {
        float edge = 1.0 - smoothstep(0.15, 1.0, abs(vSide));
        // pulses travel from the citing act to the cited one (legislation) or both ways (practice)
        float p = fract(vT * 6.0 - uTime * 0.35 * sign(vFlow + 1e-6));
        float pulse = smoothstep(0.0, 0.05, p) * (1.0 - smoothstep(0.05, 0.28, p));
        float a = vAlpha * uGlobal * edge * (0.55 + 1.6 * pulse * abs(vFlow)) * fogA(vDepth);
        if (uLight > 0.5) { a = min(a * 1.1, 0.95); gl_FragColor = vec4(ink(vColor) * a, a); return; }
        gl_FragColor = vec4(vColor * a, a);
      }`,
    transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,   // the strip is expanded in screen space; its winding says nothing
  }));
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 4;
  return mesh;
}

// Fill a ribbon geometry from polylines: [{pts: Float32Array xyz…, width, color[3], alpha, flow, taper}].
// A tapered ribbon narrows from source to target, so direction reads even when still.
export function setRibbons(mesh, lines) {
  let nv = 0, ni = 0;
  for (const l of lines) { const k = l.pts.length / 3; nv += k * 2; ni += (k - 1) * 6; }
  const pos = new Float32Array(nv * 3), nxt = new Float32Array(nv * 3), side = new Float32Array(nv),
    tt = new Float32Array(nv), wid = new Float32Array(nv), col = new Float32Array(nv * 3),
    alp = new Float32Array(nv), flow = new Float32Array(nv);
  const idx = nv > 65535 ? new Uint32Array(ni) : new Uint16Array(ni);
  let v = 0, ii = 0;
  for (const l of lines) {
    const p = l.pts, k = p.length / 3;
    for (let j = 0; j < k; j++) {
      const jn = j < k - 1 ? j + 1 : j - 1, sgn = j < k - 1 ? 1 : -1;
      for (const s of [-1, 1]) {
        pos.set([p[j * 3], p[j * 3 + 1], p[j * 3 + 2]], v * 3);
        nxt.set([p[jn * 3], p[jn * 3 + 1], p[jn * 3 + 2]], v * 3);
        side[v] = s * sgn; tt[v] = j / (k - 1); wid[v] = l.taper ? l.width * (1 - 0.72 * j / (k - 1)) : l.width;
        col.set(l.color, v * 3); alp[v] = l.alpha; flow[v] = l.flow;
        v++;
      }
      if (j < k - 1) {
        const a = v - 2;
        idx.set([a, a + 1, a + 2, a + 1, a + 3, a + 2], ii);
        ii += 6;
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aNext", new THREE.BufferAttribute(nxt, 3));
  g.setAttribute("aSide", new THREE.BufferAttribute(side, 1));
  g.setAttribute("aT", new THREE.BufferAttribute(tt, 1));
  g.setAttribute("aWidth", new THREE.BufferAttribute(wid, 1));
  g.setAttribute("aColor", new THREE.BufferAttribute(col, 3));
  g.setAttribute("aAlpha", new THREE.BufferAttribute(alp, 1));
  g.setAttribute("aFlow", new THREE.BufferAttribute(flow, 1));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  mesh.geometry.dispose();
  mesh.geometry = g;
}

// A faint field of stars far away, for depth.
export function makeStars(count = 2600) {
  const pos = new Float32Array(count * 3), size = new Float32Array(count);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < count; i++) {
    const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, r = Math.sqrt(1 - u * u);
    pos.set([r * Math.cos(th), u, r * Math.sin(th)], i * 3);
    size[i] = 0.4 + Math.pow(rnd(), 6) * 2.4;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: { uScale: { value: 1 } },
    vertexShader: /* glsl */ `
      attribute float aSize; varying float vA; uniform float uScale;
      void main() {
        vec4 v = viewMatrix * vec4(position, 0.0);          // direction only: stars sit at infinity
        gl_Position = projectionMatrix * vec4(v.xyz, 1.0);
        gl_Position.z = gl_Position.w * 0.9999;
        gl_PointSize = aSize * uScale; vA = 0.25 + 0.5 * aSize / 2.8;
      }`,
    fragmentShader: /* glsl */ `
      varying float vA;
      void main() { float d = length(gl_PointCoord - 0.5); float a = vA * (1.0 - smoothstep(0.2, 0.5, d)); gl_FragColor = vec4(vec3(0.75, 0.82, 1.0) * a, a); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const pts = new THREE.Points(g, mat);
  pts.frustumCulled = false;
  pts.renderOrder = 0;
  return pts;
}
