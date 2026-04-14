import { useState, useEffect, useRef } from 'react'
import type { SessionStatus } from '../types'
import { getDownloadUrl, startExport } from '../api/client'

interface Props { sessionId: string; status: SessionStatus | null; processing: boolean }

const DOT: Record<string, string> = {
  idle:       'bg-dim',
  uploading:  'bg-warning animate-pulse-op',
  loading:    'bg-warning animate-pulse-op',
  ready:      'bg-success',
  processing: 'bg-accent animate-pulse-op',
  exporting:  'bg-accent animate-pulse-op',
  error:      'bg-danger',
}

export default function StatusBar({ sessionId, status, processing }: Props) {
  const [waitForDownload, setWaitForDownload] = useState(false)
  const prevStatusRef = useRef<string>('')

  // Detect exporting → ready transition to auto-trigger download
  useEffect(() => {
    const curr = status?.status ?? ''
    const prev = prevStatusRef.current
    prevStatusRef.current = curr
    if (prev === 'exporting' && curr === 'ready' && waitForDownload) {
      setWaitForDownload(false)
      window.open(getDownloadUrl(sessionId))
    }
  }, [status?.status, sessionId, waitForDownload])

  const doExportAndDownload = async () => {
    setWaitForDownload(true)
    try { await startExport(sessionId) }
    catch { setWaitForDownload(false) }
  }

  const exporting = status?.status === 'exporting' || waitForDownload

  if (!status) {
    return <div className="h-7 bg-surface border-t border-border" />
  }

  const phase  = status.status
  const dot    = DOT[phase] ?? 'bg-dim'
  const orig   = status.original_points
  const curr   = status.current_points
  const removed = orig - curr
  const pct    = orig > 0 ? ((removed / orig) * 100).toFixed(2) : '0.00'
  const fmt    = (n: number) => n.toLocaleString()

  return (
    <div className="h-7 flex items-center justify-between px-3 bg-surface border-t border-border
      flex-shrink-0 text-[11px] gap-4 overflow-hidden">

      {/* Status */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />
        <span className="text-muted capitalize">{status.status_message || phase}</span>
      </div>

      {/* Point counts */}
      {orig > 0 && (
        <div className="flex items-center gap-4 text-muted font-mono">
          <span>Orig: <span className="text-text">{fmt(orig)}</span></span>
          <span>Current: <span className={curr < orig ? 'text-success' : 'text-text'}>{fmt(curr)}</span></span>
          {removed > 0 && (
            <span>Removed: <span className="text-removed">−{fmt(removed)} ({pct}%)</span></span>
          )}
        </div>
      )}

      {/* Right side: hash + export */}
      <div className="flex items-center gap-3 ml-auto flex-shrink-0">
        {status.original_filename && (
          <span className="text-dim truncate max-w-[180px]">{status.original_filename}</span>
        )}
        {status.original_hash && (
          <span className="text-dim font-mono hidden xl:block" title={`SHA-256: ${status.original_hash}`}>
            SHA-256: {status.original_hash.slice(0, 16)}…
          </span>
        )}

        {phase === 'ready' && (
          <button onClick={doExportAndDownload} disabled={exporting || processing}
            className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-2.5 py-0.5 rounded font-medium">
            {exporting ? (
              <>
                <div className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />
                Exporting…
              </>
            ) : (
              <>
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Export & Download
              </>
            )}
          </button>
        )}
      </div>
    </div>
  )
}
