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

/** 회사 · 그룹 계열 */
export function companyLine(c: Company | undefined, fallback: string): string {
  const name = c?.name ?? fallback
  return c?.group ? `${name} · ${c.group} 계열` : name
}
