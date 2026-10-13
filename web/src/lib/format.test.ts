import { describe, expect, it } from 'vitest'
import { dateText, deadlineText, isUrgent } from './format'

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
