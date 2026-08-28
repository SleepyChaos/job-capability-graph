const BASE = '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { signal })
  if (!response.ok) throw new Error(`请求失败（${response.status}）`)
  return (await response.json()) as T
}

export interface RoleListItem {
  role_code: string
  canonical_name: string
  lifecycle_status: string
  latest_version_no: number | null
  latest_approval_status: string | null
  requirement_count: number
  /** 版本数。只有 ≥2 才谈得上能力演变——首版岗位没有可比对象。 */
  version_count: number
  /** 最新一次版本更替产生的变更项数。 */
  change_count: number
  has_comparison_warning: boolean
}

export interface RoleVersionItem {
  version_no: number
  valid_from: string
  valid_to: string | null
  approval_status: string
  evidence_strength: string
  update_summary: string | null
}

export interface RoleRequirementItem {
  technology_code: string
  technology_name: string
  requirement_type: string
  importance: string
  coverage: string | null
  job_count: number
  organization_count: number
  source_count: number
  confidence: string
}

/**
 * 一条能力变更。`change_type` 为 added / removed / modified；
 * modified 时 `change_subtype` 进一步区分 strengthened / weakened。
 */
export interface RoleEvolutionChange {
  technology_code: string
  change_type: string
  change_subtype: string | null
  magnitude: string
  reason: string | null
}

export interface RoleDetail extends RoleListItem {
  definition: string | null
  core_responsibilities: string | null
  versions: RoleVersionItem[]
  requirements: RoleRequirementItem[]
  evolution_changes: RoleEvolutionChange[]
  /** 两版证据量相差过大时的提示；不阻断版本生成，只提醒解读方式。 */
  evolution_warning: string | null
}

export const rolesApi = {
  list(
    params: { evolvedOnly?: boolean; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams()
    if (params.evolvedOnly) query.set('evolved_only', 'true')
    query.set('limit', String(params.limit ?? 200))
    query.set('offset', String(params.offset ?? 0))
    return getJson<{ total: number; items: RoleListItem[] }>(`/job-roles?${query}`, signal)
  },
  detail(roleCode: string, signal?: AbortSignal) {
    return getJson<RoleDetail>(`/job-roles/${encodeURIComponent(roleCode)}`, signal)
  },
}

/** 四种变更的呈现口径。没有变化的能力项不进这张表，留空即可。 */
export const CHANGE_MARKS: Record<string, { mark: string; label: string; fg: string; bg: string }> = {
  added: { mark: '●', label: '新增', fg: '#1f6b3f', bg: '#eaf6ee' },
  removed: { mark: '○', label: '已消失', fg: '#8a3b32', bg: '#fdeeec' },
  strengthened: { mark: '↑', label: '重要度上升', fg: '#1c4d86', bg: '#eaf2fd' },
  weakened: { mark: '↓', label: '重要度下降', fg: '#8a5a11', bg: '#fdf3e3' },
}

export function changeKey(change: RoleEvolutionChange): string {
  if (change.change_type === 'modified') return change.change_subtype ?? 'strengthened'
  return change.change_type
}
