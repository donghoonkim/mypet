<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import BottomSheet from './BottomSheet.vue'
import { useBodyLock } from '../composables/useBodyLock'

// 펫 키우기 하단 시트 (샘플 데이터). 실제 서비스에서는 API 응답으로 바꾸면 된다.
// BottomSheet 의 옵션(peek, height, maxWidth, topGap, bodyToggle)은 이 컴포넌트에 그대로 주면 전달된다.
// 예: <PetMissionSheet :peek="160" :body-toggle="false" />
const props = defineProps({
  playCount: { type: Number, default: 0 },   // 사용자가 펫과 놀아준 횟수 (PetStage 의 react 이벤트)
})

// 이 시트가 화면에 있는 동안 페이지 자체의 스크롤·핀치 줌·바운스를 막는다 (body 에 인라인 스타일, 언마운트 시 복원)
useBodyLock()

const open = ref(false)
const LEVEL_EXP = 300
const level = ref(3)
const exp = ref(180)
const expPercent = computed(() => Math.round((exp.value / LEVEL_EXP) * 100))

const missions = ref([
  { id: 'attend', icon: '📅', title: '출석 체크하기', desc: '하루 한 번 몽이에게 인사해요', exp: 10, goal: 1, claimed: false },
  { id: 'play', icon: '🎾', title: '몽이랑 3번 놀아주기', desc: '인사·놀기·웃기 무엇이든 좋아요', exp: 30, goal: 3, claimed: false },
  { id: 'pay', icon: '💳', title: '1,000원 이상 결제하기', desc: '결제할 때마다 사료를 받아요', exp: 50, goal: 1, claimed: false, link: true },
  { id: 'invite', icon: '💌', title: '친구 초대하기', desc: '친구가 함께하면 둘 다 보상을 받아요', exp: 100, goal: 1, claimed: false, link: true },
])
const snacks = ref([
  { id: 'feed', icon: '🍖', name: '사료', count: 3, exp: 5 },
  { id: 'cookie', icon: '🍪', name: '쿠키', count: 1, exp: 8 },
  { id: 'milk', icon: '🥛', name: '우유', count: 2, exp: 5 },
  { id: 'apple', icon: '🍎', name: '사과', count: 0, exp: 10 },
])
const NOTICES = [
  '이벤트 기간: 2026.11.01 ~ 2026.12.31 (샘플)',
  '미션 보상은 하루에 한 번만 받을 수 있어요.',
  '간식은 미션과 결제로 모을 수 있고, 먹이면 경험치가 올라요.',
  '레벨이 오르면 몽이의 모습과 보상이 달라져요.',
  '부정한 방법으로 참여하면 보상이 회수될 수 있어요.',
]

const progressOf = (m) => (m.id === 'play' ? Math.min(props.playCount, m.goal) : m.id === 'attend' ? 1 : 0)
const remaining = computed(() => missions.value.filter((m) => !m.claimed).length)

function statusOf(m) {
  if (m.claimed) return { label: '완료', kind: 'done' }
  if (m.link) return { label: '하러가기', kind: 'link' }
  const p = progressOf(m)
  return p >= m.goal ? { label: '받기', kind: 'claim' } : { label: `${p}/${m.goal}`, kind: 'wait' }
}

function addExp(n) {
  exp.value += n
  while (exp.value >= LEVEL_EXP) {
    exp.value -= LEVEL_EXP
    level.value += 1
    say(`레벨 업! 몽이가 Lv.${level.value}이 되었어요 🎉`)
  }
}

function onMission(m) {
  const s = statusOf(m)
  if (s.kind === 'claim') {
    m.claimed = true
    addExp(m.exp)
    say(`+${m.exp} EXP 받았어요!`)
  } else if (s.kind === 'link') {
    say('샘플 화면이라 이동하지 않아요')
  }
}

function feed(s) {
  if (!s.count) return say(`${s.name}가 없어요. 미션으로 모아보세요!`)
  s.count -= 1
  addExp(s.exp)
  say(`몽이가 ${s.name}를 맛있게 먹었어요! +${s.exp} EXP`)
}

const toast = ref('')
let toastTimer = 0
function say(text) {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 1800)
}
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>

<template>
  <BottomSheet v-model:open="open" label="몽이 미션">
    <template #header>
      <div class="peek">
        <div class="avatar" aria-hidden="true">🐻</div>
        <div class="peek-main">
          <div class="peek-title"><strong>몽이</strong><span class="lv">Lv.{{ level }}</span></div>
          <div class="exp" role="progressbar" :aria-valuenow="exp" aria-valuemin="0" :aria-valuemax="LEVEL_EXP">
            <span :style="{ width: expPercent + '%' }"></span>
          </div>
          <div class="peek-sub">다음 레벨까지 {{ LEVEL_EXP - exp }} EXP</div>
        </div>
        <span class="count" :class="{ zero: !remaining }">{{ remaining ? `미션 ${remaining}` : '미션 완료' }}</span>
      </div>
    </template>

    <section class="block">
      <h2>오늘의 미션</h2>
      <ul class="missions">
        <li v-for="m in missions" :key="m.id" :class="{ claimed: m.claimed }">
          <span class="m-icon" aria-hidden="true">{{ m.icon }}</span>
          <div class="m-text">
            <strong>{{ m.title }}</strong>
            <span>{{ m.desc }}</span>
          </div>
          <button type="button" class="m-btn" :class="statusOf(m).kind" :disabled="statusOf(m).kind === 'wait' || m.claimed" @click="onMission(m)">
            <small>+{{ m.exp }} EXP</small>{{ statusOf(m).label }}
          </button>
        </li>
      </ul>
    </section>

    <section class="block">
      <h2>간식 보관함 <small>눌러서 먹이기</small></h2>
      <div class="snacks">
        <button v-for="s in snacks" :key="s.id" type="button" class="snack" :class="{ empty: !s.count }" @click="feed(s)">
          <span class="s-icon" aria-hidden="true">{{ s.icon }}</span>
          <span class="s-name">{{ s.name }}</span>
          <span class="s-count">{{ s.count }}개</span>
        </button>
      </div>
    </section>

    <section class="block notice">
      <h2>이벤트 유의사항</h2>
      <ul>
        <li v-for="n in NOTICES" :key="n">{{ n }}</li>
      </ul>
    </section>

    <div class="toast" :class="{ show: toast }" role="status" aria-live="polite">{{ toast }}</div>
  </BottomSheet>
</template>

<style scoped>
/* ── 접힌 상태에서 보이는 요약 ── */
.peek { display: flex; align-items: center; gap: 12px; }
.avatar {
  flex: none; width: 46px; height: 46px; border-radius: 50%;
  display: grid; place-items: center; font-size: 26px; background: #fff3dc;
}
.peek-main { flex: 1; min-width: 0; }
.peek-title { display: flex; align-items: baseline; gap: 6px; font-size: 15px; }
.lv { font-size: 12px; font-weight: 800; color: var(--mint-deep); }
.exp { height: 8px; margin: 6px 0 4px; border-radius: 4px; background: #e8f3ed; overflow: hidden; }
.exp span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #5ee0a0, var(--mint)); transition: width .5s cubic-bezier(.2, .8, .2, 1); }
.peek-sub { font-size: 12px; color: var(--ink-soft); }
.count {
  flex: none; padding: 6px 10px; border-radius: 999px;
  background: var(--mint); color: #fff; font-size: 12px; font-weight: 800;
}
.count.zero { background: #e8f3ed; color: var(--mint-deep); }

/* ── 본문 ── */
.block { padding-top: 18px; }
.block h2 { margin: 0 0 10px; font-size: 16px; letter-spacing: -.01em; }
.block h2 small { margin-left: 6px; font-size: 12px; font-weight: 600; color: var(--ink-soft); }

.missions { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.missions li {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; border-radius: 16px; background: #f6faf8;
}
.missions li.claimed { opacity: .55; }
.m-icon { flex: none; width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-size: 22px; background: #fff; }
.m-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.m-text strong { font-size: 14px; }
.m-text span { font-size: 12px; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.m-btn {
  flex: none; min-width: 72px; padding: 6px 10px; border: 0; border-radius: 12px; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  font: inherit; font-size: 13px; font-weight: 800; color: #fff; background: var(--ink);
  -webkit-tap-highlight-color: transparent;
}
.m-btn small { font-size: 10px; font-weight: 700; opacity: .75; }
.m-btn.claim { background: var(--mint); }
.m-btn.link { background: #fff; color: var(--ink); box-shadow: inset 0 0 0 1px #d6e2dc; }
.m-btn.wait, .m-btn.done { background: #e8f3ed; color: var(--ink-soft); cursor: default; }
.m-btn:focus-visible, .snack:focus-visible { outline: 3px solid var(--mint); outline-offset: 2px; }

.snacks { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.snack {
  border: 0; cursor: pointer; font: inherit; color: var(--ink);
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 12px 4px 10px; border-radius: 16px; background: #fff8ea;
  -webkit-tap-highlight-color: transparent; transition: transform .12s;
}
.snack:active { transform: scale(.95); }
.snack.empty { opacity: .45; }
.s-icon { font-size: 26px; line-height: 1.2; }
.s-name { font-size: 13px; font-weight: 700; }
.s-count { font-size: 11px; color: var(--ink-soft); }

.notice ul { margin: 0; padding-left: 18px; display: grid; gap: 6px; font-size: 12px; line-height: 1.5; color: var(--ink-soft); }

.toast {
  position: sticky; bottom: 8px; z-index: 1; width: fit-content; max-width: 100%;
  margin: 16px auto 0; padding: 10px 16px; border-radius: 999px;
  background: rgba(29, 43, 36, .9); color: #fff; font-size: 13px; font-weight: 700;
  opacity: 0; transform: translateY(8px); pointer-events: none;
  transition: opacity .2s, transform .2s;
}
.toast.show { opacity: 1; transform: none; }
</style>
