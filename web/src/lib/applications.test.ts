import { describe, expect, it } from 'vitest'
import { upcoming, type Application } from './applications'

function app(id: string, stage: Application['stage'], deadline: string | null, nextOn: string | null = null): Application {
  return {
    postingId: id, stage, outcome: null, memo: '', nextOn, nextLabel: nextOn ? '1차 면접' : '', dates: {},
    snapshot: { company: `회사${id}`, title: '데이터 엔지니어', url: null, deadlineType: deadline ? 'date' : 'always', deadline },
  }
}

describe('upcoming', () => {
  it('관심 공고의 2주 안 마감과 내가 적은 다음 일정을 날짜 순으로 모은다', () => {
    const list = upcoming([
      app('1', 'interest', '2026-10-25'),
      app('2', 'interest', '2026-11-30'), // 2주 밖
      app('3', 'applied', '2026-10-22', '2026-10-28'), // 지원한 공고의 마감은 빼고 면접 일정만
      app('4', 'interest', '2026-10-20'), // 이미 지남
      app('5', 'dismissed', null, '2026-10-23'), // 관심 없음은 빼기
    ], '2026-10-21')
    expect(list.map((u) => [u.date, u.postingId, u.what])).toEqual([
      ['2026-10-25', '1', 'deadline'],
      ['2026-10-28', '3', 'next'],
    ])
  })
})
