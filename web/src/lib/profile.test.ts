import { describe, expect, it } from 'vitest'
import { careerTotals, durationText, emptyProfile, months, periodText, roleYears, upgrade, type Profile } from './profile'

const today = new Date(2026, 9, 14) // 2026.10
const names = { data_eng: '데이터 엔지니어', analyst: '데이터 분석가', pi: '업무 프로세스 혁신(PI) 기획' }
// tests/test_profile_facts.py의 V2와 같은 프로필, 같은 결과
const v2: Profile = {
  ...emptyProfile,
  careers: [
    { company: '한샘', industry: 'consumer', start: '2016-12', end: '2023-11', title: '', roles: [
      { role: 'pi', start: '2016-12', end: '2018-03', summary: '', projects: [] },
      { role: 'analyst', start: '2018-04', end: '2022-10', summary: '', projects: [] },
      { role: 'data_eng', start: '2022-11', end: '2023-11', summary: '', projects: [] },
    ] },
    { company: '포스코이앤씨', industry: 'construction', start: '2023-11', end: '', title: '', roles: [
      { role: 'other', roleName: 'BI 플랫폼 운영', start: '2023-11', end: '2025-12', summary: '', projects: [] },
    ] },
  ],
}

it('months counts both ends and runs to this month when open', () => {
  expect(months('2026-01', '2026-09', today)).toBe(9)
  expect(months('2026-01', '', today)).toBe(10)
  expect(months('', '2026-01', today)).toBe(0)
})

it('roleYears and careerTotals match the Python side', () => {
  const ys = Object.fromEntries(roleYears(v2, names, today))
  expect(ys['데이터 엔지니어'].toFixed(1)).toBe('1.1')
  expect(ys['데이터 분석가'].toFixed(1)).toBe('4.6')
  expect(ys['BI 플랫폼 운영']).toBeGreaterThan(2)
  const [total, data] = careerTotals(v2, today)
  expect(total.toFixed(1)).toBe('10.0')
  expect(data.toFixed(1)).toBe('8.7')
})

it('upgrade moves a v1 profile into careers with unrated skills', () => {
  const p = upgrade({ jobs: [{ company: 'A', start: '2020-01', end: '', role: '데이터 리드' }],
    projects: [{ title: 'P', result: 'R' }], skills: ['SQL'], targetRoles: ['data_eng'] })
  expect(p.schema).toBe(2)
  expect(p.careers[0].roles[0].roleName).toBe('데이터 리드')
  expect(p.careers[0].roles[0].projects[0].summary).toBe('R')
  expect(p.skills).toEqual([{ name: 'SQL', level: 0 }])
})

describe('periodText', () => {
  it('끝이 없으면 재직 중과 지금까지의 기간', () => {
    expect(periodText('2021-03', '', '재직 중', new Date(2026, 9, 28))).toBe('2021.03 ~ 재직 중 (5년 8개월)')
    expect(periodText('2024-09', '2025-06', '현재')).toBe('2024.09 ~ 2025.06 (10개월)')
    expect(durationText(36)).toBe('3년')
  })
})
