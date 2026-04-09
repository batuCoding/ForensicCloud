import { useState } from 'react'
import type { BoundingBox, AutoCleanParams, Algorithm, AlgorithmParams } from '../types'
import { runAutoClean, runManualClean, deleteRegion } from '../api/client'

interface Props {
  sessionId: string
  processing: boolean
  selectionMode: boolean
  selectedBBox: BoundingBox | null
  onProcessingStart: () => void
  onProcessingDone: () => void
  onToggleSelection: () => void
  onClearSelection: () => void
}

type Tab = 'auto' | 'manual' | 'region'

// ── Tiny reusable controls ────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-medium text-muted uppercase tracking-wider mb-2">{children}</div>
}

function Param({ label, value, min, max, step = 0.01, decimals = 2, onChange }: {
  label: string; value: number; min: number; max: number; step?: number; decimals?: number
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="text-text font-mono">{value.toFixed(decimals)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))} />
    </div>
  )
}

function Toggle({ label, desc, checked, onChange }: {
  label: string; desc?: string; checked: boolean; onChange: (v: boolean) => void
}) {
  return (
    <button onClick={() => onChange(!checked)}
      className="w-full flex items-center gap-3 text-left py-1">
      <div className={`relative w-8 h-4 rounded-full flex-shrink-0 transition-colors ${checked ? 'bg-accent' : 'bg-surface3'}`}>
        <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${checked ? 'left-4' : 'left-0.5'}`} />
      </div>
      <div>
        <div className="text-xs text-text">{label}</div>
        {desc && <div className="text-[11px] text-muted">{desc}</div>}
      </div>
    </button>
  )
}

function Btn({ onClick, disabled, variant = 'primary', children }: {
  onClick: () => void; disabled?: boolean; variant?: 'primary' | 'danger' | 'ghost'
  children: React.ReactNode
}) {
  const cls = variant === 'primary'
    ? 'bg-accent hover:bg-accent-hover text-white'
    : variant === 'danger'
    ? 'bg-danger/10 hover:bg-danger/20 border border-danger/30 text-danger'
    : 'bg-surface3 hover:bg-border text-text border border-border'
  return (
    <button onClick={onClick} disabled={disabled}
      className={`w-full py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}>
      {children}
    </button>
  )
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="mx-4 mb-3 flex gap-2 items-start bg-danger-dim border border-danger/30 rounded-lg p-3 text-danger text-xs animate-fade-in">
      <span className="mt-0.5">⚠</span>{msg}
    </div>
  )
}

// ── Section divider ───────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <Label>{title}</Label>
      <div className="space-y-2.5">{children}</div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ToolPanel({
  sessionId, processing, selectionMode, selectedBBox,
  onProcessingStart, onToggleSelection, onClearSelection,
}: Props) {
  const [tab,   setTab]   = useState<Tab>('auto')
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')

  // Auto params
  const [sorN,    setSorN]   = useState(20)
  const [sorStd,  setSorStd] = useState(2.0)
  const [rorPts,  setRorPts] = useState(10)
  const [rorR,    setRorR]   = useState(0.08)
  const [runClr,  setRunClr] = useState(true)
  const [runPln,  setRunPln] = useState(true)
  const [colorPreset, setColorPreset] = useState('tape_all')

  // Manual params
  const [algo,       setAlgo]      = useState<Algorithm>('statistical_outlier')
  const [mSorN,      setMSorN]     = useState(20)
  const [mSorStd,    setMSorStd]   = useState(2.0)
  const [mRorPts,    setMRorPts]   = useState(16)
  const [mRorR,      setMRorR]     = useState(0.05)
  const [mPreset,    setMPreset]   = useState('tape_all')
  const [mSatMin,    setMSatMin]   = useState(0.35)
  const [mValMin,    setMValMin]   = useState(0.25)
  const [mPlnDist,   setMPlnDist]  = useState(0.02)
  const [mPlnMax,    setMPlnMax]   = useState(5)
  const [mPlnVert,   setMPlnVert]  = useState(true)
  const [applyRgn,   setApplyRgn]  = useState(false)

  // Region delete
  const [delNotes,   setDelNotes]  = useState('')

  const busy = processing

  function bboxSummary(b: BoundingBox) {
    return [
      `X [${b.min[0].toFixed(2)}, ${b.max[0].toFixed(2)}]`,
      `Y [${b.min[1].toFixed(2)}, ${b.max[1].toFixed(2)}]`,
      `Z [${b.min[2].toFixed(2)}, ${b.max[2].toFixed(2)}]`,
    ].join('  ')
  }

  async function run(fn: () => Promise<void>) {
    setError(null)
    onProcessingStart()
    try { await fn() }
    catch (e: unknown) { setError((e as Error).message); /* processing flag cleared by status poll */ }
  }

  const doAuto = () => run(() => runAutoClean(sessionId, {
    sor_neighbors: sorN, sor_std: sorStd,
    ror_points: rorPts, ror_radius: rorR,
    color_preset: colorPreset, run_color: runClr, run_plane: runPln,
    bbox_filter: applyRgn ? selectedBBox : null,
  }))

  const doManual = () => {
    let params: AlgorithmParams = {}
    if (algo === 'statistical_outlier') params = { nb_neighbors: mSorN, std_ratio: mSorStd }
    else if (algo === 'radius_outlier') params = { nb_points: mRorPts, radius: mRorR }
    else if (algo === 'color_filter')   params = { preset: mPreset, sat_min: mSatMin, val_min: mValMin }
    else if (algo === 'plane_ransac')   params = { distance_threshold: mPlnDist, max_planes: mPlnMax, vertical_only: mPlnVert }
    run(() => runManualClean(sessionId, algo, params, applyRgn ? selectedBBox : null, notes))
  }

  const doDelete = () => {
    if (!selectedBBox) return
    run(() => deleteRegion(
      sessionId,
      selectedBBox.min as [number, number, number],
      selectedBBox.max as [number, number, number],
      delNotes,
    ))
  }

  return (
    <div className="h-full flex flex-col bg-surface overflow-hidden">

      {/* ── Region selection widget ─────────────────────────────────────── */}
      <div className="p-4 border-b border-border">
        <Label>3D Region Selection</Label>

        <button onClick={onToggleSelection}
          className={`w-full flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all mb-2
            ${selectionMode
              ? 'bg-accent text-white ring-1 ring-accent/50'
              : 'bg-surface2 text-text hover:bg-surface3 border border-border'}`}>
          <span className="text-base">{selectionMode ? '✓' : '⊡'}</span>
          {selectionMode ? 'Selection Active — click two points' : 'Select 3D Region'}
        </button>

        {selectedBBox ? (
          <div className="bg-surface2 border border-border rounded-lg p-3 animate-fade-in">
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-[11px] text-muted uppercase tracking-wider">Selected region</span>
              <button onClick={onClearSelection} className="text-[11px] text-dim hover:text-danger transition-colors">
                Clear ✕
              </button>
            </div>
            <div className="text-[11px] text-success font-mono leading-relaxed">
              {bboxSummary(selectedBBox)}
            </div>
          </div>
        ) : selectionMode ? (
          <div className="text-[11px] text-muted bg-surface2 border border-border rounded-lg px-3 py-2">
            Click point 1 on the left panel, then point 2 to define a box.
          </div>
        ) : null}

        {selectedBBox && (
          <label className="flex items-center gap-2 mt-2 text-xs text-muted cursor-pointer hover:text-text transition-colors">
            <input type="checkbox" checked={applyRgn} onChange={e => setApplyRgn(e.target.checked)} />
            Limit next clean to this region only
          </label>
        )}
      </div>

      {/* ── Tabs ───────────────────────────────────────────────────────── */}
      <div className="flex border-b border-border flex-shrink-0">
        {([
          { k: 'auto',   l: 'Auto Clean' },
          { k: 'manual', l: 'Manual' },
          { k: 'region', l: 'Delete Region' },
        ] as { k: Tab; l: string }[]).map(({ k, l }) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex-1 py-2.5 text-xs font-medium transition-colors border-b-2
              ${tab === k
                ? 'border-accent text-accent bg-accent/5'
                : 'border-transparent text-muted hover:text-text'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* ── Tab content ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* AUTO */}
        {tab === 'auto' && <>
          <p className="text-xs text-muted leading-relaxed">
            Runs four algorithms in sequence: outlier removal → colour filter → plane detection → flying points.
          </p>

          <Section title="Statistical Outlier Removal">
            <Param label="Neighbours (k)" value={sorN} min={5} max={60} step={1} decimals={0} onChange={setSorN} />
            <Param label="Std-dev ratio" value={sorStd} min={0.5} max={8} step={0.1} onChange={setSorStd} />
          </Section>

          <Section title="Radius Outlier Removal">
            <Param label="Min neighbours" value={rorPts} min={3} max={32} step={1} decimals={0} onChange={setRorPts} />
            <Param label="Search radius (m)" value={rorR} min={0.01} max={2.0} step={0.01} onChange={setRorR} />
          </Section>

          <Section title="Optional Stages">
            <Toggle label="Colour filter" desc="Remove tape, cones and markers by hue"
              checked={runClr} onChange={setRunClr} />
            {runClr && (
              <select value={colorPreset} onChange={e => setColorPreset(e.target.value)}
                className="w-full bg-surface2 text-text text-xs rounded-lg px-3 py-2 border border-border
                  focus:outline-none focus:border-accent">
                <option value="tape_all">All tape (yellow + red)</option>
                <option value="tape_yellow">Yellow tape only</option>
                <option value="tape_red">Red tape only</option>
                <option value="cone_orange">Orange cones</option>
              </select>
            )}
            <Toggle label="Plane removal" desc="Remove windows, glass walls (RANSAC)"
              checked={runPln} onChange={setRunPln} />
          </Section>

          <div>
            <Label>Analyst notes</Label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
              placeholder="Optional — logged in audit trail"
              className="w-full bg-surface2 text-text text-xs rounded-lg p-2.5 border border-border
                resize-none focus:outline-none focus:border-accent placeholder:text-dim" />
          </div>

          <Btn onClick={doAuto} disabled={busy}>
            {busy ? 'Running…' : 'Run Auto-Clean'}
          </Btn>
        </>}

        {/* MANUAL */}
        {tab === 'manual' && <>
          <div>
            <Label>Algorithm</Label>
            <select value={algo} onChange={e => setAlgo(e.target.value as Algorithm)}
              className="w-full bg-surface2 text-text text-xs rounded-lg px-3 py-2 border border-border
                focus:outline-none focus:border-accent">
              <option value="statistical_outlier">Statistical Outlier Removal</option>
              <option value="radius_outlier">Radius Outlier Removal</option>
              <option value="color_filter">Colour Filter (tape / markers)</option>
              <option value="plane_ransac">Planar Surface Removal (RANSAC)</option>
            </select>
          </div>

          {algo === 'statistical_outlier' && (
            <Section title="Parameters">
              <Param label="Neighbours (k)" value={mSorN} min={5} max={100} step={1} decimals={0} onChange={setMSorN} />
              <Param label="Std-dev ratio" value={mSorStd} min={0.5} max={10} step={0.1} onChange={setMSorStd} />
            </Section>
          )}
          {algo === 'radius_outlier' && (
            <Section title="Parameters">
              <Param label="Min neighbours" value={mRorPts} min={3} max={64} step={1} decimals={0} onChange={setMRorPts} />
              <Param label="Search radius (m)" value={mRorR} min={0.005} max={5.0} step={0.005} onChange={setMRorR} />
            </Section>
          )}
          {algo === 'color_filter' && (
            <Section title="Parameters">
              <div>
                <Label>Colour preset</Label>
                <select value={mPreset} onChange={e => setMPreset(e.target.value)}
                  className="w-full bg-surface2 text-text text-xs rounded-lg px-3 py-2 border border-border
                    focus:outline-none focus:border-accent">
                  <option value="tape_all">All tape (yellow + red)</option>
                  <option value="tape_yellow">Yellow tape</option>
                  <option value="tape_red">Red tape</option>
                  <option value="cone_orange">Orange cones</option>
                </select>
              </div>
              <Param label="Min saturation" value={mSatMin} min={0.1} max={1.0} step={0.05} onChange={setMSatMin} />
              <Param label="Min brightness" value={mValMin} min={0.1} max={1.0} step={0.05} onChange={setMValMin} />
            </Section>
          )}
          {algo === 'plane_ransac' && (
            <Section title="Parameters">
              <Param label="Distance threshold (m)" value={mPlnDist} min={0.005} max={0.5} step={0.005} onChange={setMPlnDist} />
              <Param label="Max planes to remove" value={mPlnMax} min={1} max={20} step={1} decimals={0} onChange={setMPlnMax} />
              <Toggle label="Vertical surfaces only" desc="Targets windows / walls, not floors"
                checked={mPlnVert} onChange={setMPlnVert} />
            </Section>
          )}

          <div>
            <Label>Analyst notes</Label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
              placeholder="Optional — logged in audit trail"
              className="w-full bg-surface2 text-text text-xs rounded-lg p-2.5 border border-border
                resize-none focus:outline-none focus:border-accent placeholder:text-dim" />
          </div>

          <Btn onClick={doManual} disabled={busy}>
            {busy ? 'Running…' : 'Apply Algorithm'}
          </Btn>
        </>}

        {/* REGION DELETE */}
        {tab === 'region' && <>
          <p className="text-xs text-muted leading-relaxed">
            Deletes <strong className="text-text">all</strong> points inside the selected 3D bounding box.
            Use for clearly identifiable objects (tape flags, equipment, markers).
          </p>

          {selectedBBox ? (
            <div className="bg-surface2 border border-border rounded-lg p-3 animate-fade-in">
              <div className="text-[11px] text-muted mb-1.5">Region to delete</div>
              <div className="text-[11px] text-removed font-mono leading-relaxed">
                {bboxSummary(selectedBBox)}
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2 bg-warning-dim border border-warning/20 rounded-lg p-3 text-warning text-xs">
              <span>⚠</span>
              <span>No region selected. Use "Select 3D Region" above first.</span>
            </div>
          )}

          <div>
            <Label>Reason for deletion <span className="text-danger">*</span></Label>
            <textarea value={delNotes} onChange={e => setDelNotes(e.target.value)} rows={4}
              placeholder="Required for audit trail. Describe what is being removed and why.&#10;e.g. Crime scene tape visible between markers A3–A5, no evidentiary value."
              className="w-full bg-surface2 text-text text-xs rounded-lg p-2.5 border border-border
                resize-none focus:outline-none focus:border-accent placeholder:text-dim" />
          </div>

          <Btn onClick={doDelete}
            disabled={busy || !selectedBBox || delNotes.trim().length < 10}
            variant="danger">
            {busy ? 'Deleting…' : 'Delete Selected Region'}
          </Btn>
          {delNotes.trim().length > 0 && delNotes.trim().length < 10 && (
            <p className="text-[11px] text-warning text-center">Reason must be at least 10 characters.</p>
          )}
        </>}
      </div>

      {error && <ErrorBox msg={error} />}
    </div>
  )
}
