import { useEffect, useState } from 'react'
import { runtimeApi } from '../../api/settings'
import type { RuntimeSettingsResponse, RuntimeSettingsUpdate } from '../../api/settings'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

function SecretInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm pr-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs">
        {show ? '숨김' : '표시'}
      </button>
    </div>
  )
}

function ToggleSwitch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-gray-300'}`}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
      </button>
      <span className="text-sm text-gray-700">{label}</span>
    </label>
  )
}

function SliderField({ label, value, onChange, min, max, step = 1, format }: {
  label: string; value: number; onChange: (v: number) => void;
  min: number; max: number; step?: number; format?: (v: number) => string
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <span className="text-sm font-semibold text-blue-600 w-16 text-right">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-blue-600"
      />
      <div className="flex justify-between text-xs text-gray-400 mt-0.5">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  )
}

export default function RuntimeSettings() {
  const [data, setData] = useState<RuntimeSettingsResponse | null>(null)
  const [form, setForm] = useState<RuntimeSettingsUpdate & { youtube_api_key: string }>({
    youtube_api_key: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await runtimeApi.get()
      setData(d)
      setForm({
        master_interval_min: d.master_interval_min,
        default_channel_interval_min: d.default_channel_interval_min,
        youtube_api_key: '',
        youtube_daily_quota: d.youtube_daily_quota,
        window_hours: d.window_hours,
        max_concurrent_channels: d.max_concurrent_channels,
        max_concurrent_analyses: d.max_concurrent_analyses,
        telegram_enabled: d.telegram_enabled,
        wait_between_messages_sec: d.wait_between_messages_sec,
        low_confidence_threshold: d.low_confidence_threshold,
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      const { youtube_api_key, ...rest } = form
      const payload: RuntimeSettingsUpdate = { ...rest }
      if (youtube_api_key) payload.youtube_api_key = youtube_api_key
      const updated = await runtimeApi.update(payload)
      setData(updated)
      setSaved(true)
      setSaveMessage('저장되었습니다. 마스터 폴링 잡 주기가 즉시 반영됩니다.')
      setTimeout(() => setSaved(false), 4000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const setF = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">폴링 / 알림 설정</h1>
      <p className="text-sm text-gray-500">YouTube 폴링 주기, API 할당량, Telegram 알림 옵션을 설정합니다.</p>

      <form onSubmit={handleSave} className="space-y-5">
        {/* YouTube API 설정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">YouTube API</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                YouTube API Key
                {data?.youtube_api_key_masked && (
                  <span className="ml-2 text-xs text-gray-400 font-normal">현재: {data.youtube_api_key_masked}</span>
                )}
              </label>
              <SecretInput
                value={form.youtube_api_key ?? ''}
                onChange={(v) => setF('youtube_api_key', v)}
                placeholder="변경 시에만 입력"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">일일 쿼터 한도</label>
              <input
                type="number" min={100} max={1000000} step={100}
                value={form.youtube_daily_quota ?? 10000}
                onChange={(e) => setF('youtube_daily_quota', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* 폴링 설정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">폴링 설정</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Master 폴링 주기 (분)
              </label>
              <input
                type="number" min={1} max={60}
                value={form.master_interval_min ?? 12}
                onChange={(e) => setF('master_interval_min', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">마스터 스케줄러가 채널 목록을 확인하는 주기</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                기본 채널 폴링 주기 (분)
              </label>
              <input
                type="number" min={10} max={10080}
                value={form.default_channel_interval_min ?? 720}
                onChange={(e) => setF('default_channel_interval_min', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">채널별 설정이 없을 때 적용되는 기본값</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                신규 영상 탐색 윈도우 (시간)
              </label>
              <input
                type="number" min={1} max={168}
                value={form.window_hours ?? 24}
                onChange={(e) => setF('window_hours', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">이 시간 이내에 업로드된 영상만 신규로 처리</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
            <SliderField
              label="채널 동시성"
              value={form.max_concurrent_channels ?? 5}
              onChange={(v) => setF('max_concurrent_channels', v)}
              min={1} max={10}
              format={(v) => `${v}개`}
            />
            <SliderField
              label="분석 동시성"
              value={form.max_concurrent_analyses ?? 3}
              onChange={(v) => setF('max_concurrent_analyses', v)}
              min={1} max={10}
              format={(v) => `${v}개`}
            />
          </div>
        </div>

        {/* 알림 설정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">Telegram 알림 설정</h2>

          <ToggleSwitch
            checked={form.telegram_enabled ?? true}
            onChange={(v) => setF('telegram_enabled', v)}
            label="Telegram 알림 활성화"
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                채널 간 대기 시간 (초)
              </label>
              <input
                type="number" min={0} max={120}
                value={form.wait_between_messages_sec ?? 30}
                onChange={(e) => setF('wait_between_messages_sec', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">Telegram 스팸 방지용 배치 발송 간격</p>
            </div>
            <SliderField
              label="저신뢰도 임계값"
              value={form.low_confidence_threshold ?? 0.5}
              onChange={(v) => setF('low_confidence_threshold', v)}
              min={0} max={1} step={0.05}
              format={(v) => `${Math.round(v * 100)}%`}
            />
          </div>
          <p className="text-xs text-gray-400">
            신뢰도가 임계값 미만인 분석 결과에는 알림 메시지에 ⚠️ 저신뢰도 배지가 표시됩니다.
          </p>
        </div>

        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
            ✅ {saveMessage}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </form>
    </div>
  )
}
