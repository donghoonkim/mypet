<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

// props 는 마운트 시점에 한 번만 읽는다. 값을 바꾸려면 부모에서 :key 로 다시 마운트한다.
const props = defineProps({
  modelUrl: { type: String, default: `${import.meta.env.BASE_URL}assets/pet.glb` },
  verticalRotate: { type: Boolean, default: false },   // 위아래 회전 허용
  zoom: { type: Boolean, default: false },             // 휠·핀치 줌 허용
})
// 사용자가 직접 반응시킨 경우(버튼·펫 터치)에만 알린다. 첫 자동 인사는 제외.
const emit = defineEmits(['react'])

// ── 설정 ─────────────────────────────────────────────────────────────────────
// 클립 이름은 아래 정규식으로 찾고, 못 찾은 액션은 간단한 절차적 모션(점프/흔들기)으로 대체된다.
const TARGET_HEIGHT = 1.95
const CLIP_ALIASES = {
  idle: /idle|stand|breath/i,
  hello: /hello|wave|greet/i,
  play: /play|jump|dance|spin/i,
  laugh: /laugh|smile|happy|joy|yes/i,
}
const REACTIONS = {
  hello: { lines: ['안녕! 반가워 👋', '왔구나! 기다렸어', '오늘도 만나서 좋아!'], fx: ['👋', '✨', '💚', '✨'], dur: 2.6 },
  play: { lines: ['야호! 신난다~', '한 번 더! 한 번 더!', '점프 점프!'], fx: ['🎾', '⭐', '🎵', '✨'], dur: 3.2 },
  laugh: { lines: ['꺄하하하!', '푸하핫, 간지러워~', '히히, 또 웃겨줘!'], fx: ['ㅋ', 'ㅋㅋ', '😆', '하하'], dur: 2.8 },
}
const POKE_ORDER = ['hello', 'laugh', 'play']
const BUTTONS = [
  { key: 'hello', icon: '👋', label: '인사하기' },
  { key: 'play', icon: '🎾', label: '놀아주기' },
  { key: 'laugh', icon: '😆', label: '웃겨주기' },
]
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]

// ── 화면 상태 (반응형) ───────────────────────────────────────────────────────
const visualEl = ref(null)
const canvasEl = ref(null)
const bubbleEl = ref(null)
const ready = ref(false)
const loadError = ref(false)
const activeKey = ref('idle')
const bubbleText = ref('')
const bubbleShow = ref(false)
const hintHidden = ref(false)
const hover = ref(false)
const dragging = ref(false)
const fxItems = ref([])
const sparkles = Array.from({ length: 14 }, () => ({
  '--x': 6 + Math.random() * 88 + '%',
  '--y': 8 + Math.random() * 70 + '%',
  '--s': 3 + Math.random() * 4 + 'px',
  '--t': 2.4 + Math.random() * 2.6 + 's',
  '--dl': -Math.random() * 5 + 's',
}))

// ── three.js 객체 ────────────────────────────────────────────────────────────
// Vue 의 반응형 프록시로 감싸면 three.js 가 깨지므로 ref 가 아닌 일반 변수로 둔다.
let renderer, scene, camera, controls, holder, resizeObserver
let mixer = null, current = null, headNode = null, headTopOffset = 0
let proc = null          // 클립이 없는 액션의 대체 모션 { key, t, dur }
let down = null, pokeIndex = 0, lastTouch = 0, fxId = 0
let bubbleTimer = 0, greetTimer = 0, disposed = false
const actions = {}       // key -> [actionA, actionB]  (같은 액션 재시작 때도 크로스페이드하려고 2벌)
const flip = {}
const clock = new THREE.Clock()
const raycaster = new THREE.Raycaster(), ndc = new THREE.Vector2()
const HOME = new THREE.Vector3(0, 1.6, 6.3)
const sph = new THREE.Spherical(), homeSph = new THREE.Spherical(), off = new THREE.Vector3(), _v = new THREE.Vector3()

function initScene() {
  const canvas = canvasEl.value
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50)
  camera.position.copy(HOME)

  controls = new OrbitControls(camera, canvas)
  controls.target.set(0, 1.2, 0)
  controls.enablePan = false
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.rotateSpeed = 0.8
  controls.enableZoom = props.zoom
  if (props.zoom) { controls.minDistance = 4.4; controls.maxDistance = 8.5 }
  if (props.verticalRotate) { controls.minPolarAngle = Math.PI * 0.22; controls.maxPolarAngle = Math.PI * 0.52 }
  controls.update()
  // 허용하지 않은 축은 기본 시점 값에 고정
  if (!props.verticalRotate) controls.minPolarAngle = controls.maxPolarAngle = controls.getPolarAngle()
  if (!props.zoom) controls.minDistance = controls.maxDistance = controls.getDistance()
  homeSph.setFromVector3(HOME.clone().sub(controls.target))

  scene.add(new THREE.HemisphereLight(0xffffff, 0xffe2c0, 1.5))
  const key = new THREE.DirectionalLight(0xfff4e0, 2.1)
  key.position.set(2.6, 5.5, 4.2)
  key.castShadow = true
  key.shadow.mapSize.set(1024, 1024)
  key.shadow.camera.left = key.shadow.camera.bottom = -3
  key.shadow.camera.right = key.shadow.camera.top = 3
  key.shadow.camera.far = 16
  key.shadow.radius = 6
  key.shadow.bias = -0.0005
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xbff5d8, 0.9)
  rim.position.set(-3.5, 2.5, -3)
  scene.add(rim)

  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(1.34, 1.44, 0.16, 72),
    new THREE.MeshStandardMaterial({ color: 0x8fe0b6, roughness: 0.9 }),
  )
  base.position.y = -0.08
  const top = new THREE.Mesh(
    new THREE.CircleGeometry(1.34, 72),
    new THREE.MeshStandardMaterial({ color: 0xd6f7e5, roughness: 1 }),
  )
  top.rotation.x = -Math.PI / 2
  top.position.y = 0.002
  top.receiveShadow = true
  scene.add(base, top)

  holder = new THREE.Group()   // 절차적 모션용 래퍼 (GLB 내부 노드는 건드리지 않는다)
  scene.add(holder)
}

// ── 모델 & 애니메이션 ────────────────────────────────────────────────────────
function loadModel() {
  new GLTFLoader().load(props.modelUrl, (gltf) => {
    if (disposed) return
    const model = gltf.scene
    model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false } })

    const box = new THREE.Box3().setFromObject(model)
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3())
    model.position.set(-center.x, -box.min.y, -center.z)
    holder.scale.setScalar(TARGET_HEIGHT / size.y)
    holder.add(model)
    holder.updateMatrixWorld(true)

    headNode = model.getObjectByName('Head') || null
    if (headNode) headTopOffset = TARGET_HEIGHT - headNode.getWorldPosition(new THREE.Vector3()).y

    mixer = new THREE.AnimationMixer(model)
    for (const [k, re] of Object.entries(CLIP_ALIASES)) {
      const clip = gltf.animations.find((c) => re.test(c.name))
      if (!clip) continue
      actions[k] = [mixer.clipAction(clip), mixer.clipAction(clip.clone())]
      flip[k] = 0
      if (k !== 'idle') for (const a of actions[k]) { a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true }
    }
    mixer.addEventListener('finished', (e) => { if (e.action === current) toIdle() })
    toIdle(0)

    ready.value = true
    greetTimer = setTimeout(() => react('hello', false), 500)
  }, undefined, (err) => {
    console.error(err)
    loadError.value = true
  })
}

function fadeTo(action, fade) {
  action.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).fadeIn(fade).play()
  if (current && current !== action) current.fadeOut(fade)
  current = action
}

function toIdle(fade = 0.35) {
  activeKey.value = 'idle'
  if (actions.idle) fadeTo(actions.idle[0], fade)
  else if (current) { current.fadeOut(fade); current = null }
}

function react(key, byUser = true) {
  if (!ready.value) return
  const r = REACTIONS[key]
  activeKey.value = key
  if (byUser) emit('react', key)

  if (actions[key]) {
    flip[key] ^= 1
    fadeTo(actions[key][flip[key]], 0.18)
  } else {
    proc = { key, t: 0, dur: r.dur }
  }
  say(pick(r.lines), r.dur * 1000 - 300)
  const p = anchor(0.55)
  burst(r.fx, p.x, p.y, 9)
}

const poke = () => react(POKE_ORDER[pokeIndex++ % POKE_ORDER.length])

// 클립이 없는 GLB 를 위한 대체 모션
function updateProc(dt) {
  holder.position.y = 0
  holder.rotation.set(0, 0, 0)
  if (!proc) return
  proc.t += dt
  const u = proc.t / proc.dur
  if (u >= 1) { proc = null; if (!current || activeKey.value !== 'idle') toIdle(); return }
  const env = Math.sin(Math.PI * u)
  if (proc.key === 'hello') holder.rotation.z = Math.sin(u * Math.PI * 6) * 0.14 * env
  if (proc.key === 'play') { holder.position.y = Math.abs(Math.sin(u * Math.PI * 3)) * 0.6 * env; holder.rotation.y = u * Math.PI * 2 }
  if (proc.key === 'laugh') { holder.position.y = Math.abs(Math.sin(u * Math.PI * 14)) * 0.06 * env; holder.rotation.x = -0.12 * env }
}

// ── 말풍선 & 이펙트 ──────────────────────────────────────────────────────────
/** 펫 머리 기준 화면 좌표. up=1 이면 정수리, 0 이면 목 높이. */
function anchor(up = 1) {
  const el = visualEl.value
  if (headNode) { headNode.getWorldPosition(_v); _v.y += headTopOffset * up }
  else _v.set(0, holder.position.y + TARGET_HEIGHT * (0.55 + 0.45 * up), 0)
  _v.project(camera)
  return { x: (_v.x * 0.5 + 0.5) * el.clientWidth, y: (-_v.y * 0.5 + 0.5) * el.clientHeight }
}

function say(text, ms = 2200) {
  bubbleText.value = text
  bubbleShow.value = true
  clearTimeout(bubbleTimer)
  bubbleTimer = setTimeout(() => { bubbleShow.value = false }, ms)
}

// 매 프레임 위치가 바뀌므로 반응형 상태를 거치지 않고 DOM 에 직접 쓴다.
function placeBubble() {
  const el = bubbleEl.value, box = visualEl.value
  const p = anchor(1)
  const half = el.offsetWidth / 2 + 8
  el.style.left = Math.min(Math.max(p.x, half), box.clientWidth - half) + 'px'
  el.style.top = Math.max(p.y - 14, el.offsetHeight + 6) + 'px'
}

function burst(items, x, y, count = 8) {
  for (let i = 0; i < count; i++) {
    const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.3
    const dist = 70 + Math.random() * 90
    fxItems.value.push({
      id: ++fxId,
      text: items[i % items.length],
      style: {
        left: x + 'px',
        top: y + 'px',
        '--dx': Math.cos(ang) * dist + 'px',
        '--dy': Math.sin(ang) * dist - 20 + 'px',
        '--rot': (Math.random() - 0.5) * 60 + 'deg',
        '--dl': i * 0.045 + 's',
        '--fs': 18 + Math.random() * 12 + 'px',
      },
    })
  }
}
const removeFx = (id) => { fxItems.value = fxItems.value.filter((f) => f.id !== id) }

// ── 입력 ─────────────────────────────────────────────────────────────────────
function hitsPet(ev) {
  const r = canvasEl.value.getBoundingClientRect()
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1)
  raycaster.setFromCamera(ndc, camera)
  return raycaster.intersectObject(holder, true).length > 0
}

const touch = () => { lastTouch = performance.now() }

function onPointerDown(ev) {
  down = { x: ev.clientX, y: ev.clientY, t: performance.now() }
  dragging.value = true
  touch()
}

function onPointerUp(ev) {
  dragging.value = false
  touch()
  if (!down) return
  const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y), held = performance.now() - down.t
  down = null
  if (moved > 8) { hintHidden.value = true; return }
  if (held > 500 || !ready.value || !hitsPet(ev)) return
  const r = canvasEl.value.getBoundingClientRect()
  burst(['💚', '💛', '💚'], ev.clientX - r.left, ev.clientY - r.top, 5)
  poke()
}

function onPointerMove(ev) {
  if (down || ev.pointerType !== 'mouse' || !ready.value) return
  hover.value = hitsPet(ev)
}

// ── 루프 ─────────────────────────────────────────────────────────────────────
function resize() {
  const w = visualEl.value.clientWidth, h = visualEl.value.clientHeight
  if (!w || !h) return
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  // 세로가 짧은 화면에서도 점프 높이까지 보이도록 시야각 보정
  camera.fov = THREE.MathUtils.clamp(30 * (0.78 / Math.min(camera.aspect, 0.78)), 30, 44)
  camera.updateProjectionMatrix()
}

function tick() {
  const dt = Math.min(clock.getDelta(), 0.05)
  if (mixer) mixer.update(dt)
  updateProc(dt)

  // 손을 떼고 잠시 지나면 정면으로 천천히 복귀
  if (!down && performance.now() - lastTouch > 2500) {
    off.copy(camera.position).sub(controls.target)
    sph.setFromVector3(off)
    const k = 1 - Math.exp(-dt * 2.2)
    sph.theta += (homeSph.theta - sph.theta) * k
    sph.phi += (homeSph.phi - sph.phi) * k
    sph.radius += (homeSph.radius - sph.radius) * k
    camera.position.copy(controls.target).add(off.setFromSpherical(sph))
  }
  controls.update()
  renderer.render(scene, camera)
  if (ready.value) placeBubble()
}

onMounted(() => {
  initScene()
  loadModel()
  window.addEventListener('pointerup', onPointerUp)
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(visualEl.value)
  resize()
  renderer.setAnimationLoop(tick)
})

onBeforeUnmount(() => {
  disposed = true
  clearTimeout(bubbleTimer)
  clearTimeout(greetTimer)
  window.removeEventListener('pointerup', onPointerUp)
  resizeObserver.disconnect()
  renderer.setAnimationLoop(null)
  controls.dispose()
  if (mixer) mixer.stopAllAction()
  scene.traverse((o) => {
    if (!o.isMesh) return
    o.geometry.dispose()
    for (const m of [].concat(o.material)) m.dispose()
  })
  renderer.dispose()
  renderer.forceContextLoss()   // 타입을 여러 번 오가도 WebGL 컨텍스트가 쌓이지 않게 바로 반납
})
</script>

<template>
  <header class="copy">
    <span class="badge">EVENT</span>
    <h1><em>몽이</em>랑 놀아주세요!</h1>
    <p>몽이를 톡 누르거나, 버튼으로 놀아줄 수 있어요</p>
  </header>

  <section ref="visualEl" class="visual" aria-label="3D 펫">
    <div class="sparkles" aria-hidden="true">
      <i v-for="(s, i) in sparkles" :key="i" :style="s"></i>
    </div>
    <canvas
      ref="canvasEl"
      class="pet-canvas"
      :class="{ 'is-hover': hover, 'is-drag': dragging }"
      tabindex="0"
      :aria-label="`몽이 3D 모델. ${verticalRotate ? '' : '좌우로 '}드래그해서 돌려볼 수 있어요.`"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @wheel.passive="touch"
      @keydown.enter.space.prevent="poke"
    ></canvas>
    <div class="fx-layer" aria-hidden="true">
      <span v-for="f in fxItems" :key="f.id" class="fx" :style="f.style" @animationend="removeFx(f.id)">{{ f.text }}</span>
    </div>
    <div ref="bubbleEl" class="bubble" :class="{ show: bubbleShow }" role="status" aria-live="polite">{{ bubbleText }}</div>
    <div v-if="!ready" class="status">
      <template v-if="!loadError">몽이를 부르는 중…</template>
      <template v-else>모델을 불러오지 못했어요.<br><code>{{ modelUrl }}</code> 경로를 확인해주세요.</template>
    </div>
    <div class="hint" :class="{ hide: hintHidden }">{{ verticalRotate ? '↻ 드래그해서 돌려보세요' : '↔ 좌우로 드래그해서 돌려보세요' }}</div>
  </section>

  <nav class="actions" aria-label="펫 액션">
    <button
      v-for="b in BUTTONS"
      :key="b.key"
      type="button"
      :class="{ 'is-on': activeKey === b.key }"
      :disabled="!ready"
      @click="react(b.key)"
    ><span class="ico">{{ b.icon }}</span>{{ b.label }}</button>
  </nav>
</template>

<style scoped>
/* ── 카피 ── */
.copy { padding: 16px 24px 0; text-align: center; position: relative; z-index: 2; pointer-events: none; }
.badge {
  display: inline-block; padding: 5px 12px; border-radius: 999px;
  background: var(--ink); color: #fff; font-size: 11px; font-weight: 800; letter-spacing: .12em;
}
.copy h1 { margin: 12px 0 6px; font-size: 26px; line-height: 1.25; letter-spacing: -.02em; }
.copy h1 em { font-style: normal; color: var(--mint-deep); }
.copy p { margin: 0; font-size: 14px; color: var(--ink-soft); }

/* ── 비주얼 영역 ── */
.visual { position: relative; flex: 1; min-height: 0; margin-top: -8px; }
.visual::before, .visual::after {   /* 배경 광원 */
  content: ""; position: absolute; border-radius: 50%; filter: blur(40px); pointer-events: none;
}
.visual::before { width: 70%; aspect-ratio: 1; left: 15%; top: 12%; background: radial-gradient(circle, #fff 0%, rgba(255,255,255,0) 70%); }
.visual::after  { width: 46%; aspect-ratio: 1; right: -12%; top: 4%; background: rgba(255, 214, 122, .45); }

.sparkles { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.sparkles i {
  position: absolute; left: var(--x); top: var(--y); width: var(--s); height: var(--s);
  background: #fff; border-radius: 50%; opacity: 0;
  box-shadow: 0 0 10px 2px rgba(255,255,255,.9);
  animation: twinkle var(--t) ease-in-out var(--dl) infinite;
}
@keyframes twinkle { 0%, 100% { opacity: 0; transform: translateY(6px) scale(.6); } 50% { opacity: .95; transform: translateY(-6px) scale(1); } }

.pet-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; cursor: grab; outline: none; }
.pet-canvas.is-hover { cursor: pointer; }
.pet-canvas.is-drag { cursor: grabbing; }

.bubble {
  position: absolute; left: 0; top: 0; z-index: 3; pointer-events: none;
  padding: 10px 16px; border-radius: 18px; background: var(--card); color: var(--ink);
  font-size: 15px; font-weight: 700; white-space: nowrap;
  box-shadow: 0 8px 22px rgba(22, 120, 74, .16);
  transform: translate(-50%, -100%) scale(.6); transform-origin: 50% 100%; opacity: 0;
  transition: opacity .18s ease, transform .28s cubic-bezier(.34, 1.56, .64, 1);
}
.bubble::after {
  content: ""; position: absolute; left: 50%; bottom: -6px; width: 14px; height: 14px;
  background: inherit; border-radius: 3px; transform: translateX(-50%) rotate(45deg);
}
.bubble.show { opacity: 1; transform: translate(-50%, -100%) scale(1); }

.fx-layer { position: absolute; inset: 0; pointer-events: none; overflow: hidden; z-index: 2; }
.fx {
  position: absolute; font-size: var(--fs, 22px); font-weight: 900; color: var(--mint-deep);
  text-shadow: 0 2px 0 #fff; will-change: transform, opacity;
  animation: pop 1.25s cubic-bezier(.2, .7, .3, 1) var(--dl, 0s) both;
}
@keyframes pop {
  0%   { transform: translate(-50%, -50%) scale(.2) rotate(0deg); opacity: 0; }
  18%  { opacity: 1; }
  100% { transform: translate(calc(-50% + var(--dx)), calc(-50% + var(--dy))) scale(1.1) rotate(var(--rot)); opacity: 0; }
}

.hint {
  position: absolute; left: 50%; bottom: 10px; transform: translateX(-50%); z-index: 2;
  padding: 6px 12px; border-radius: 999px; background: rgba(29, 43, 36, .08); color: var(--ink-soft);
  font-size: 12px; font-weight: 600; white-space: nowrap; pointer-events: none; transition: opacity .4s;
}
.hint.hide { opacity: 0; }

.status { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; padding: 24px;
  font-size: 14px; font-weight: 600; color: var(--ink-soft); line-height: 1.6; pointer-events: none; z-index: 1; }

/* ── 액션 버튼 ── */
.actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 12px 18px 14px; position: relative; z-index: 3; }
.actions button {
  appearance: none; border: 0; cursor: pointer; font: inherit; color: var(--ink);
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 14px 6px 12px; border-radius: 20px; background: var(--card);
  box-shadow: 0 6px 0 #d3eee0, 0 12px 24px rgba(22, 120, 74, .12);
  font-size: 14px; font-weight: 800; letter-spacing: -.01em;
  transition: transform .12s ease, box-shadow .12s ease, background .2s;
  -webkit-tap-highlight-color: transparent; touch-action: manipulation;
}
.actions button .ico { font-size: 28px; line-height: 1; transition: transform .3s cubic-bezier(.34, 1.56, .64, 1); }
.actions button:hover .ico { transform: scale(1.15) rotate(-8deg); }
.actions button:active, .actions button.is-on { transform: translateY(4px); box-shadow: 0 2px 0 #d3eee0, 0 4px 10px rgba(22, 120, 74, .12); }
.actions button.is-on { background: #e9fbf2; }
.actions button:focus-visible { outline: 3px solid var(--mint); outline-offset: 2px; }
.actions button:disabled { opacity: .5; cursor: default; }

@media (max-height: 620px) {
  .copy { padding-top: 10px; }
  .copy h1 { font-size: 21px; margin: 8px 0 4px; }
  .actions button { padding: 10px 6px 8px; }
  .actions button .ico { font-size: 22px; }
}
@media (prefers-reduced-motion: reduce) {
  .sparkles i { animation: none; opacity: .5; }
}
</style>
