import { expect, it } from 'vitest'
import { passes } from './filter'
import type { Company, Filters, Posting } from './types'

const base: Posting = {
  id: 'zighang:a', company: 'k', title: '데이터 엔지니어', careerMin: 5, careerMax: 10, career: '경력 5~10년',
  deadlineType: 'always', deadline: null, regions: ['서울'], employment: [], headhunter: false, noise: null,
  firstSeen: '2026-10-13', jobType: 'data_eng', hasBody: false, sources: [],
}
const large: Company = { name: '삼성전자', type: '대기업', group: '삼성' }
const f: Filters = {
  exclude_keywords: ['데이터 입력'], company_types: ['대기업'], career: { min: 7, max: 15 }, regions: ['서울', '경기', '원격'],
}

// src/jobpost/filters.py와 같은 결과여야 한다
it('passes like filters.py', () => {
  expect(passes(base, large, f)).toBe(true)
  expect(passes({ ...base, title: '데이터입력 담당' }, large, f)).toBe(false)
  expect(passes(base, { ...large, type: '그 외' }, f)).toBe(false)
  expect(passes({ ...base, careerMin: 1, careerMax: 3 }, large, f)).toBe(false)
  expect(passes({ ...base, careerMin: null, careerMax: null }, large, f)).toBe(true)
  expect(passes({ ...base, regions: ['부산'] }, large, f)).toBe(false)
  expect(passes({ ...base, regions: ['부산'], title: '데이터 엔지니어(재택)' }, large, f)).toBe(true)
  expect(passes(base, { ...large, type: '그 외' }, { ...f, always_companies: ['삼성'] })).toBe(true)
})

it('filters by job type but lets unclassified postings through', () => {
  const g: Filters = { job_types: ['data_eng', 'ai_eng'] }
  expect(passes(base, large, g)).toBe(true)
  expect(passes({ ...base, jobType: 'non_data' }, large, g)).toBe(false)
  expect(passes({ ...base, jobType: null }, large, g)).toBe(true)
})
