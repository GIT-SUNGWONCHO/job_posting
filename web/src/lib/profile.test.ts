import { expect, it } from 'vitest'
import { careerYears } from './profile'

it('careerYears rounds years from the start month', () => {
  const today = new Date(2026, 9, 13) // 2026.10
  expect(careerYears('2016-12', today)).toBe(10)
  expect(careerYears('2021-06', today)).toBe(5)
  expect(careerYears('2016-10', today)).toBe(10)
  expect(careerYears('2027-01', today)).toBeNull()
  expect(careerYears('', today)).toBeNull()
})
