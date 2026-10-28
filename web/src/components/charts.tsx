import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { copy } from '../copy'
import { FIT_LINE, niceTicks, type Bin, type Position, type Quadrant } from '../lib/career'
import { dateText } from '../lib/format'
import { yearsText } from '../lib/profile'

// 커리어 탭 차트. 강조 1색(--accent) + 바탕 회색(--chart-off), 축 하나, 얇은 막대, 값은 끝에, 마우스·포커스에 툴팁.
// 값은 모두 글자(막대 끝 값, 아래 목록)로도 보여서 툴팁 없이도 읽힌다.

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

/** 위 모서리만 둥근 세로 막대(바닥은 각지게) */
function columnPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

/** 날짜(또는 주)마다 새 공고 수. 마지막 막대에만 값을 적는다 */
export function ColumnChart({ data, label }: { data: Bin[]; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const H = 168
  const pad = { l: 32, r: 8, t: 18, b: 24 }
  const values = data.map((d) => d.value ?? 0)
  const ticks = niceTicks(Math.max(1, ...values), 3)
  const yMax = ticks[ticks.length - 1]
  const plotW = Math.max(0, width - pad.l - pad.r)
  const plotH = H - pad.t - pad.b
  const slot = data.length ? plotW / data.length : 0
  const barW = Math.max(1, Math.min(24, slot - 2))
  const y = (v: number) => pad.t + plotH - (v / yMax) * plotH
  const range = (d: Bin) => (d.start === d.end ? dateText(d.start) : `${dateText(d.start)}~${dateText(d.end)}`)
  const xLabels = data.length > 6 ? [0, Math.floor((data.length - 1) / 2), data.length - 1] : data.map((_, i) => i)
  const last = data.length - 1

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={H} role="group" aria-label={label} onPointerLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="grid" />
              <text x={pad.l - 6} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">{t.toLocaleString()}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const cx = pad.l + slot * i + slot / 2
            const h = d.value ? plotH * (d.value / yMax) : 0
            return (
              <g key={d.start}>
                {h > 0 && <path d={columnPath(cx - barW / 2, y(d.value!), barW, h)} className={hover === i ? 'mark on' : 'mark'} />}
                {i === last && d.value !== null && (
                  <text x={cx} y={y(d.value) - 6} className="value" textAnchor="middle">{d.value.toLocaleString()}</text>
                )}
                <rect x={pad.l + slot * i} y={pad.t} width={slot} height={plotH} className="hit" tabIndex={0}
                  aria-label={`${range(d)} ${d.value === null ? copy.career.notCounted : copy.career.count(d.value)}`}
                  onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
              </g>
            )
          })}
          {xLabels.map((i) => (
            <text key={i} x={pad.l + slot * i + slot / 2} y={H - 6} className="tick"
              textAnchor={data.length > 6 ? (i === 0 ? 'start' : i === last ? 'end' : 'middle') : 'middle'}>
              {dateText(data[i].start)}
            </text>
          ))}
        </svg>
      )}
      {hover !== null && data[hover] && (
        <Tip x={pad.l + slot * hover + slot / 2} y={y(data[hover].value ?? 0) - 8} width={width}>
          <b>{data[hover].value === null ? copy.career.notCounted : copy.career.count(data[hover].value!)}</b>
          <span>{range(data[hover])}</span>
        </Tip>
      )}
    </div>
  )
}

export interface BarRow {
  key: string
  label: ReactNode
  value: number
  /** 막대 끝에 적는 값 */
  text: string
  /** 강조(내 연차, 내 스킬, 내 직무) */
  on?: boolean
  /** 강조한 이유를 글자로(색만으로 구분하지 않게) */
  tag?: string
  selected?: boolean
  onClick?: () => void
}

/** 가로 막대 목록. 한 축(같은 단위)만 그린다 */
export function BarList({ rows, max }: { rows: BarRow[]; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="bars">
      {rows.map((r) => {
        const inner = (
          <>
            <span className="bar-label">
              <span className="bar-name">{r.label}</span>
              {r.tag && <span className="bar-tag">{r.tag}</span>}
            </span>
            <span className="bar-track">
              <span className={r.on ? 'bar on' : 'bar'} style={{ width: `${Math.max(r.value ? 1 : 0, (r.value / top) * 100)}%` }} />
            </span>
            <span className="bar-value">{r.text}</span>
          </>
        )
        return r.onClick
          ? <button key={r.key} type="button" className={r.selected ? 'bar-row selected' : 'bar-row'} aria-pressed={r.selected} onClick={r.onClick}>{inner}</button>
          : <div key={r.key} className="bar-row">{inner}</div>
      })}
    </div>
  )
}

const CORNERS: { q: Quadrant; x: 'l' | 'r'; y: 't' | 'b' }[] = [
  { q: 'grow', x: 'l', y: 't' }, { q: 'apply', x: 'r', y: 't' }, { q: 'reduce', x: 'l', y: 'b' }, { q: 'keep', x: 'r', y: 'b' },
]

/** 글자 폭 어림(13px): 한글 13, 그 밖 7.5 */
const textWidth = (s: string) => [...s].reduce((w, ch) => w + (/[ㄱ-힝]/.test(ch) ? 13 : 7.5), 0)

interface Box { x: number; y: number; w: number; h: number }

/** 직무 지도(포지션 맵): 가로 스킬 적합도(0~100%), 세로 열린 공고. 기준선 두 개로 네 칸을 나눈다 */
export function PositionMap({ list, demandLine, mine, label }: {
  list: Position[]
  demandLine: number
  mine: Set<string>
  label: string
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<string | null>(null)
  const H = Math.round(Math.min(360, Math.max(280, width * 0.75)))
  const pad = { l: 40, r: 16, t: 28, b: 36 }
  const plotW = Math.max(0, width - pad.l - pad.r)
  const plotH = H - pad.t - pad.b
  const ticks = niceTicks(Math.max(1, ...list.map((p) => p.open)), 4)
  const yMax = ticks[ticks.length - 1]
  const x = (fit: number) => pad.l + (fit / 100) * plotW
  const y = (open: number) => pad.t + plotH - (open / yMax) * plotH
  const shown = list.filter((p) => p.fit !== null)

  // 이름 붙이기: 점 둘레 여덟 자리 중 다른 이름·점과 겹치지 않는 첫 자리. 다 겹치면 가장 덜 겹치는 자리. 내 직무부터 자리를 잡는다
  const placed: Box[] = shown.map((p) => ({ x: x(p.fit!) - 6, y: y(p.open) - 6, w: 12, h: 12 }))
  const labels = new Map<string, { x: number; y: number; anchor: 'start' | 'end' | 'middle' }>()
  const order = [...shown].sort((a, b) => Number(mine.has(b.id)) - Number(mine.has(a.id)) || b.open - a.open)
  const area = (a: Box, b: Box) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))
  for (const p of order) {
    const cx = x(p.fit!)
    const cy = y(p.open)
    const w = textWidth(p.short)
    const at = (dx: number, dy: number, anchor: 'start' | 'end' | 'middle') => {
      const left = anchor === 'start' ? cx + dx : anchor === 'end' ? cx + dx - w : cx + dx - w / 2
      return { box: { x: left, y: cy + dy - 8, w, h: 16 }, at: { x: cx + dx, y: cy + dy, anchor } }
    }
    const options = [
      at(9, 0, 'start'), at(-9, 0, 'end'), at(0, -16, 'middle'), at(0, 16, 'middle'),
      at(6, -14, 'start'), at(6, 14, 'start'), at(-6, -14, 'end'), at(-6, 14, 'end'),
    ]
    const inside = (b: Box) => b.x >= 0 && b.x + b.w <= width && b.y >= 0 && b.y + b.h <= H - pad.b + 4
    const cost = (b: Box) => placed.reduce((sum, q) => sum + area(b, q), 0)
    const fits = options.filter((o) => inside(o.box))
    const pick = fits.find((o) => cost(o.box) === 0)
      ?? [...fits].sort((a, b) => cost(a.box) - cost(b.box))[0] ?? options[0]
    placed.push(pick.box)
    labels.set(p.id, pick.at)
  }
  const hovered = shown.find((p) => p.id === hover)
  // 점이 겹쳐도 모두 고를 수 있게 포인터에서 가장 가까운 점(24px 안)
  const nearest = (px: number, py: number): string | null => {
    let best: string | null = null
    let dist = 24 * 24
    for (const p of shown) {
      const d = (x(p.fit!) - px) ** 2 + (y(p.open) - py) ** 2
      if (d < dist) {
        dist = d
        best = p.id
      }
    }
    return best
  }

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={H} role="group" aria-label={label} onPointerLeave={() => setHover(null)}
          onPointerMove={(e) => setHover(nearest(e.nativeEvent.offsetX, e.nativeEvent.offsetY))}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="grid" />
              <text x={pad.l - 6} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">{t.toLocaleString()}</text>
            </g>
          ))}
          {[0, 50, 100].map((t) => (
            <text key={t} x={x(t)} y={H - pad.b + 16} className="tick" textAnchor={t === 0 ? 'start' : t === 100 ? 'end' : 'middle'}>{t}%</text>
          ))}
          <text x={width - pad.r} y={H - 4} className="tick" textAnchor="end">{copy.career.axisFit} →</text>
          <text x={pad.l} y={12} className="tick" textAnchor="start">↑ {copy.career.axisDemand}</text>
          <line x1={x(FIT_LINE)} x2={x(FIT_LINE)} y1={pad.t} y2={pad.t + plotH} className="ref" />
          <line x1={pad.l} x2={width - pad.r} y1={y(demandLine)} y2={y(demandLine)} className="ref" />
          {CORNERS.map((c) => (
            <text key={c.q} className="quad" x={c.x === 'l' ? pad.l + 6 : width - pad.r - 6} y={c.y === 't' ? pad.t + 14 : pad.t + plotH - 8}
              textAnchor={c.x === 'l' ? 'start' : 'end'}>{copy.career.quadrants[c.q]}</text>
          ))}
          {shown.map((p) => {
            const l = labels.get(p.id)!
            const on = mine.has(p.id)
            return (
              <g key={p.id}>
                <circle cx={x(p.fit!)} cy={y(p.open)} r={hover === p.id ? 6.5 : 5} className={on ? 'dot on' : 'dot'} />
                <text x={l.x} y={l.y} className={on ? 'dot-label on' : 'dot-label'} textAnchor={l.anchor} dominantBaseline="middle">{p.short}</text>
                {/* 마우스는 가장 가까운 점(nearest)으로, 키보드는 점마다 포커스 */}
                <circle cx={x(p.fit!)} cy={y(p.open)} r={14} className="hit" tabIndex={0}
                  aria-label={`${p.name} ${copy.career.open(p.open)} ${copy.career.fit(p.fit)}`}
                  onFocus={() => setHover(p.id)} onBlur={() => setHover(null)} />
              </g>
            )
          })}
        </svg>
      )}
      {hovered && (
        <Tip x={x(hovered.fit!)} y={y(hovered.open) - 12} width={width}>
          <b>{copy.career.open(hovered.open)} · {copy.career.fit(hovered.fit)}</b>
          <span>{hovered.name}</span>
          {(hovered.years > 0 || hovered.match) && (
            <span>{[hovered.years > 0 && copy.career.years(yearsText(Math.round(hovered.years * 10) / 10)),
              hovered.match && copy.career.matchAvg(hovered.match.avg, hovered.match.n)].filter(Boolean).join(' · ')}</span>
          )}
        </Tip>
      )}
    </div>
  )
}

/** 몇 해 안 되는 값(연도별 매출). 막대마다 값을 적는다(3~5개라 다 읽혀서 툴팁·포커스는 두지 않는다).
 * 음수는 0 아래로, 마지막 해만 강조색 */
export function YearBars({ data, label, format }: {
  data: { year: number; value: number | null | undefined }[]
  label: string
  format: (v: number) => string
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const vals = data.map((d) => d.value ?? 0)
  const max = Math.max(0, ...vals)
  const min = Math.min(0, ...vals)
  const H = min < 0 ? 166 : 150
  // 음수 막대 아래에 값을 적을 자리를 연도 위에 따로 둔다
  const pad = { l: 8, r: 8, t: 22, b: min < 0 ? 42 : 24 }
  const span = max - min || 1
  const plotW = Math.max(0, width - pad.l - pad.r)
  const plotH = H - pad.t - pad.b
  const slot = data.length ? plotW / data.length : 0
  const barW = Math.max(1, Math.min(40, slot * 0.5))
  const y = (v: number) => pad.t + ((max - v) / span) * plotH
  const zero = y(0)
  const last = data.length - 1
  const summary = `${label} ${data.map((d) => `${d.year} ${d.value === null || d.value === undefined ? '-' : format(d.value)}`).join(', ')}`

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label={summary}>
          <line x1={pad.l} x2={width - pad.r} y1={zero} y2={zero} className="grid" />
          {data.map((d, i) => {
            const cx = pad.l + slot * i + slot / 2
            const v = d.value
            if (v === null || v === undefined) {
              return <text key={d.year} x={cx} y={H - 6} className="tick" textAnchor="middle">{d.year}</text>
            }
            const top = Math.min(y(v), zero)
            const h = Math.abs(y(v) - zero)
            const cls = i === last ? 'mark' : 'mark off'
            return (
              <g key={d.year}>
                {h > 0 && (v >= 0
                  ? <path d={columnPath(cx - barW / 2, top, barW, h)} className={cls} />
                  : <rect x={cx - barW / 2} y={top} width={barW} height={h} className={cls} />)}
                <text x={cx} y={v >= 0 ? top - 6 : top + h + 14} className="value" textAnchor="middle">{format(v)}</text>
                <text x={cx} y={H - 6} className="tick" textAnchor="middle">{d.year}</text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
