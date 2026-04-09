export interface SessionStatus {
  status: 'idle' | 'uploading' | 'loading' | 'ready' | 'processing' | 'exporting' | 'error'
  status_message: string
  progress: number
  original_points: number
  current_points: number
  bbox: { min: [number, number, number]; max: [number, number, number] }
  center: [number, number, number]
  has_colors: boolean
  original_filename: string
  original_hash: string
  scan_count: number
}

export interface BoundingBox {
  min: [number, number, number] | number[]
  max: [number, number, number] | number[]
}

export interface AuditEntry {
  id: number
  session_id: string
  timestamp: string
  operation_type: string
  algorithm: string
  params: Record<string, unknown>
  points_before: number
  points_removed: number
  points_after: number
  removed_bbox: { min: number[]; max: number[] }
  region_bbox?: { min: number[]; max: number[] } | null
  operator_notes: string
}

export type Algorithm =
  | 'statistical_outlier'
  | 'radius_outlier'
  | 'color_filter'
  | 'plane_ransac'

export interface AlgorithmParams {
  // SOR
  nb_neighbors?: number
  std_ratio?: number
  // ROR
  nb_points?: number
  radius?: number
  // Color
  preset?: string
  sat_min?: number
  val_min?: number
  // Plane
  distance_threshold?: number
  max_planes?: number
  vertical_only?: boolean
}

export interface AutoCleanParams {
  sor_neighbors: number
  sor_std: number
  ror_points: number
  ror_radius: number
  color_preset: string
  run_color: boolean
  run_plane: boolean
  bbox_filter?: BoundingBox | null
}
