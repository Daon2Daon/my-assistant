/** YouTube Monitor — 알림 발송 설정 API 클라이언트 */

const BASE = '/api/youtube/settings/notification'

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
  return resp.json()
}

// ── 타입 ─────────────────────────────────────────────────────────────────────

export type SendMode = 'immediate' | 'scheduled'

export interface NotificationSettingsResponse {
  telegram_enabled: boolean
  /** 'immediate' | 'scheduled' */
  send_mode: SendMode
  /** 예약 시각 목록 ["HH:MM", ...] */
  scheduled_times: string[]
  wait_between_messages_sec: number
  low_confidence_threshold: number
}

export interface NotificationSettingsUpdate {
  telegram_enabled?: boolean
  send_mode?: SendMode
  scheduled_times?: string[]
  wait_between_messages_sec?: number
  low_confidence_threshold?: number
}

// ── API ───────────────────────────────────────────────────────────────────────

export const notificationApi = {
  get: () => request<NotificationSettingsResponse>(''),
  update: (body: NotificationSettingsUpdate) =>
    request<NotificationSettingsResponse>('', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
