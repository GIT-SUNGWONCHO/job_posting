import { SCREEN_BUCKET, SCREEN_PATH, supabase } from './supabase'
import type { Body, CompaniesFile, Screen } from './types'

async function gunzipJson<T = Screen>(blob: Blob): Promise<T> {
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

async function fetchFile<T>(path: string): Promise<T> {
  let blob: Blob
  if (supabase) {
    const { data, error } = await supabase.storage.from(SCREEN_BUCKET).download(path)
    if (error || !data) throw error ?? new Error('no data')
    blob = data
  } else {
    const res = await fetch(`/__dev/${path}`)
    if (!res.ok) throw new Error(`dev file ${path}: ${res.status}`)
    blob = await res.blob()
  }
  return gunzipJson<T>(blob)
}

let companies: Promise<CompaniesFile> | null = null

/** 회사 기본정보(DART, 지난 공고). 회사 화면을 처음 열 때 한 번 받는다. 예전 배포에는 파일이 없을 수 있다 */
export function loadCompanies(): Promise<CompaniesFile> {
  if (!companies) {
    companies = fetchFile<CompaniesFile>('companies.json.gz')
    companies.catch(() => {
      companies = null
    })
  }
  return companies
}

/** 본문 묶음 번호. src/jobpost/screen.py body_shard와 같은 FNV-1a 32비트(UTF-8), 16묶음. */
export function bodyShard(id: string): string {
  let h = 0x811c9dc5
  for (const b of new TextEncoder().encode(id)) {
    h ^= b
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return (h % 16).toString(16).padStart(2, '0')
}

const shards = new Map<string, Promise<Record<string, Body>>>()

async function fetchShard(shard: string): Promise<Record<string, Body>> {
  return (await fetchFile<{ bodies: Record<string, Body> }>(`bodies/${shard}.json.gz`)).bodies
}

/** 공고 본문. 같은 묶음은 한 번만 받는다. */
export async function loadBody(id: string): Promise<Body | null> {
  const shard = bodyShard(id)
  let p = shards.get(shard)
  if (!p) {
    p = fetchShard(shard)
    shards.set(shard, p)
    p.catch(() => shards.delete(shard))
  }
  return (await p)[id] ?? null
}
