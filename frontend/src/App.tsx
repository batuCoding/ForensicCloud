import { useState, useEffect, useCallback, useRef } from 'react'
import FileUpload from './components/FileUpload'
import Viewer3D from './components/Viewer3D'
import ToolPanel from './components/ToolPanel'
import AuditLog from './components/AuditLog'
import StatusBar from './components/StatusBar'
import type { SessionStatus, BoundingBox, AuditEntry } from './types'
import { getStatus, getAuditLog } from './api/client'

const POLL_MS = 1500

export default function App() {
  const [sessionId, setSessionId]     = useState<string | null>(null)
  const [status, setStatus]           = useState<SessionStatus | null>(null)
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([])
  const [processing, setProcessing]   = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedBBox, setSelectedBBox] = useState<BoundingBox | null>(null)
  const [origKey, setOrigKey]         = useState(0)
  const [currKey, setCurrKey]         = useState(0)
  const [auditHeight, setAuditHeight] = useState(200)

  const prevStatusRef = useRef<string>('')
  const auditDragRef  = useRef(false)

  // ── Polling ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    const tick = async () => {
      if (cancelled) return
      try {
        const s = await getStatus(sessionId)
        setStatus(s)
      } catch { /* swallow network hiccups */ }
      if (!cancelled) setTimeout(tick, POLL_MS)
    }
    tick()
    return () => { cancelled = true }
  }, [sessionId])

  // ── React to status transitions ─────────────────────────────────────────
  useEffect(() => {
    if (!status || !sessionId) return
    const curr = status.status
    const prev = prevStatusRef.current
    prevStatusRef.current = curr

    // File loaded for the first time
    if (curr === 'ready' && (prev === 'loading' || prev === 'uploading' || prev === '')) {
      setOrigKey(k => k + 1)
      setCurrKey(k => k + 1)
    }

    // A cleaning operation just finished
    if (curr === 'ready' && prev === 'processing') {
      setProcessing(false)
      setCurrKey(k => k + 1)
      getAuditLog(sessionId).then(setAuditEntries).catch(() => {})
    }

    // Export done
    if (curr === 'ready' && prev === 'exporting') {
      setProcessing(false)
    }

    if (curr === 'error') {
      setProcessing(false)
    }
  }, [status?.status, sessionId])

  // ── Session ──────────────────────────────────────────────────────────────
  const handleSessionCreated = useCallback((id: string) => {
    setSessionId(id)
    prevStatusRef.current = ''
    setOrigKey(0)
    setCurrKey(0)
    setAuditEntries([])
    setSelectedBBox(null)
    setSelectionMode(false)
    setProcessing(false)
  }, [])

  const onProcessingStart = useCallback(() => setProcessing(true), [])
  const onProcessingDone  = useCallback(() => {}, []) // real done handled by status poll

  const onRegionSelected   = useCallback((bbox: BoundingBox) => {
    setSelectedBBox(bbox)
    setSelectionMode(false)
  }, [])
  const onSelectionCleared = useCallback(() => setSelectedBBox(null), [])
  const onToggleSelection  = useCallback(() => setSelectionMode(m => !m), [])

  // ── Audit panel drag resize ──────────────────────────────────────────────
  const onDividerDown = (e: React.MouseEvent) => {
    e.preventDefault()
    auditDragRef.current = true
    const startY = e.clientY
    const startH = auditHeight

    const onMove = (ev: MouseEvent) => {
      if (!auditDragRef.current) return
      setAuditHeight(Math.max(80, Math.min(startH + (startY - ev.clientY), 500)))
    }
    const onUp = () => {
      auditDragRef.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const phase     = status?.status ?? 'idle'
  const isLoading = phase === 'loading' || phase === 'uploading'
  const isReady   = phase === 'ready'

  if (!sessionId) {
    return <FileUpload onSessionCreated={handleSessionCreated} />
  }

  return (
    <div className="flex flex-col h-screen bg-bg overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="h-11 flex items-center gap-3 px-4 bg-surface border-b border-border flex-shrink-0">
        <button
          onClick={() => { setSessionId(null); setStatus(null) }}
          className="flex items-center gap-1.5 text-muted hover:text-text transition-colors text-xs"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          New file
        </button>

        <div className="w-px h-4 bg-border" />

        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-text">
            Forensic<span className="text-accent">Cloud</span>
          </span>
          {status?.original_filename && (
            <>
              <span className="text-border">/</span>
              <span className="text-muted text-xs truncate max-w-sm font-mono">
                {status.original_filename}
              </span>
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-4 text-xs text-muted">
          {status?.scan_count != null && (
            <span>{status.scan_count} scan{status.scan_count !== 1 ? 's' : ''}</span>
          )}
          {status?.has_colors != null && (
            <span className={status.has_colors ? 'text-success' : 'text-dim'}>
              {status.has_colors ? '● RGB colour' : '○ No colour data'}
            </span>
          )}
          {status?.original_hash && (
            <span className="font-mono text-dim hidden lg:block" title={`SHA-256: ${status.original_hash}`}>
              {status.original_hash.slice(0, 8)}…
            </span>
          )}
        </div>
      </header>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* 3D Viewer */}
        <div className="flex-1 relative overflow-hidden bg-bg">
          {isLoading ? (
            <LoadingScreen message={status?.status_message} progress={status?.progress ?? 0} />
          ) : (
            <Viewer3D
              sessionId={sessionId}
              originalKey={origKey}
              currentKey={currKey}
              selectionMode={selectionMode && isReady && !processing}
              onRegionSelected={onRegionSelected}
              onSelectionCleared={onSelectionCleared}
              currentBBox={selectedBBox}
            />
          )}

          {processing && (
            <div className="absolute inset-0 bg-bg/70 backdrop-blur-sm flex flex-col items-center justify-center gap-4 z-10 animate-fade-in">
              <div className="w-10 h-10 border-2 border-border border-t-accent rounded-full animate-spin" />
              <div className="text-text text-sm font-medium">{status?.status_message ?? 'Processing…'}</div>
              {(status?.progress ?? 0) > 0 && (
                <div className="w-48 h-1 bg-surface3 rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full transition-all duration-300"
                    style={{ width: `${status?.progress ?? 0}%` }} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Tool panel */}
        <div className="w-72 flex-shrink-0 border-l border-border">
          <ToolPanel
            sessionId={sessionId}
            processing={processing}
            selectionMode={selectionMode}
            selectedBBox={selectedBBox}
            onProcessingStart={onProcessingStart}
            onProcessingDone={onProcessingDone}
            onToggleSelection={onToggleSelection}
            onClearSelection={onSelectionCleared}
          />
        </div>
      </div>

      {/* ── Audit log ───────────────────────────────────────────────────── */}
      {sessionId && (
        <>
          <div
            onMouseDown={onDividerDown}
            className="h-1 bg-border hover:bg-accent/50 cursor-ns-resize flex-shrink-0 transition-colors"
          />
          <div style={{ height: auditHeight }} className="flex-shrink-0 bg-surface border-t border-border overflow-hidden">
            <AuditLog sessionId={sessionId} entries={auditEntries} />
          </div>
        </>
      )}

      {/* ── Status bar ──────────────────────────────────────────────────── */}
      <StatusBar sessionId={sessionId} status={status} processing={processing} />
    </div>
  )
}

function LoadingScreen({ message, progress }: { message?: string; progress: number }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-5 animate-fade-in">
      <div className="relative">
        <div className="w-14 h-14 border-2 border-border rounded-full" />
        <div className="absolute inset-0 w-14 h-14 border-2 border-transparent border-t-accent rounded-full animate-spin" />
      </div>
      <div className="text-center">
        <div className="text-text font-medium mb-1">{message ?? 'Parsing point cloud…'}</div>
        <div className="text-muted text-xs">Large files may take a minute</div>
      </div>
      {progress > 0 && (
        <div className="w-56">
          <div className="flex justify-between text-xs text-muted mb-1.5">
            <span>Progress</span><span>{progress}%</span>
          </div>
          <div className="h-1 bg-surface3 rounded-full overflow-hidden">
            <div className="h-full bg-accent rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
    </div>
  )
}
