import { onBeforeUnmount, onMounted } from 'vue'

// 페이지(html/body) 자체의 스크롤·핀치 줌·당김 바운스를 막는다.
// body 가 있는 레이아웃을 직접 고칠 수 없는 환경을 위해, 컴포넌트가 마운트될 때 인라인 스타일로 넣고
// 언마운트될 때 원래 값으로 되돌린다. (다른 화면으로 이동해도 페이지가 잠긴 채 남지 않게)
const HTML_STYLE = { overflow: 'hidden', overscrollBehavior: 'none' }
const BODY_STYLE = { position: 'fixed', inset: '0', overflow: 'hidden', touchAction: 'none', overscrollBehavior: 'none' }

let lockCount = 0   // 여러 컴포넌트가 동시에 써도 한 번만 잠그고, 마지막 하나가 풀릴 때 되돌린다
let saved = null

// 우리가 바꾸는 속성의 기존 인라인 값만 저장해 두고 덮어쓴다.
// inset 처럼 top 등을 함께 바꾸는 단축 속성이 있으니, 값을 바꾸기 전에 전부 먼저 저장한다.
function apply(el, styles) {
  const prev = {}
  for (const key of Object.keys(styles)) prev[key] = el.style[key]
  for (const [key, value] of Object.entries(styles)) el.style[key] = value
  return prev
}

function lock() {
  if (lockCount++ > 0) return
  const { documentElement: html, body } = document
  const scrollY = window.scrollY
  // 스크롤된 상태에서 잠그면 그 위치가 그대로 보이도록 body 를 위로 올려 둔다
  const bodyStyle = scrollY ? { ...BODY_STYLE, top: `-${scrollY}px` } : BODY_STYLE
  saved = { scrollY, html: apply(html, HTML_STYLE), body: apply(body, bodyStyle) }
}

function unlock() {
  if (--lockCount > 0 || !saved) return
  const { documentElement: html, body } = document
  apply(html, saved.html)
  apply(body, saved.body)
  window.scrollTo(0, saved.scrollY)   // 잠그기 전 스크롤 위치로 복귀
  saved = null
}

export function useBodyLock() {
  onMounted(lock)
  onBeforeUnmount(unlock)
}
