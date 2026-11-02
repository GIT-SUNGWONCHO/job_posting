import { expect, it } from 'vitest'
import { bodyLines } from './body'

it('turns short lines under a heading into list items', () => {
  const got = bodyLines('회사 소개 문단입니다\n담당업무\n정보보안 진단 및 정책 수립\n- 서버 가상화·클라우드 구축\n1. 첫째 단계\n\n[자격요건]\n• SQL 숙련')
  expect(got).toEqual([
    { kind: 'p', text: '회사 소개 문단입니다' },
    { kind: 'h', text: '담당업무' },
    { kind: 'li', text: '정보보안 진단 및 정책 수립' },
    { kind: 'li', text: '서버 가상화·클라우드 구축' },
    { kind: 'p', text: '1. 첫째 단계' },
    { kind: 'p', text: '' },
    { kind: 'h', text: '자격요건' },
    { kind: 'li', text: 'SQL 숙련' },
  ])
})
