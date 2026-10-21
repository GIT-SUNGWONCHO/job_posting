import { describe, expect, it } from 'vitest'
import {
  bins, bucketOf, currentOf, gaps, otherDirections, periodStats, periods, positions, skillFit, strengths, sumSeries,
} from './career'
import type { CareerMetrics, JobType } from './types'

const days = (n: number) => Array.from({ length: n }, (_, i) => `2026-10-${String(13 + i).padStart(2, '0')}`)

const m: CareerMetrics = {
  version: 1,
  since: '2026-10-13',
  days: days(9),
  series: {
    'data_eng|대기업': { open: [10, 11, 12, 12, 13, 13, 14, 15, 16], new: [null, 1, 1, 0, 1, 0, 1, 1, 1] },
    'data_eng|그 외': { open: [50, 50, 50, 50, 50, 50, 50, 50, 50], new: [null, 5, 5, 5, 5, 5, 5, 5, 5] },
    'ml_eng|대기업': { open: [30, 30, 31, 31, 32, 32, 33, 33, 34], new: [null, 2, 2, 2, 2, 2, 2, 2, 2] },
  },
  current: {
    'data_eng|대기업': { career: { '3-7': 10, '7-12': 5, any: 1 }, skills: [['SQL', 8], ['Spark', 6], ['Kafka', 4]], withBody: 12 },
    'ml_eng|대기업': { career: { '0-3': 4, '3-7': 30 }, skills: [['Python', 20], ['PyTorch', 15], ['SQL', 2]], withBody: 30 },
  },
}

const jobTypes: JobType[] = [
  { id: 'data_eng', name: '데이터 엔지니어', short: '데이터 엔지니어' },
  { id: 'ml_eng', name: 'ML 엔지니어', short: 'ML 엔지니어' },
  { id: 'non_data', name: '데이터·AI 아닌 직무', direction: false },
]

describe('커리어 지표', () => {
  it('묶음을 직무·기업 구분으로 골라 더한다(첫날 새 공고는 세지 않음)', () => {
    const s = sumSeries(m, { jobs: ['data_eng'], ctypes: ['대기업'] })
    expect(s.open[8]).toBe(16)
    expect(s.new[0]).toBeNull()
    expect(sumSeries(m, { jobs: null, ctypes: ['대기업'] }).open[8]).toBe(50)
    expect(sumSeries(m, { jobs: ['data_eng'], ctypes: null }).new[1]).toBe(6)
  })

  it('기간: 데이터가 있는 기간만 고르고, 앞 기간이 온전할 때만 비교한다', () => {
    expect(periods({ ...m, days: days(7) })).toEqual([])
    expect(periods(m)).toEqual([7])
    const s = sumSeries(m, { jobs: ['ml_eng'], ctypes: null })
    const week = periodStats(s, 7)
    expect(week.newSum).toBe(14)
    expect(week.prevSum).toBeNull()
    const three = periodStats(s, 3)
    expect(three).toMatchObject({ newSum: 6, prevSum: 6, openNow: 34, openFrom: 33 })
    expect(periodStats(s, 0).newSum).toBe(16)
  })

  it('막대: 짧으면 하루, 60일이 넘으면 7일씩 끝에서부터 묶는다', () => {
    expect(bins(m.days, [null, 1, 2, 3, 4, 5, 6, 7, 8], 0)).toHaveLength(9)
    const d = Array.from({ length: 70 }, (_, i) => new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10))
    const v = d.map((_, i) => (i === 0 ? null : 1))
    const b = bins(d, v, 0)
    expect(b).toHaveLength(10)
    expect(b[b.length - 1]).toMatchObject({ end: d[69], value: 7 })
    expect(b[0].value).toBe(6)
  })

  it('지금 열린 공고의 연차와 스킬을 더한다', () => {
    const c = currentOf(m, { jobs: null, ctypes: ['대기업'] })
    expect(c.career).toEqual({ '0-3': 4, '3-7': 40, '7-12': 5, '12+': 0, any: 1 })
    expect(c.total).toBe(50)
    expect(c.skills[0]).toEqual(['Python', 20])
    expect(c.skills.find(([n]) => n === 'SQL')).toEqual(['SQL', 10])
    expect(bucketOf(8.5)).toBe('7-12')
    expect(bucketOf(12)).toBe('12+')
  })

  it('스킬 적합도: 요구한 공고 수로 가중, 써 봄은 절반', () => {
    const skills: [string, number][] = [['SQL', 8], ['Spark', 6], ['Kafka', 4], ['Go', 2]]
    expect(skillFit(skills, new Map([['SQL', 3], ['Spark', 1]]))).toBe(55) // (8 + 3) / 20
    expect(skillFit([], new Map())).toBeNull()
    expect(strengths(skills, new Map([['SQL', 3], ['Spark', 1]]), 3)).toEqual(['SQL'])
    expect(gaps(skills, new Map([['SQL', 3], ['Spark', 1]]), 2)).toEqual([
      { name: 'Spark', count: 6, level: 1 }, { name: 'Kafka', count: 4, level: 0 },
    ])
  })

  it('포지션 맵: 커리어 방향이 아닌 직무는 빼고 네 칸으로 나눈다', () => {
    const mine = new Map([['SQL', 3], ['Spark', 3]])
    const { list, demandLine } = positions(m, jobTypes, ['대기업'], mine, new Map([['data_eng', 4]]), new Map())
    expect(list.map((p) => p.id)).toEqual(['data_eng', 'ml_eng'])
    expect(demandLine).toBe(25)
    const de = list.find((p) => p.id === 'data_eng')!
    expect(de).toMatchObject({ open: 16, change: 5, fit: 78, years: 4, quadrant: 'keep' })
    expect(list.find((p) => p.id === 'ml_eng')!.quadrant).toBe('grow')
    expect(otherDirections(list, ['data_eng'], 3).map((p) => p.id)).toEqual(['ml_eng'])
  })
})
