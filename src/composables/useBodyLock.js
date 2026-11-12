import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, toValue, watch } from 'vue'

// 페이지(html/body) 자체의 스크롤·핀치 줌·당김 바운스를 막는다.
//
// body 를 직접 고칠 수 없는 환경을 위해 JS 로 넣되, body 의 인라인 스타일은 건드리지 않는다.
// 대신 <head> 에 <style> 을 하나 넣고 <html> 에 data-body-lock 속성을 붙였다 뗀다.
// - 인라인 스타일로 넣으면, 잠긴 동안 열린 팝업(모달 라이브러리 등)이 body.style 을 저장해 두었다가
//   닫힐 때 그 값을 되돌리면서 잠금 CSS 를 다시 써 넣는다. 이미 풀었는데도 CSS 가 남는 원인이었다.
// - 속성 하나만 떼면 되니, 누가 body 스타일을 바꿔 두었든 상관없이 깨끗하게 풀린다.
const ATTR = 'data-body-lock'
const STYLE_ID = 'body-lock-style'
const TOP_VAR = '--body-lock-top'
const CSS = `
html[${ATTR}] { overflow: hidden !important; overscroll-behavior: none !important; }
html[${ATTR}] body {
  position: fixed !important; inset: 0 !important; top: var(${TOP_VAR}, 0) !important; width: 100% !important;
  overflow: hidden !important; touch-action: none !important; overscroll-behavior: none !important;
}`

// 지금 잠금을 걸고 있는 쪽들. 여러 곳에서 동시에 걸어도 한 번만 잠그고, 마지막 하나가 풀 때 푼다.
// 숫자 대신 Set 이라 같은 쪽이 두 번 걸거나 두 번 풀어도 개수가 어긋나지 않는다.
const owners = new Set()
let savedScrollY = 0

function acquire(owner) {
  if (owners.has(owner)) return
  owners.add(owner)
  if (owners.size > 1) return
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style')
    style.id = STYLE_ID
    style.textContent = CSS
    document.head.appendChild(style)
  }
  const html = document.documentElement
  savedScrollY = window.scrollY
  // 스크롤된 상태에서 잠그면 그 위치가 그대로 보이도록 body 를 위로 올려 둔다
  html.style.setProperty(TOP_VAR, `-${savedScrollY}px`)
  html.setAttribute(ATTR, '')
}

function release(owner) {
  if (!owners.delete(owner) || owners.size > 0) return
  const html = document.documentElement
  html.removeAttribute(ATTR)
  html.style.removeProperty(TOP_VAR)
  document.getElementById(STYLE_ID)?.remove()
  window.scrollTo(0, savedScrollY)   // 잠그기 전 스크롤 위치로 복귀
}

// 컴포넌트가 화면에 있는 동안 페이지를 잠근다.
// - 언마운트뿐 아니라 <KeepAlive> 로 숨겨질 때(onDeactivated)도 푼다.
//   페이지 이동 시 컴포넌트가 캐시되면 onBeforeUnmount 는 실제로 사라질 때까지 불리지 않는다.
// - active 로 조건을 줄 수 있다. 예) useBodyLock(() => !popupOpen.value)  팝업이 열려 있는 동안은 풀기
// - 돌려주는 lock() / unlock() 으로 직접 풀고 걸 수도 있다. 예) 페이지 이동이나 팝업 열기 직전에 unlock()
export function useBodyLock(active = true) {
  const owner = {}
  const manual = ref(true)
  let mounted = false
  let deactivated = false

  const sync = () => (mounted && !deactivated && manual.value && toValue(active) ? acquire(owner) : release(owner))

  onMounted(() => { mounted = true; sync() })
  onActivated(() => { deactivated = false; sync() })
  onDeactivated(() => { deactivated = true; sync() })
  onBeforeUnmount(() => { mounted = false; sync() })
  watch([manual, () => toValue(active)], sync)

  return {
    lock: () => { manual.value = true; sync() },
    unlock: () => { manual.value = false; sync() },
  }
}
