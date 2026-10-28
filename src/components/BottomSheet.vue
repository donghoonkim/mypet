<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// 손으로 끌어올리는 바텀시트.
// 접힘: peek 를 주면 항상 그 높이만큼 보인다. 없으면 헤더(손잡이 + header 슬롯) 높이 + 하단 안전영역만큼 보인다.
//       header 슬롯은 넣어도 되고 안 넣어도 된다(없으면 손잡이만).
// 펼침: 기본은 내용 높이만큼만 올라온다. height 로 높이를 직접 정할 수 있고,
//       어느 경우든 화면 위쪽 topGap 은 남긴다(넘치는 내용은 본문 안에서 스크롤).
// 헤더는 항상 끌거나 탭해서 여닫을 수 있다. 조금이라도 끌어올리면 펼쳐진다.
// 본문(bodyToggle=true 일 때): 접힌 상태에서 보이는 본문 부분도 끌거나 탭해서 열 수 있고,
//                            펼친 상태에서는 본문을 맨 위까지 올린 뒤 아래로 당겨도 닫힌다.
const props = defineProps({
  // 접힌 상태로 보이는 높이(px). 지정하면 헤더 높이와 상관없이 항상 이 값이 기준이 된다.
  peek: { type: Number, default: null },
  // 펼친 높이. null = 내용 높이에 맞춤, 숫자 = px, 문자열 = CSS 값('60%', '420px', '50dvh' 등)
  height: { type: [Number, String], default: null },
  topGap: { type: Number, default: 56 },   // 펼쳤을 때 위쪽에 최소한 남길 여백(px)
  label: { type: String, default: '바텀시트' },
  // 본문 영역으로도 여닫을지. false 면 본문에서는 열기·닫기가 동작하지 않고 헤더로만 여닫는다.
  bodyToggle: { type: Boolean, default: true },
})
const open = defineModel('open', { type: Boolean, default: false })

const sheetEl = ref(null)
const headerEl = ref(null)
const bodyEl = ref(null)
const peekHeight = ref(0)   // 실제 접힌 높이. 같은 높이의 빈 공간(spacer)을 둬서 시트 뒤 내용이 가려지지 않게 한다
const y = ref(0)            // 펼친 위치에서 아래로 내려간 거리. 0 = 펼침, maxY = 접힘
const maxY = ref(0)
const dragging = ref(false)
const measured = ref(false) // 첫 측정 전에는 트랜지션 없이 바로 자리 잡는다
const progress = computed(() => (maxY.value ? 1 - Math.min(Math.max(y.value / maxY.value, 0), 1) : 0))
const sheetStyle = computed(() => ({
  height: typeof props.height === 'number' ? props.height + 'px' : props.height ?? undefined,
  maxHeight: `calc(100% - ${props.topGap}px)`,
  transform: `translateY(${y.value}px)`,
}))

const DRAG_START = 6         // 이만큼 움직여야 드래그로 본다(px)
const FLICK = 0.35           // 이 속도(px/ms) 이상으로 놓으면 방향대로 여닫는다
let safeBottom = 0, resizeObserver, start = null, touch = null, samples = []

// 접힌 높이 = peek 값(있으면) 또는 헤더 높이 + 하단 안전영역, 접힐 때 내려가는 거리(maxY) = 시트 높이 - 접힌 높이
function measure() {
  peekHeight.value = props.peek ?? headerEl.value.offsetHeight + safeBottom
  maxY.value = Math.max(sheetEl.value.offsetHeight - peekHeight.value, 0)
  if (!dragging.value) y.value = open.value ? 0 : maxY.value
}

watch(open, (v) => { if (!dragging.value) y.value = v ? 0 : maxY.value })
watch(() => props.peek, () => measure())

// 범위를 넘겨 끌면 고무줄처럼 조금만 따라온다
const rubber = (d) => 60 * (1 - Math.exp(-d / 120))

function dragTo(raw, t) {
  const m = maxY.value
  y.value = raw < 0 ? -rubber(-raw) : raw > m ? m + rubber(raw - m) : raw
  samples.push({ t, y: y.value })
  samples = samples.filter((s) => t - s.t < 100)
}

function release(t, fromY) {
  dragging.value = false
  // 놓기 직전 100ms 동안의 움직임으로 속도를 잰다 (끌다가 멈춘 뒤 놓으면 0)
  const recent = samples.filter((s) => t - s.t < 100)
  const a = recent[0], b = recent[recent.length - 1]
  const v = a && b && b.t > a.t ? (b.y - a.y) / (b.t - a.t) : 0   // + 는 아래 방향
  // 시작 위치보다 조금이라도 위로 끌었으면 무조건 펼친다.
  // 아래로 끈 경우에만 속도(플릭)·절반 위치로 닫을지 정한다.
  const close = y.value < fromY ? false : Math.abs(v) > FLICK ? v > 0 : y.value > maxY.value / 2
  open.value = !close
  y.value = close ? maxY.value : 0
}

// ── 포인터 드래그 (마우스·터치 공통) ──
// 헤더: 항상 / 본문: 접힌 상태이고 bodyToggle 일 때만 (펼친 상태의 본문은 버튼·스크롤에 양보)
function onPointerDown(e) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  const onHeader = headerEl.value.contains(e.target)
  if (!onHeader && (open.value || !props.bodyToggle)) return
  start = { py: e.clientY, y: y.value, moved: false }
  samples = [{ t: e.timeStamp, y: y.value }]
  e.currentTarget.setPointerCapture(e.pointerId)
}

function onPointerMove(e) {
  if (!start) return
  const dy = e.clientY - start.py
  if (!start.moved) {
    if (Math.abs(dy) < DRAG_START) return
    start.moved = true
    dragging.value = true
  }
  dragTo(start.y + dy, e.timeStamp)
}

function onPointerUp(e) {
  if (!start) return
  const { moved, y: fromY } = start
  start = null
  if (moved) release(e.timeStamp, fromY)
  else open.value = !open.value   // 탭하면 토글
}

function onPointerCancel(e) {
  if (!start) return
  const { moved, y: fromY } = start
  start = null
  if (moved) release(e.timeStamp, fromY)
}

// ── 본문: 맨 위에서 아래로 당기면 시트를 끌어내린다 (그 외에는 기본 스크롤) ──
function onTouchStart(e) {
  if (!props.bodyToggle || !open.value || e.touches.length > 1) return
  touch = { py: e.touches[0].clientY, y: y.value, active: null }
  samples = [{ t: e.timeStamp, y: y.value }]
}

function onTouchMove(e) {
  if (!touch) return
  const dy = e.touches[0].clientY - touch.py
  if (touch.active === null) {
    if (dy < 0 || bodyEl.value.scrollTop > 0) { touch.active = false; return }
    e.preventDefault()   // 네이티브 스크롤이 시작되기 전에 막아야 이후에도 막을 수 있다
    if (dy < DRAG_START) return
    touch.active = true
    dragging.value = true
  }
  if (!touch.active) return
  e.preventDefault()
  dragTo(touch.y + dy, e.timeStamp)
}

function onTouchEnd(e) {
  if (touch?.active) release(e.timeStamp, touch.y)
  touch = null
}

const onKeyDown = (e) => { if (e.key === 'Escape' && open.value) open.value = false }

onMounted(() => {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:fixed;bottom:0;height:env(safe-area-inset-bottom);visibility:hidden;pointer-events:none'
  document.body.append(probe)
  safeBottom = probe.offsetHeight
  probe.remove()

  measure()
  requestAnimationFrame(() => { measured.value = true })
  resizeObserver = new ResizeObserver(measure)
  resizeObserver.observe(sheetEl.value)
  resizeObserver.observe(headerEl.value)
  window.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  resizeObserver.disconnect()
  window.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <!-- 접힌 시트 높이만큼 자리를 차지해서, 부모 레이아웃의 내용이 시트 뒤로 가려지지 않게 한다 -->
  <div class="sheet-spacer" aria-hidden="true" :style="{ height: peekHeight + 'px' }"></div>

  <div
    class="sheet-backdrop"
    :class="{ on: open, dragging, measured }"
    :style="{ opacity: progress }"
    aria-hidden="true"
    @click="open = false"
  ></div>

  <section
    ref="sheetEl"
    class="sheet"
    :class="{ open, dragging, measured, 'body-toggle': bodyToggle }"
    :style="sheetStyle"
    :aria-label="label"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
  >
    <div
      ref="headerEl"
      class="sheet-header"
      :class="{ bare: !$slots.header }"
      role="button"
      tabindex="0"
      :aria-expanded="open"
      :aria-label="`${label} ${open ? '닫기' : '열기'}`"
      @keydown.enter.space.prevent="open = !open"
    >
      <span class="handle" aria-hidden="true"></span>
      <slot name="header" :open="open" :progress="progress" />
    </div>

    <div
      ref="bodyEl"
      class="sheet-body"
      :inert="!open"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
      @touchcancel="onTouchEnd"
    >
      <slot :open="open" />
    </div>
  </section>
</template>

<style scoped>
.sheet-spacer { flex: none; }

.sheet-backdrop {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(16, 32, 24, .42);
  pointer-events: none;
}
.sheet-backdrop.on { pointer-events: auto; }

.sheet {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 11;
  display: flex; flex-direction: column;
  background: #fff; border-radius: 24px 24px 0 0;
  box-shadow: 0 -10px 30px rgba(22, 80, 50, .14);
  will-change: transform;
}
/* 위로 고무줄처럼 당겼을 때 아래가 비어 보이지 않게 */
.sheet::after { content: ""; position: absolute; left: 0; right: 0; top: 100%; height: 80px; background: inherit; }

.sheet.measured:not(.dragging) { transition: transform .38s cubic-bezier(.2, .8, .2, 1); }
.sheet-backdrop.measured:not(.dragging) { transition: opacity .38s cubic-bezier(.2, .8, .2, 1); }

.sheet-header {
  flex: none; padding: 10px 20px 14px;
  cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none;
  outline: none; border-radius: 24px 24px 0 0;
  -webkit-tap-highlight-color: transparent;
}
.sheet.dragging .sheet-header { cursor: grabbing; }
/* 접힌 상태: 브라우저 제스처를 막고, bodyToggle 이면 보이는 부분 전체가 손잡이 역할 */
.sheet:not(.open) { touch-action: none; user-select: none; -webkit-user-select: none; }
.sheet.body-toggle:not(.open) { cursor: grab; }
.sheet.dragging { cursor: grabbing; }
/* header 슬롯이 없으면 손잡이만 */
.sheet-header.bare { padding-bottom: 10px; }
.sheet-header.bare .handle { margin-bottom: 0; }
.sheet-header:focus-visible { box-shadow: inset 0 0 0 3px var(--mint); }
.handle { display: block; width: 40px; height: 5px; margin: 0 auto 12px; border-radius: 3px; background: #d6e2dc; }

.sheet-body {
  flex: 1 1 auto; min-height: 0; overflow-y: auto;   /* 내용만큼 크고, 시트가 최대 높이에 닿으면 줄어들며 스크롤 */
  overscroll-behavior: contain; touch-action: pan-y; -webkit-overflow-scrolling: touch;
  padding: 0 20px calc(28px + env(safe-area-inset-bottom));
}
</style>
