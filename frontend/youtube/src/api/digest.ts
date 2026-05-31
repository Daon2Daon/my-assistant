/** YouTube Monitor — 주간 리뷰(Weekly Digest) API 클라이언트 */

const BASE = '/api/youtube'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(detail?.detail ?? resp.statusText)
  }
  if (resp.status === 204) return undefined as T
  return resp.json()
}

// ── 타입 ─────────────────────────────────────────────────────────────────────

export interface DigestTag {
  name: string
  weight: number
  count: number
}

export interface DigestChannel {
  name: string
  count: number
}

export interface DigestListItem {
  digest_pk: number
  period_type: string
  period_weeks: number
  period_start: string
  period_end: string
  category: string | null
  video_count: number
  headline: string | null
  status: string
  created_at: string
}

export interface DigestDetail {
  digest_pk: number | null
  period_type: string
  period_weeks: number
  period_start: string
  period_end: string
  category: string | null
  video_count: number
  headline: string | null
  summary_md: string | null
  telegram_summary: string | null
  sentiment_breakdown: Record<string, number> | null
  top_tags: DigestTag[] | null
  top_channels: DigestChannel[] | null
  model_name: string | null
  token_input: number | null
  token_output: number | null
  cost_usd: number | null
  status: string
  error: string | null
  created_at: string | null
}

export interface PaginatedDigests {
  total: number
  page: number
  page_size: number
  items: DigestListItem[]
}

export interface DigestGenerateResponse {
  success: boolean
  message: string
  created_digest_pks: number[]
  items: DigestDetail[]
}

export interface DigestScheduleItem {
  day_of_week: string
  time: string
}

export interface DigestSettings {
  enabled: boolean
  period_weeks: number
  schedule_times: DigestScheduleItem[]
  telegram_enabled: boolean
  /** 대상 필터 (타입 간 AND, 타입 내 OR). null/빈배열 = 전체 */
  categories: string[] | null
  channel_pks: number[] | null
  tags: string[] | null
}

// ── 다이제스트 API ─────────────────────────────────────────────────────────────

export const digestApi = {
  list: (params: { category?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams()
    if (params.category) q.set('category', params.category)
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    return request<PaginatedDigests>(`/digests?${q}`)
  },

  get: (pk: number) => request<DigestDetail>(`/digests/${pk}`),

  remove: (pk: number) => request<void>(`/digests/${pk}`, { method: 'DELETE' }),

  generate: (body: { period_weeks?: number; categories?: string[]; save?: boolean }) =>
    request<DigestGenerateResponse>('/digests/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

// ── 다이제스트 설정 API ─────────────────────────────────────────────────────────

export const digestSettingsApi = {
  get: () => request<DigestSettings>('/settings/digest'),

  update: (body: Partial<DigestSettings>) =>
    request<DigestSettings>('/settings/digest', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}

// ── 공용 헬퍼 ──────────────────────────────────────────────────────────────────

export const SENTIMENT_KO: Record<string, string> = {
  bullish: '긍정',
  bearish: '부정',
  neutral: '중립',
  mixed: '혼조',
  unknown: '미상',
}

export const DOW_KO: Record<string, string> = {
  mon: '월',
  tue: '화',
  wed: '수',
  thu: '목',
  fri: '금',
  sat: '토',
  sun: '일',
}

export const UNCATEGORIZED = '미분류'

/**
 * 채널 category 문자열을 콤마 기준 토큰으로 분리.
 * 예: '경제, 투자, 재테크' → ['경제', '투자', '재테크']
 * 백엔드 split_category_tokens 와 동일한 규칙.
 */
export function splitCategoryTokens(raw: string | null | undefined): string[] {
  if (!raw) return []
  return raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

/**
 * 채널 목록에서 고유 카테고리 토큰을 추출(콤마 분리, 중복 제거, 정렬).
 */
export function collectCategoryTokens(
  channels: { category?: string | null }[]
): string[] {
  const set = new Set<string>()
  for (const c of channels) {
    for (const tok of splitCategoryTokens(c.category)) set.add(tok)
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'ko'))
}
