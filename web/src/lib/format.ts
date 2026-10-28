// 표기 형식은 docs/glossary.md "표기 형식"을 따른다.
import type { Company, Posting } from './types'

const DAY = 24 * 60 * 60 * 1000

/** 브라우저 기준 오늘(YYYY-MM-DD). */
export function todayISO(now = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** 목록 제목: 회사 이름·'채용' 같은 말을 뺀 제목(screen.py가 만든다). 없으면 원문 제목. 공고 상세는 원문 제목 */
export function listTitle(p: { title: string; listTitle?: string }): string {
  return p.listTitle || p.title
}

/** 마감까지 남은 날. 마감일이 없으면 null. */
export function daysLeft(p: Pick<Posting, 'deadlineType' | 'deadline'>, today: string): number | null {
  if (p.deadlineType !== 'date' || !p.deadline) return null
  return Math.round((Date.parse(p.deadline) - Date.parse(today)) / DAY)
}

/** D-12, D-day, 상시, 마감 */
export function deadlineText(p: Pick<Posting, 'deadlineType' | 'deadline'>, today: string): string {
  const n = daysLeft(p, today)
  if (n === null) return '상시'
  if (n < 0) return '마감'
  if (n === 0) return 'D-day'
  return `D-${n}`
}

/** n일 뒤(앞이면 음수)의 YYYY-MM-DD */
export function addDays(iso: string, n: number): string {
  return new Date(Date.parse(iso) + n * DAY).toISOString().slice(0, 10)
}

/** 마감 3일 이내(D-day~D-3)면 빨강으로 표시한다. */
export function isUrgent(p: Pick<Posting, 'deadlineType' | 'deadline'>, today: string): boolean {
  const n = daysLeft(p, today)
  return n !== null && n >= 0 && n <= 3
}

/** 10.13 / 2026.10.13 */
export function dateText(iso: string, withYear = false): string {
  const [y, m, d] = iso.split('-')
  return withYear ? `${y}.${m}.${d}` : `${Number(m)}.${d}`
}

/** 목록 줄의 회사: 회사 · 그룹(그룹 이름이 회사 이름과 같으면 회사만) */
export function companyLine(c: Company | undefined, fallback: string): string {
  const name = c?.name ?? fallback
  return c?.group && c.group !== name ? `${name} · ${c.group}` : name
}

/** +3, -2, 0 */
export const signed = (n: number) => (n > 0 ? `+${n.toLocaleString()}` : n.toLocaleString())

/** 2026-10 */
export const monthOf = (iso: string) => iso.slice(0, 7)

/** 금액(원): 1조 이상은 12.3조, 10억 이상은 1,234억, 1억 이상은 3.2억, 그 아래는 1,234만 원(반올림한 뒤 단위를 고른다) */
export function money(won: number): string {
  const sign = won < 0 ? '-' : ''
  const v = Math.abs(won)
  const jo = Math.round(v / 1e11) / 10
  if (jo >= 1) return `${sign}${jo.toFixed(1)}조`
  const eok = v / 1e8
  if (Math.round(eok * 10) / 10 >= 10) return `${sign}${Math.round(eok).toLocaleString()}억`
  if (eok >= 1 || Math.round(v / 1e4) >= 10000) return `${sign}${(Math.round(eok * 10) / 10).toFixed(1)}억`
  return `${sign}${Math.round(v / 1e4).toLocaleString()}만 원`
}

/** 전년 대비 증감: ▲12.3%, ▼4.0%, 0.0%. 부호가 바뀌면 흑자 전환 · 적자 전환, 둘 다 손실이면 적자 지속.
 * 비교할 값이 없거나 전년이 0이면 null */
export function growth(cur: number | null | undefined, prev: number | null | undefined): string | null {
  if (cur === null || cur === undefined || prev === null || prev === undefined || prev === 0) return null
  if (prev > 0 && cur < 0) return '적자 전환'
  if (prev < 0 && cur > 0) return '흑자 전환'
  if (prev < 0 && cur <= 0) return '적자 지속'
  const pct = Math.round(((cur - prev) / prev) * 1000) / 10
  if (pct === 0) return '0.0%'
  return `${pct > 0 ? '▲' : '▼'}${Math.abs(pct).toFixed(1)}%`
}

/** 비율의 증감: ▲1.2%p, 0.0%p(반올림한 뒤 화살표를 고른다) */
export function pointChange(cur: number | null, prev: number | null): string | null {
  if (cur === null || prev === null) return null
  const d = Math.round((cur - prev) * 10) / 10
  if (d === 0) return '0.0%p'
  return `${d > 0 ? '▲' : '▼'}${Math.abs(d).toFixed(1)}%p`
}

/** 2026.03(접수번호 앞 8자리 YYYYMMDD나 YYYY-MM-DD에서) */
export function yearMonth(s: string | null | undefined): string | null {
  const m = /^(\d{4})-?(\d{2})/.exec(s ?? '')
  return m ? `${m[1]}.${m[2]}` : null
}

/** DART 공시 보기 주소 */
export const dartUrl = (rceptNo: string) => `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${rceptNo}`
