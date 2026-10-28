import { describe, expect, it } from 'vitest'
import {
  bins, bucketOf, currentOf, gaps, mySlice, niceTicks, otherDirections, periodStats, periods, positions, skillFit, strengths, sumSeries,
  weekBins, weekLabel,
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

  it('막대: 짧으면 하루, 60일이 넘으면 7일씩 끝에서부터 묶고 7일이 안 되는 맨 앞은 뺀다', () => {
    expect(bins(m.days, [null, 1, 2, 3, 4, 5, 6, 7, 8], 0)).toMatchObject({ size: 1 })
    expect(bins(m.days, [null, 1, 2, 3, 4, 5, 6, 7, 8], 0).bins).toHaveLength(9)
    const d = Array.from({ length: 71 }, (_, i) => new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10))
    const v = d.map((_, i) => (i === 0 ? null : 1))
    const { bins: b, size } = bins(d, v, 0)
    expect(size).toBe(7)
    expect(b).toHaveLength(10) // 71일 = 7일 × 10 + 맨 앞 하루(뺌)
    expect(b[b.length - 1]).toMatchObject({ end: d[70], value: 7 })
    expect(b[0]).toMatchObject({ start: d[1], value: 7 })
  })

  it('묶음이 없는 직무도 0건(세지 않음은 첫날만), 눈금 간격은 1 이상', () => {
    const s = sumSeries(m, { jobs: ['dba'], ctypes: null })
    expect(s.new).toEqual([null, 0, 0, 0, 0, 0, 0, 0, 0])
    expect(niceTicks(1, 3)).toEqual([0, 1])
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

  it('스킬 적합도: 요구한 공고 수로 가중, 기초는 절반', () => {
    const skills: [string, number][] = [['SQL', 8], ['Spark', 6], ['Kafka', 4], ['Go', 2]]
    expect(skillFit(skills, new Map([['SQL', 3], ['Spark', 1]]))).toBe(55) // (8 + 3) / 20
    expect(skillFit([], new Map())).toBeNull()
    expect(strengths(skills, new Map([['SQL', 3], ['Spark', 1]]), 3)).toEqual(['SQL'])
    expect(gaps(skills, new Map([['SQL', 3], ['Spark', 1]]), 2)).toEqual([
      { name: 'Spark', count: 6, level: 1 }, { name: 'Kafka', count: 4, level: 0 },
    ])
  })

  it('직무 지도: 커리어 방향이 아닌 직무는 빼고 네 칸으로 나눈다', () => {
    const mine = new Map([['SQL', 3], ['Spark', 3]])
    const { list, demandLine } = positions(m, jobTypes, ['대기업'], mine, new Map([['data_eng', 4]]), new Map())
    expect(list.map((p) => p.id)).toEqual(['data_eng', 'ml_eng'])
    expect(demandLine).toBe(25)
    const de = list.find((p) => p.id === 'data_eng')!
    expect(de).toMatchObject({ open: 16, change: 5, fit: 78, years: 4, quadrant: 'keep' })
    expect(list.find((p) => p.id === 'ml_eng')!.quadrant).toBe('grow')
    expect(otherDirections(list, ['data_eng'], 3).map((p) => p.id)).toEqual(['ml_eng'])
  })

  it('포지션 맵: 적합도가 없는 직무는 기준선과 네 칸에서 뺀다', () => {
    const noSkills: CareerMetrics = { ...m, series: { ...m.series, 'dba|대기업': { open: new Array(9).fill(100), new: new Array(9).fill(0) } } }
    const types: JobType[] = [...jobTypes, { id: 'dba', name: 'DBA' }]
    const { list, demandLine } = positions(noSkills, types, ['대기업'], new Map([['SQL', 3]]), new Map(), new Map())
    expect(demandLine).toBe(25) // DBA(100건, 적합도 없음)는 가운데 값에 넣지 않는다
    expect(list.find((p) => p.id === 'dba')).toMatchObject({ fit: null, quadrant: null })
  })
})

describe('mySlice', () => {
  const types = [
    { id: 'data_eng', name: '데이터 엔지니어', short: '데이터 엔지니어' },
    { id: 'ai_eng', name: 'AI 엔지니어', short: 'AI 엔지니어' },
    { id: 'labeling', name: '라벨링', short: '라벨링', direction: false },
  ] as JobType[]
  it('keeps my career-direction job types and company types', () => {
    expect(mySlice(types, { job_types: ['data_eng', 'labeling'], company_types: ['대기업'] }))
      .toEqual({ jobs: ['data_eng'], ctypes: ['대기업'] })
  })
  it('falls back to every direction job type and every company type', () => {
    expect(mySlice(types, { job_types: [], company_types: [] })).toEqual({ jobs: ['data_eng', 'ai_eng'], ctypes: null })
  })
})

describe('weekBins', () => {
  it('월요일부터 일요일까지 묶고 이번 주는 며칠째인지 센다', () => {
    const days = ['2026-10-13', '2026-10-14', '2026-10-19', '2026-10-20', '2026-10-27', '2026-10-28']
    const out = weekBins(days, [100, 5, 7, 3, 4, null], 1)
    expect(out.map((b) => [b.start, b.value, b.days])).toEqual([['2026-10-12', 5, 1], ['2026-10-19', 10, 2], ['2026-10-26', 4, 2]])
    expect(weekLabel('2026-10-12')).toBe('10월 2주')
  })
})
