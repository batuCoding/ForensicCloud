import type {
  SessionStatus,
  AuditEntry,
  AutoCleanParams,
  Algorithm,
  AlgorithmParams,
  BoundingBox,
} from '../types'

const BASE = '/api'

async function checkResponse(res: Response) {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res
}

export async function uploadFile(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  // Use XMLHttpRequest so we can track upload progress for large files
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)

    xhr.open('POST', `${BASE}/upload`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const body = JSON.parse(xhr.responseText)
        resolve(body.session_id)
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(form)
  })
}

export async function getStatus(sessionId: string): Promise<SessionStatus> {
  const res = await checkResponse(await fetch(`${BASE}/process/status/${sessionId}`))
  return res.json()
}

export async function getPreviewBinary(
  sessionId: string,
  which: 'original' | 'current',
): Promise<ArrayBuffer> {
  const res = await checkResponse(
    await fetch(`${BASE}/process/preview/${sessionId}/${which}`)
  )
  return res.arrayBuffer()
}

export async function runAutoClean(
  sessionId: string,
  params: AutoCleanParams,
): Promise<void> {
  await checkResponse(
    await fetch(`${BASE}/process/auto/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })
  )
}

export async function runManualClean(
  sessionId: string,
  algorithm: Algorithm,
  params: AlgorithmParams,
  bboxFilter?: BoundingBox | null,
  notes?: string,
): Promise<void> {
  await checkResponse(
    await fetch(`${BASE}/process/manual/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ algorithm, params, bbox_filter: bboxFilter ?? null, notes: notes ?? '' }),
    })
  )
}

export async function deleteRegion(
  sessionId: string,
  bboxMin: [number, number, number],
  bboxMax: [number, number, number],
  notes?: string,
): Promise<void> {
  await checkResponse(
    await fetch(`${BASE}/process/region-delete/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox_min: bboxMin, bbox_max: bboxMax, notes: notes ?? '' }),
    })
  )
}

export async function startExport(sessionId: string, outputPath?: string): Promise<void> {
  await checkResponse(
    await fetch(`${BASE}/export/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ output_path: outputPath ?? '' }),
    })
  )
}

export function getDownloadUrl(sessionId: string): string {
  return `${BASE}/export/${sessionId}/download`
}

export async function getAuditLog(sessionId: string): Promise<AuditEntry[]> {
  const res = await checkResponse(await fetch(`${BASE}/audit/${sessionId}`))
  const body = await res.json()
  return body.entries ?? []
}

export function getReportUrl(
  sessionId: string,
  caseNumber: string,
  analystName: string,
): string {
  const params = new URLSearchParams({ case_number: caseNumber, analyst_name: analystName })
  return `${BASE}/audit/${sessionId}/report?${params}`
}
