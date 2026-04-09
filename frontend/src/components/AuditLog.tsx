import { useState } from 'react'
import type { AuditEntry } from '../types'
import { getReportUrl } from '../api/client'

interface Props { sessionId: string; entries: AuditEntry[] }

const fmt = (n: number) => n.toLocaleString()

function bboxStr(b?: { min: number[]; max: number[] } | null) {
  if (!b) return 'Entire point cloud'
  return `X[${b.min[0].toFixed(2)}, ${b.max[0].toFixed(2)}]  Y[${b.min[1].toFixed(2)}, ${b.max[1].toFixed(2)}]  Z[${b.min[2].toFixed(2)}, ${b.max[2].toFixed(2)}]`
}

function OpBadge({ type }: { type: string }) {
  const labels: Record<string, { label: string; cls: string }> = {
    auto_clean:    { label: 'Auto', cls: 'bg-accent/10 text-accent border-accent/20' },
    manual_clean:  { label: 'Manual', cls: 'bg-surface3 text-muted border-border' },
    region_delete: { label: 'Delete', cls: 'bg-danger-dim text-danger border-danger/20' },
  }
  const { label, cls } = labels[type] ?? { label: type, cls: 'bg-surface3 text-muted border-border' }
  return <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${cls}`}>{label}</span>
}

function Row({ entry, idx }: { entry: AuditEntry; idx: number }) {
  const [open, setOpen] = useState(false)
  const pct = entry.points_before > 0
    ? ((entry.points_removed / entry.points_before) * 100).toFixed(2)
    : '0.00'
  const ts = entry.timestamp.slice(0, 19).replace('T', ' ')

  return (
    <div className={`border-b border-border/50 last:border-0 transition-colors ${open ? 'bg-surface2/50' : 'hover:bg-surface2/30'}`}>
      {/* Row header */}
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left">
        {/* Step number */}
        <div className="flex-shrink-0 w-5 h-5 rounded-full bg-surface3 border border-border
          text-[10px] text-muted flex items-center justify-center font-mono font-bold">
          {idx}
        </div>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span className="text-text text-xs font-medium truncate">{entry.algorithm}</span>
            <OpBadge type={entry.operation_type} />
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted">
            <span>{ts} UTC</span>
            {entry.region_bbox && <span className="text-dim">· region scoped</span>}
          </div>
        </div>

        {/* Removed count */}
        <div className="flex-shrink-0 text-right">
          <div className={`text-xs font-mono font-medium ${entry.points_removed > 0 ? 'text-removed' : 'text-success'}`}>
            {entry.points_removed > 0 ? `−${fmt(entry.points_removed)}` : 'No change'}
          </div>
          {entry.points_removed > 0 && (
            <div className="text-[10px] text-muted font-mono">{pct}%</div>
          )}
        </div>

        <div className="text-dim text-xs ml-1">{open ? '▲' : '▼'}</div>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="px-4 pb-4 animate-fade-in">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-[11px] bg-surface2 border border-border rounded-lg p-3">
            <Field label="Points before" value={fmt(entry.points_before)} mono />
            <Field label="Points after"  value={fmt(entry.points_after)}  mono colour="text-success" />
            <Field label="Points removed" value={`${fmt(entry.points_removed)} (${pct}%)`} mono colour="text-removed" />
            <Field label="Operation"     value={entry.operation_type} mono />
            <div className="col-span-2">
              <Field label="Removed points — spatial extent" value={bboxStr(entry.removed_bbox)} mono />
            </div>
            <div className="col-span-2">
              <Field label="Applied to region" value={bboxStr(entry.region_bbox)} mono />
            </div>
            <div className="col-span-2">
              <Field label="Parameters"
                value={Object.entries(entry.params).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join('  ·  ')}
                mono />
            </div>
            {entry.operator_notes && (
              <div className="col-span-2">
                <Field label="Analyst notes" value={entry.operator_notes} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, mono, colour }: {
  label: string; value: string; mono?: boolean; colour?: string
}) {
  return (
    <div>
      <div className="text-[10px] text-dim uppercase tracking-wider mb-0.5">{label}</div>
      <div className={`${mono ? 'font-mono' : ''} ${colour ?? 'text-text'} break-all leading-snug`}>{value}</div>
    </div>
  )
}

export default function AuditLog({ sessionId, entries }: Props) {
  const [caseNum,  setCaseNum]  = useState('')
  const [analyst,  setAnalyst]  = useState('')

  const totalRemoved = entries.reduce((s, e) => s + e.points_removed, 0)
  const origCount    = entries[0]?.points_before ?? 0
  const pct          = origCount > 0 ? ((totalRemoved / origCount) * 100).toFixed(2) : '0.00'

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border flex-shrink-0 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs font-semibold text-text whitespace-nowrap">Audit Log</span>
          {entries.length > 0 && (
            <span className="text-[11px] text-muted whitespace-nowrap">
              {entries.length} op{entries.length !== 1 ? 's' : ''}
              {origCount > 0 && <span className="text-removed"> · −{pct}% total</span>}
            </span>
          )}
        </div>

        {/* PDF export row */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <input value={caseNum} onChange={e => setCaseNum(e.target.value)}
            placeholder="Case #"
            className="bg-surface2 border border-border text-text text-xs rounded-lg px-2.5 py-1 w-20
              focus:outline-none focus:border-accent placeholder:text-dim" />
          <input value={analyst} onChange={e => setAnalyst(e.target.value)}
            placeholder="Analyst name"
            className="bg-surface2 border border-border text-text text-xs rounded-lg px-2.5 py-1 w-32
              focus:outline-none focus:border-accent placeholder:text-dim" />
          <a href={getReportUrl(sessionId, caseNum, analyst)} target="_blank" rel="noreferrer"
            className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white
              text-xs px-3 py-1.5 rounded-lg transition-colors font-medium whitespace-nowrap">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293
                   l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            PDF Report
          </a>
        </div>
      </div>

      {/* Entries */}
      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted text-xs gap-2">
            <svg className="w-8 h-8 text-border" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2
                   M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            No operations yet — apply a cleaning tool to begin
          </div>
        ) : (
          entries.map((e, i) => <Row key={e.id} entry={e} idx={i + 1} />)
        )}
      </div>
    </div>
  )
}
