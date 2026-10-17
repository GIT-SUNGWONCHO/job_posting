// 카톡 안 브라우저에서는 구글 로그인이 막힌다(구글이 앱 내장 브라우저 로그인을 거부).
// 아침 카톡 링크로 들어오면 휴대폰 기본 브라우저로 다시 연다. 기본 브라우저에 한 번 로그인해 두면 계속 쓴다.
export function openOutsideKakao(): boolean {
  if (!/KAKAOTALK/i.test(navigator.userAgent)) return false
  window.location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(window.location.href)
  return true
}
