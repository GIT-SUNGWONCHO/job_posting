// 이 기기에서만 기억하는 값. 필터는 관리 화면이 생기면 사람별 설정(Supabase)으로 옮긴다.
export function readLocal<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: unknown) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 저장이 막힌 브라우저(사생활 보호 모드 등)에서는 이번 방문 동안만 유지한다
  }
}
