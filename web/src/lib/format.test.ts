import { describe, expect, it } from 'vitest'
import { addDays, dateText, deadlineText, isUrgent } from './format'

describe('deadlineText', () => {
  const today = '2026-10-13'
  it('follows the glossary format', () => {
    expect(deadlineText({ deadlineType: 'date', deadline: '2026-10-25' }, today)).toBe('D-12')
    expect(deadlineText({ deadlineType: 'date', deadline: '2026-10-13' }, today)).toBe('D-day')
    expect(deadlineText({ deadlineType: 'date', deadline: '2026-10-12' }, today)).toBe('마감')
    expect(deadlineText({ deadlineType: 'always', deadline: null }, today)).toBe('상시')
    expect(deadlineText({ deadlineType: 'until_filled', deadline: null }, today)).toBe('상시')
  })
  it('marks D-day to D-3 as urgent', () => {
    expect(isUrgent({ deadlineType: 'date', deadline: '2026-10-16' }, today)).toBe(true)
    expect(isUrgent({ deadlineType: 'date', deadline: '2026-10-17' }, today)).toBe(false)
    expect(isUrgent({ deadlineType: 'date', deadline: '2026-10-12' }, today)).toBe(false)
  })
})

it('dateText', () => {
  expect(dateText('2026-10-03')).toBe('10.03')
  expect(dateText('2026-10-03', true)).toBe('2026.10.03')
})

describe('금액·증감 표기(용어집 "표기 형식")', () => {
  it('금액은 반올림한 뒤 단위를 고른다', async () => {
    const { money } = await import('./format')
    expect(money(186254472000000)).toBe('186.3조')
    expect(money(999_970_000_000)).toBe('1.0조')
    expect(money(48_924_000_000)).toBe('489억')
    expect(money(-815_400_000_000)).toBe('-8,154억')
    expect(money(130_858_949)).toBe('1.3억')
    expect(money(999_950_000)).toBe('10억')
    expect(money(99_999_000)).toBe('1.0억')
    expect(money(98_000_000)).toBe('9,800만 원')
  })

  it('증감은 반올림한 뒤 화살표, 부호가 바뀌면 흑자·적자 전환', async () => {
    const { growth, pointChange } = await import('./format')
    expect(growth(110, 100)).toBe('▲10.0%')
    expect(growth(90, 100)).toBe('▼10.0%')
    expect(growth(100.04, 100)).toBe('0.0%')
    expect(growth(-50, 100)).toBe('적자 전환')
    expect(growth(50, -100)).toBe('흑자 전환')
    expect(growth(-50, -100)).toBe('적자 지속')
    expect(growth(50, 0)).toBeNull()
    expect(growth(50, null)).toBeNull()
    expect(pointChange(6.2, 8.2)).toBe('▼2.0%p')
    expect(pointChange(6.21, 6.24)).toBe('0.0%p')
  })

  it('연.월', async () => {
    const { yearMonth } = await import('./format')
    expect(yearMonth('20260318001394')).toBe('2026.03')
    expect(yearMonth('2026-08-01')).toBe('2026.08')
    expect(yearMonth(null)).toBeNull()
  })
})

describe('addDays', () => {
  it('moves across month ends', () => {
    expect(addDays('2026-10-26', -6)).toBe('2026-10-20')
    expect(addDays('2026-11-01', -1)).toBe('2026-10-31')
  })
})
