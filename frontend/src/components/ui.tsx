import type { ReactNode } from 'react'
import { ChevronRight, Info } from 'lucide-react'
import type { StatusTone } from '../types'

export function Panel({
  title,
  subtitle,
  action,
  children,
  className = '',
}: {
  title?: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {title || action ? (
        <header className="panel-head">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {action}
        </header>
      ) : null}
      {children}
    </section>
  )
}

export function StatusTag({ children, tone = 'neutral' }: { children: ReactNode; tone?: StatusTone }) {
  return <span className={`status-tag status-tag--${tone}`}>{children}</span>
}

export function ScoreBar({ value, tone = 'teal', label }: { value: number; tone?: 'teal' | 'amber' | 'blue'; label?: string }) {
  return (
    <div className="score-line">
      {label ? <span>{label}</span> : null}
      <div className="score-track" aria-label={`${label ?? '评分'} ${value}%`}>
        <i className={`score-fill score-fill--${tone}`} style={{ width: `${value}%` }} />
      </div>
      <strong>{value}%</strong>
    </div>
  )
}

export function LinkButton({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return <button className="link-button" type="button" onClick={onClick}>{children}<ChevronRight size={15} /></button>
}

export function MetricStrip({ items }: { items: { label: string; value: string; delta?: string }[] }) {
  return (
    <div className="metric-strip">
      {items.map((item) => (
        <div className="metric-item" key={item.label}>
          <span>{item.label}<Info size={13} /></span>
          <div><strong>{item.value}</strong>{item.delta ? <em>{item.delta}</em> : null}</div>
        </div>
      ))}
    </div>
  )
}

export function MiniLineChart({ color = '#1769e0', values }: { color?: string; values: number[] }) {
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = Math.max(max - min, 1)
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${34 - ((value - min) / range) * 28}`).join(' ')
  return (
    <svg className="mini-chart" viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="35" x2="100" y2="35" stroke="#e7ecf3" strokeWidth="1" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭">×</button></header>
        {children}
      </section>
    </div>
  )
}
