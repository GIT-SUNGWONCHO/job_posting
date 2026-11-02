// 공고 본문 보여 주기: 줄을 제목 · 목록 · 문단으로 나눈다(공고 상세).
// 직행 요약처럼 여러 직무·요건이 줄마다 이어진 본문도 제목 아래 짧은 줄은 글머리 목록으로 보여 구분되게 한다.

const BULLET = /^\s*[-•·ㆍ*▪◦●○]\s*/
const NUMBERED = /^\s*\d+[.)]\s/

/** 본문 줄을 제목 · 목록 · 문단으로. 제목 아래의 짧은 줄은 글머리 목록으로 보여 직무·요건이 한 덩어리로 붙어 보이지 않게 한다 */
export function bodyLines(text: string): { kind: 'h' | 'li' | 'p'; text: string }[] {
  let inSection = false
  return text.split('\n').map((line) => {
    const s = line.trim()
    if (HEADING.test(s)) {
      inSection = true
      return { kind: 'h', text: s.replace(/^\[|\]$/g, '') }
    }
    if (!s) return { kind: 'p', text: '' }
    if (BULLET.test(s)) return { kind: 'li', text: s.replace(BULLET, '') }
    if (inSection && s.length <= 200 && !NUMBERED.test(s)) return { kind: 'li', text: s }
    return { kind: 'p', text: line }
  })
}

export const HEADING = /^(\p{Extended_Pictographic}\s*)?\[?(소개|포지션 소개|회사 소개|담당\s*업무|주요\s*업무|자격\s*요건|필수\s*요건|우대\s*사항|혜택\s*및\s*복지|복지\s*및\s*혜택|채용\s*절차|전형\s*절차|근무\s*조건|근무\s*환경|기타\s*사항|유의\s*사항|보상|접수\s*방법|마감\s*기한|사내\s*문화)\]?$/u
