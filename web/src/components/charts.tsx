import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { copy } from '../copy'
import { FIT_LINE, niceTicks, type Position } from '../lib/career'

// 커리어 탭 차트. 강조할 값 하나만 파랑(--accent), 나머지는 회색 막대(--chart-off), 축 하나, 값은 글자로도 보인다.
// 범례는 한 줄, 축·범례 이름은 용어집 이름 그대로(docs/content-rules.md, 캔버스 공통 규칙 12)

function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(el.clientWidth)
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

function Tip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  // 가장자리에서 잘리지 않게 가운데를 안쪽으로 당긴다
  const left = Math.min(Math.max(x, 80), Math.max(80, width - 80))
  return <div className="chart-tip" role="status" style={{ left, top: y }}>{children}</div>
}

export interface BarRow {
  key: string
  label: ReactNode
  value: number
  /** 막대 끝에 적는 값 */
  text: string
  /** 강조(내 연차, 내 스킬): 파랑 막대, 이름 굵게 */
  on?: boolean
  /** 강조한 이유를 이름 아래 글자로(색만으로 구분하지 않게): 내 연차, 숙련도 */
  tag?: string
  /** 맨 끝 칸(성장 계획의 내 숙련도). levelOn이면 파랑, 아니면 흐리게 */
  level?: string
  levelOn?: boolean
}

/** 가로 막대 목록. 한 축(같은 단위)만 그린다 */
export function BarList({ rows, max }: { rows: BarRow[]; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  const withLevel = rows.some((r) => r.level)
  return (
    <div className={withLevel ? 'bars with-level' : 'bars'}>
      {rows.map((r) => (
        <div key={r.key} className={r.on ? 'bar-row on' : 'bar-row'}>
          <span className="bar-label">
            <span className="bar-name">{r.label}</span>
            {r.tag && <span className="bar-tag">{r.tag}</span>}
          </span>
          <span className="bar-track"><span className={r.on ? 'bar on' : 'bar'} style={{ width: `${Math.max(r.value ? 1 : 0, (r.value / top) * 100)}%` }} /></span>
          <span className="bar-value">{r.text}</span>
          {withLevel && <span className={r.levelOn ? 'bar-level on' : 'bar-level'}>{r.level}</span>}
        </div>
      ))}
    </div>
  )
}

/** 세로 막대(주마다 · 날마다 새 공고): 강조한 막대만 파랑, 값은 막대 위에(많으면 강조한 것만) */
export function Columns({ data, label }: { data: { key: string; label: string; value: number | null; on?: boolean }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.value ?? 0))
  const many = data.length > 7
  return (
    <div className="columns" role="img" aria-label={`${label}: ${data.map((d) => `${d.label} ${d.value ?? '-'}`).join(', ')}`}>
      <div className="col-plot" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}>
        {data.map((d) => (
          <span key={d.key} className={d.on ? 'col on' : 'col'}>
            {(!many || d.on) && <b>{d.value ?? '-'}</b>}
            <i style={{ height: `${((d.value ?? 0) / max) * 120}px` }} />
          </span>
        ))}
      </div>
      <div className="col-axis" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}>
        {data.map((d, i) => (
          <span key={d.key} className={d.on ? 'on' : ''}>{!many || d.on || i === 0 || i === Math.floor(data.length / 2) ? d.label : ''}</span>
        ))}
      </div>
    </div>
  )
}

/** 스킬 적합도로 진하기: 연한 파랑(15% 이하) → 파랑(78% 이상) */
const LIGHT = [0xe6, 0xee, 0xfd]
const DARK = [0x1b, 0x64, 0xda]
function fitColor(fit: number): string {
  const k = Math.min(1, Math.max(0, (fit - 15) / (78 - 15)))
  return `rgb(${LIGHT.map((a, i) => Math.round(a + (DARK[i] - a) * k)).join(',')})`
}

/** 범례 한 줄: 원 크기 = 열린 공고 수 · 진하기 = 스킬 적합도 · 어두운 빨강 테두리 = 희망 직무 */
export function MapLegend() {
  const t = copy.career
  return (
    <div className="legend map-legend">
      <span><i className="ring-s" /><i className="ring-l" />{t.legendOpen}</span>
      <span>{[20, 47, 75].map((f) => <i key={f} className="shade" style={{ background: fitColor(f) }} />)}{t.legendFit}</span>
      <span><i className="hope-ring" />{t.legendHope}</span>
    </div>
  )
}

interface Box { x: number; y: number; w: number; h: number }
/** 글자 폭 어림(12px): 한글 12, 그 밖 7 */
const textWidth = (s: string) => [...s].reduce((w, ch) => w + (/[ㄱ-힝]/.test(ch) ? 12 : 7), 0)

/** 직무 지도(거품 지도): 가로 스킬 적합도, 세로와 원 크기 열린 공고 수, 진하기 스킬 적합도, 희망 직무는 어두운 빨강 테두리.
 * 오른쪽 위 칸(주력)만 연한 파랑. 칸 경계는 적합도 50%와 열린 공고 가운데 값(점선), 가로 눈금선은 바닥선만 */
export function BubbleMap({ list, demandLine, hope, label }: { list: Position[]; demandLine: number; hope: Set<string>; label: string }) {
  const t = copy.career
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<string | null>(null)
  const H = Math.round(Math.min(380, Math.max(300, width * 0.95)))
  const pad = { l: 34, r: 16, t: 10, b: 36 }
  const pw = Math.max(0, width - pad.l - pad.r)
  const ph = H - pad.t - pad.b
  const shown = list.filter((p) => p.fit !== null)
  const maxOpen = Math.max(1, ...shown.map((p) => p.open))
  const ticks = niceTicks(maxOpen, 3)
  const yMax = ticks[ticks.length - 1]
  const X = (f: number) => pad.l + (f / 100) * pw
  const Y = (n: number) => pad.t + ph - (n / yMax) * ph
  const R = (n: number) => 4 + 14 * Math.sqrt(n / maxOpen)
  const pts = shown.map((p) => ({ p, x: X(p.fit!), y: Y(p.open), r: R(p.open), hope: hope.has(p.id) }))
  // 이름 붙이기: 희망 직무, 큰 원부터 오른쪽 · 왼쪽 · 위 · 아래 중 겹치지 않는 첫 자리(다 겹치면 가장 덜 겹치는 자리)
  const placed: Box[] = []
  const labels = new Map<string, Box>()
  const overlap = (a: Box, b: Box) => !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y)
  const hitsCircle = (b: Box, cx: number, cy: number, r: number) => {
    const nx = Math.min(Math.max(cx, b.x), b.x + b.w)
    const ny = Math.min(Math.max(cy, b.y), b.y + b.h)
    return (nx - cx) ** 2 + (ny - cy) ** 2 < (r + 1) ** 2
  }
  for (const q of [...pts].sort((a, b) => Number(b.hope) - Number(a.hope) || b.r - a.r)) {
    const w = textWidth(q.p.short)
    const h = 14
    const cands: Box[] = [
      { x: q.x + q.r + 4, y: q.y - h / 2, w, h }, { x: q.x - q.r - 4 - w, y: q.y - h / 2, w, h },
      { x: q.x - w / 2, y: q.y - q.r - 3 - h, w, h }, { x: q.x - w / 2, y: q.y + q.r + 3, w, h },
    ]
    const cost = (b: Box) => placed.filter((o) => overlap(b, o)).length * 10
      + pts.filter((o) => o !== q && hitsCircle(b, o.x, o.y, o.r)).length
      + (b.x < pad.l || b.x + b.w > pad.l + pw || b.y < pad.t || b.y + b.h > pad.t + ph ? 100 : 0)
    const best = cands.reduce((a, b) => (cost(b) < cost(a) ? b : a))
    placed.push(best)
    labels.set(q.p.id, best)
  }
  const hovered = pts.find((q) => q.p.id === hover)
  return (
    <div className="chart bubble" ref={ref}>
      {width > 0 && (
        <svg width={width} height={H} role="group" aria-label={label} onPointerLeave={() => setHover(null)}>
          <rect x={X(FIT_LINE)} y={pad.t} width={pad.l + pw - X(FIT_LINE)} height={Math.max(0, Y(demandLine) - pad.t)} className="zone-main" />
          <text x={pad.l + pw - 6} y={pad.t + 16} textAnchor="end" className="zone on">{t.zones.apply}</text>
          <text x={pad.l + 6} y={pad.t + 16} className="zone">{t.zones.grow}</text>
          <text x={pad.l + pw - 6} y={pad.t + ph - 8} textAnchor="end" className="zone">{t.zones.keep}</text>
          <line x1={pad.l} x2={pad.l + pw} y1={Y(0)} y2={Y(0)} className="grid" />
          {ticks.map((v) => <text key={v} x={pad.l - 6} y={Y(v)} className="tick" textAnchor="end" dominantBaseline="middle">{v}</text>)}
          {[0, 25, 50, 75, 100].map((v) => <text key={v} x={X(v)} y={pad.t + ph + 16} className="tick" textAnchor="middle">{v}%</text>)}
          <line x1={X(FIT_LINE)} x2={X(FIT_LINE)} y1={pad.t} y2={pad.t + ph} className="zone-line" />
          <line x1={pad.l} x2={pad.l + pw} y1={Y(demandLine)} y2={Y(demandLine)} className="zone-line" />
          <text x={pad.l + pw} y={H - 4} textAnchor="end" className="axis-name">{t.axisFit} →</text>
          {[...pts].sort((a, b) => b.r - a.r).map((q) => (
            <circle key={q.p.id} cx={q.x} cy={q.y} r={hover === q.p.id ? q.r + 2 : q.r} fill={fitColor(q.p.fit!)}
              className={q.hope ? 'bubble-dot hope' : 'bubble-dot'} tabIndex={0}
              aria-label={`${q.p.name} ${t.open(q.p.open)} ${t.fit(q.p.fit)}${q.hope ? ` ${t.legendHope}` : ''}`}
              onPointerEnter={() => setHover(q.p.id)} onFocus={() => setHover(q.p.id)} onBlur={() => setHover(null)} />
          ))}
          {pts.map((q) => {
            const b = labels.get(q.p.id)!
            return <text key={q.p.id} x={b.x} y={b.y + 11} className={q.hope ? 'bubble-label hope' : 'bubble-label'}>{q.p.short}</text>
          })}
        </svg>
      )}
      {hovered && (
        <Tip x={hovered.x} y={hovered.y - hovered.r - 8} width={width}>
          <b>{t.open(hovered.p.open)} · {t.fit(hovered.p.fit)}</b>
          <span>{hovered.p.name}</span>
        </Tip>
      )}
    </div>
  )
}
