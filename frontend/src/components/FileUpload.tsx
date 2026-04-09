import { useState, useCallback } from 'react'
import { uploadFile } from '../api/client'

interface Props { onSessionCreated: (id: string) => void }

export default function FileUpload({ onSessionCreated }: Props) {
  const [dragging,   setDragging]   = useState(false)
  const [uploading,  setUploading]  = useState(false)
  const [uploadPct,  setUploadPct]  = useState(0)
  const [error,      setError]      = useState<string | null>(null)

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.e57')) {
      setError('Only .e57 files are supported.')
      return
    }
    setError(null)
    setUploading(true)
    setUploadPct(0)
    try {
      const id = await uploadFile(file, setUploadPct)
      onSessionCreated(id)
    } catch (e: unknown) {
      setError((e as Error).message)
      setUploading(false)
    }
  }, [onSessionCreated])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-8">
      <div className="w-full max-w-lg">

        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-accent/10 border border-accent/30 flex items-center justify-center">
              <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618
                     3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03
                     9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <div className="text-xl font-bold tracking-tight text-text">
                Forensic<span className="text-accent">Cloud</span>
              </div>
              <div className="text-xs text-muted">E57 Point Cloud Cleaning Platform</div>
            </div>
          </div>
        </div>

        {/* Drop zone */}
        <label
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`
            group relative flex flex-col items-center justify-center
            rounded-xl border-2 border-dashed p-12 cursor-pointer
            transition-all duration-200 select-none
            ${dragging
              ? 'border-accent bg-accent-dim/30 scale-[1.01]'
              : 'border-border bg-surface hover:border-border2 hover:bg-surface2'}
          `}
        >
          <input type="file" accept=".e57" className="sr-only"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
            disabled={uploading} />

          {uploading ? (
            <div className="w-full text-center">
              <div className="w-10 h-10 border-2 border-border border-t-accent rounded-full animate-spin mx-auto mb-4" />
              <div className="text-text font-medium mb-3">Uploading file…</div>
              <div className="w-full h-1.5 bg-surface3 rounded-full overflow-hidden mb-2">
                <div className="h-full bg-accent rounded-full transition-all duration-300"
                  style={{ width: `${uploadPct}%` }} />
              </div>
              <div className="text-muted text-xs">{uploadPct}%</div>
            </div>
          ) : (
            <>
              <div className={`w-14 h-14 rounded-xl border flex items-center justify-center mb-5 transition-colors
                ${dragging ? 'border-accent/50 bg-accent/10' : 'border-border bg-surface2 group-hover:border-border2'}`}>
                <svg className={`w-7 h-7 transition-colors ${dragging ? 'text-accent' : 'text-muted'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <div className="text-text font-semibold mb-1">
                {dragging ? 'Drop to load' : 'Drop your E57 file here'}
              </div>
              <div className="text-muted text-xs mb-4">or click to browse</div>
              <div className="inline-flex items-center gap-1.5 text-[11px] text-dim bg-surface2 border border-border rounded-lg px-3 py-1.5">
                <span>.e57</span>
                <span className="text-border">·</span>
                <span>Multi-GB files supported</span>
                <span className="text-border">·</span>
                <span>Processed locally</span>
              </div>
            </>
          )}
        </label>

        {error && (
          <div className="mt-4 flex items-start gap-2.5 bg-danger-dim border border-danger/30
            rounded-lg px-4 py-3 text-danger text-xs animate-fade-in">
            <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        )}

        {/* Feature grid */}
        <div className="mt-8 grid grid-cols-2 gap-2">
          {[
            { icon: '🔒', label: 'SHA-256 chain of custody' },
            { icon: '📋', label: 'Court-ready PDF audit report' },
            { icon: '🎯', label: '3D region-based cleaning' },
            { icon: '👁', label: 'Before / After split view' },
            { icon: '🎨', label: 'Crime scene tape detection' },
            { icon: '🪟', label: 'Window & glass removal' },
          ].map(f => (
            <div key={f.label}
              className="flex items-center gap-2.5 bg-surface border border-border rounded-lg px-3 py-2.5 text-xs text-muted">
              <span>{f.icon}</span>
              <span>{f.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
