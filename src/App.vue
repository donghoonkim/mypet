<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import PetStage from './components/PetStage.vue'

// TYPE 1: 위아래 회전 + 줌 가능(백업),  TYPE 2: 좌우 회전만, 줌 없음
const TYPES = [
  { id: 1, label: 'TYPE 1', verticalRotate: true, zoom: true },
  { id: 2, label: 'TYPE 2', verticalRotate: false, zoom: false },
]
const VIEWPORT = 'width=device-width, initial-scale=1, viewport-fit=cover'

const readType = () => (new URLSearchParams(location.search).get('type') === '1' ? 1 : 2)
const type = ref(readType())
const current = computed(() => TYPES.find((t) => t.id === type.value))

function selectType(id) {
  if (id === type.value) return
  type.value = id
  const url = new URL(location.href)
  url.searchParams.set('type', id)
  history.pushState(null, '', url)
}

const onPopState = () => { type.value = readType() }
onMounted(() => window.addEventListener('popstate', onPopState))
onBeforeUnmount(() => window.removeEventListener('popstate', onPopState))

watchEffect(() => {
  const lock = !current.value.zoom
  document.documentElement.classList.toggle('lock-page', lock)
  document.querySelector('meta[name="viewport"]').content = VIEWPORT + (lock ? ', maximum-scale=1, user-scalable=no' : '')
  document.title = `몽이랑 놀기 · Type ${type.value}`
})
</script>

<template>
  <main class="app">
    <nav class="types" aria-label="타입 선택">
      <a
        v-for="t in TYPES"
        :key="t.id"
        :href="`?type=${t.id}`"
        :aria-current="t.id === type ? 'page' : undefined"
        @click.prevent="selectType(t.id)"
      >{{ t.label }}</a>
    </nav>

    <!-- key 로 타입이 바뀔 때마다 3D 씬을 새로 만든다 -->
    <PetStage :key="type" :vertical-rotate="current.verticalRotate" :zoom="current.zoom" />
  </main>
</template>

<style scoped>
.app {
  position: relative;
  width: 100%;
  max-width: 480px;
  height: 100dvh;
  max-height: 920px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, var(--sky-top) 0%, var(--sky-bottom) 62%, #fff 100%);
}
@media (min-width: 520px) and (min-height: 700px) {
  .app { height: calc(100dvh - 48px); border-radius: 36px; box-shadow: var(--shadow); }
}

.types {
  align-self: center; flex: none; position: relative; z-index: 4;
  display: inline-flex; gap: 2px; padding: 3px; border-radius: 999px;
  margin-top: calc(12px + env(safe-area-inset-top));
  background: rgba(255, 255, 255, .72); box-shadow: 0 2px 10px rgba(22, 120, 74, .1);
}
.types a {
  padding: 6px 16px; border-radius: 999px; text-decoration: none;
  font-size: 12px; font-weight: 800; letter-spacing: .04em; color: var(--ink-soft);
  -webkit-tap-highlight-color: transparent;
}
.types a[aria-current="page"] { background: var(--ink); color: #fff; }
.types a:focus-visible { outline: 3px solid var(--mint); outline-offset: 2px; }

@media (max-height: 620px) {
  .types { margin-top: 8px; }
}
</style>
