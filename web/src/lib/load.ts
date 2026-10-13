import { SCREEN_BUCKET, SCREEN_PATH, supabase } from './supabase'
import type { Screen } from './types'

async function gunzipJson(blob: Blob): Promise<Screen> {
  const bytes = new Uint8Array(await blob.arrayBuffer())
  // 저장소가 압축을 이미 풀어 줬으면 바로 읽는다
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return JSON.parse(new TextDecoder().decode(bytes))
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
  return JSON.parse(await new Response(stream).text())
}

/** 오늘의 화면용 파일. 개발 중에는 로컬 파일, 배포에서는 Supabase 비공개 저장소(로그인 필요). */
export async function loadScreen(): Promise<Screen> {
  if (supabase) {
    const { data, error } = await supabase.storage.from(SCREEN_BUCKET).download(SCREEN_PATH)
    if (error || !data) throw error ?? new Error('no data')
    return gunzipJson(data)
  }
  if (import.meta.env.DEV) {
    const res = await fetch('/__dev/screen.json.gz')
    if (!res.ok) throw new Error(`dev screen file: ${res.status}`)
    return gunzipJson(await res.blob())
  }
  throw new Error('Supabase가 설정되지 않았어요')
}
