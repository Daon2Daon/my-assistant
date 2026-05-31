import { useEffect, useState } from 'react'
import { digestSettingsApi, DOW_KO, collectCategoryTokens } from '../../api/digest'
import type { DigestSettings as DigestSettingsType, DigestScheduleItem } from '../../api/digest'
import { channelApi, tagApi } from '../../api/client'
import type { Channel, Tag } from '../../api/client'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

const DOW_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

function ToggleSwitch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  description?: string
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`mt-0.5 relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-blue-600' : 'bg-gray-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
      <div>
        <span className="text-sm text-gray-700 font-medium">{label}</span>
        {description && <p className="text-xs text-gray-400 mt-0.5">{description}</p>}
      </div>
    </label>
  )
}

const isValidTime = (t: string) => /^([01]?\d|2[0-3]):[0-5]\d$/.test(t)

function sortSchedule(items: DigestScheduleItem[]): DigestScheduleItem[] {
  return [...items].sort((a, b) => {
    const da = DOW_ORDER.indexOf(a.day_of_week)
    const db = DOW_ORDER.indexOf(b.day_of_week)
    if (da !== db) return da - db
    return a.time.localeCompare(b.time)
  })
}

// ── 예약 일정(요일 + 시각) 편집기 ──────────────────────────────────────────────

function ScheduleEditor({
  items,
  onChange,
}: {
  items: DigestScheduleItem[]
  onChange: (v: DigestScheduleItem[]) => void
}) {
  const [day, setDay] = useState('sun')
  const [time, setTime] = useState('')
  const [err, setErr] = useState('')

  const handleAdd = () => {
    if (!time) {
      setErr('시각을 입력하세요.')
      return
    }
    if (!isValidTime(time)) {
      setErr('HH:MM 형식(24시간제)으로 입력하세요.')
      return
    }
    if (items.some((it) => it.day_of_week === day && it.time === time)) {
      setErr('이미 등록된 일정입니다.')
      return
    }
    if (items.length >= 14) {
      setErr('최대 14개까지 등록할 수 있습니다.')
      return
    }
    onChange(sortSchedule([...items, { day_of_week: day, time }]))
    setTime('')
    setErr('')
  }

  const handleRemove = (it: DigestScheduleItem) => {
    onChange(items.filter((x) => !(x.day_of_week === it.day_of_week && x.time === it.time)))
  }

  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="text-sm text-gray-400 italic">등록된 발송 일정이 없습니다.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((it) => (
            <span
              key={`${it.day_of_week}-${it.time}`}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-50 border border-blue-200 rounded-full text-sm font-medium text-blue-700"
            >
              {DOW_KO[it.day_of_week] ?? it.day_of_week} {it.time}
              <button
                type="button"
                onClick={() => handleRemove(it)}
                className="text-blue-400 hover:text-red-500 transition-colors leading-none"
                aria-label="삭제"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2 items-start flex-wrap">
        <select
          value={day}
          onChange={(e) => {
            setDay(e.target.value)
            setErr('')
          }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {DOW_ORDER.map((d) => (
            <option key={d} value={d}>{DOW_KO[d]}요일</option>
          ))}
        </select>
        <input
          type="time"
          value={time}
          onChange={(e) => {
            setTime(e.target.value)
            setErr('')
          }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={items.length >= 14}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
        >
          추가
        </button>
      </div>
      {err && <p className="text-xs text-red-500">{err}</p>}
      <p className="text-xs text-gray-400">
        지정한 요일·시각(KST)마다 주간 리뷰를 생성하고 텔레그램으로 발송합니다. 최대 14개까지 등록할 수 있습니다.
      </p>
    </div>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────────────────────

export default function DigestSettings() {
  const [data, setData] = useState<DigestSettingsType | null>(null)
  const [form, setForm] = useState<DigestSettingsType | null>(null)
  const [knownCategories, setKnownCategories] = useState<string[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, chs, tgs] = await Promise.all([
        digestSettingsApi.get(),
        channelApi.list().catch(() => []),
        tagApi.list(2, 100).catch(() => []),
      ])
      setData(d)
      setForm(d)
      setChannels(chs)
      setTags(tgs)
      // 채널 category 문자열을 콤마 토큰으로 펼쳐 고유 목록 생성
      setKnownCategories(collectCategoryTokens(chs))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const setF = <K extends keyof DigestSettingsType>(k: K, v: DigestSettingsType[K]) =>
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev))

  const toggleCategory = (cat: string) => {
    if (!form) return
    const current = form.categories ?? []
    const next = current.includes(cat)
      ? current.filter((c) => c !== cat)
      : [...current, cat]
    setF('categories', next.length > 0 ? next : null)
  }

  const toggleChannel = (pk: number) => {
    if (!form) return
    const current = form.channel_pks ?? []
    const next = current.includes(pk)
      ? current.filter((c) => c !== pk)
      : [...current, pk]
    setF('channel_pks', next.length > 0 ? next : null)
  }

  const toggleTag = (name: string) => {
    if (!form) return
    const current = form.tags ?? []
    const next = current.includes(name)
      ? current.filter((t) => t !== name)
      : [...current, name]
    setF('tags', next.length > 0 ? next : null)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    setSaved(false)
    try {
      const updated = await digestSettingsApi.update({
        enabled: form.enabled,
        period_weeks: form.period_weeks,
        schedule_times: form.schedule_times,
        telegram_enabled: form.telegram_enabled,
        categories: form.categories ?? [],
        channel_pks: form.channel_pks ?? [],
        tags: form.tags ?? [],
      })
      setData(updated)
      setForm(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 4000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!form) return null

  const selectedCats = form.categories ?? []
  const selectedChannels = form.channel_pks ?? []
  const selectedTags = form.tags ?? []

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">주간 리뷰</h1>
      <p className="text-sm text-gray-500">
        일정 기간의 분석 완료 영상을 카테고리별로 묶어 리뷰를 생성하고, 지정한 일정에 텔레그램으로 발송합니다.
      </p>

      <form onSubmit={handleSave} className="space-y-5">
        {/* 기본 설정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">기본 설정</h2>

          <ToggleSwitch
            checked={form.enabled}
            onChange={(v) => setF('enabled', v)}
            label="주간 리뷰 자동 생성 활성화"
            description="비활성화하면 예약 일정이 있어도 자동 생성·발송하지 않습니다."
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              리뷰 기간 (주)
            </label>
            <input
              type="number"
              min={1}
              max={8}
              value={form.period_weeks}
              onChange={(e) => setF('period_weeks', Number(e.target.value))}
              className="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-400 mt-1">
              발송 시점 기준 최근 N주간의 영상을 집계합니다. (1~8주)
            </p>
          </div>

          <ToggleSwitch
            checked={form.telegram_enabled}
            onChange={(v) => setF('telegram_enabled', v)}
            label="텔레그램 발송"
            description="끄면 리뷰는 생성·저장되지만 텔레그램으로는 발송하지 않습니다."
          />
        </div>

        {/* 발송 일정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">발송 일정</h2>
          <ScheduleEditor
            items={form.schedule_times}
            onChange={(v) => setF('schedule_times', v)}
          />
          {form.enabled && form.schedule_times.length === 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-xs">
              활성화 상태이지만 발송 일정이 없습니다. 최소 1개 이상 등록해야 자동 생성·발송됩니다.
            </div>
          )}
        </div>

        {/* 대상 필터 안내 */}
        <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-xs">
          대상 필터(카테고리·채널·태그)는 <b>서로 다른 종류끼리는 모두 만족(AND)</b>,
          <b> 같은 종류 안에서는 하나라도 해당(OR)</b>하는 영상을 집계합니다.
          아무것도 선택하지 않으면 전체 영상을 대상으로 합니다. 평소에는 비워 두고, 특정 주제만 보고 싶을 때 태그를 선택하세요.
        </div>

        {/* 대상 카테고리 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-3">
          <h2 className="font-semibold text-gray-800 border-b pb-2">대상 카테고리</h2>
          {knownCategories.length === 0 ? (
            <p className="text-sm text-gray-400">
              채널에 지정된 카테고리가 없습니다. 채널 관리에서 카테고리를 지정하면 여기에 표시됩니다.
              (선택 없음 = 모든 영상 통합 리뷰)
            </p>
          ) : (
            <>
              <p className="text-xs text-gray-400">
                채널 카테고리를 콤마로 분리한 개별 항목입니다. 선택하지 않으면 카테고리 구분 없이
                모든 영상을 하나의 리뷰로 통합합니다.
              </p>
              <div className="flex flex-wrap gap-2">
                {knownCategories.map((cat) => {
                  const active = selectedCats.includes(cat)
                  return (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => toggleCategory(cat)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                      }`}
                    >
                      {cat}
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-gray-500">
                현재 대상: {selectedCats.length > 0 ? selectedCats.join(', ') : '전체'}
              </p>
            </>
          )}
        </div>

        {/* 대상 채널 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-3">
          <h2 className="font-semibold text-gray-800 border-b pb-2">대상 채널</h2>
          {channels.length === 0 ? (
            <p className="text-sm text-gray-400">등록된 채널이 없습니다. (선택 없음 = 전체 채널 대상)</p>
          ) : (
            <>
              <p className="text-xs text-gray-400">선택하지 않으면 전체 채널을 대상으로 합니다.</p>
              <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
                {channels.map((ch) => {
                  const active = selectedChannels.includes(ch.channel_pk)
                  return (
                    <button
                      key={ch.channel_pk}
                      type="button"
                      onClick={() => toggleChannel(ch.channel_pk)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                      }`}
                    >
                      {ch.channel_name}
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-gray-500">
                현재 대상: {selectedChannels.length > 0 ? `${selectedChannels.length}개 채널` : '전체'}
              </p>
            </>
          )}
        </div>

        {/* 대상 태그 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-3">
          <h2 className="font-semibold text-gray-800 border-b pb-2">대상 태그</h2>
          {tags.length === 0 ? (
            <p className="text-sm text-gray-400">사용 가능한 태그가 없습니다. (선택 없음 = 전체 대상)</p>
          ) : (
            <>
              <p className="text-xs text-gray-400">
                특정 주제만 분석하고 싶을 때 선택하세요. 선택한 태그 중 하나라도 달린 영상이 포함됩니다.
              </p>
              <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
                {tags.map((t) => {
                  const active = selectedTags.includes(t.name)
                  return (
                    <button
                      key={t.tag_pk}
                      type="button"
                      onClick={() => toggleTag(t.name)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                      }`}
                    >
                      {t.name} <span className={active ? 'text-blue-200' : 'text-gray-400'}>({t.video_count})</span>
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-gray-500">
                현재 대상: {selectedTags.length > 0 ? selectedTags.join(', ') : '전체'}
              </p>
            </>
          )}
        </div>

        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
            ✅ 저장되었습니다. 발송 일정이 즉시 반영됩니다.
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

      {/* 현재 설정 요약 */}
      {data && (
        <div className="bg-gray-50 rounded-xl border p-4 text-xs text-gray-500 space-y-1">
          <p className="font-medium text-gray-600 mb-2">현재 적용 중인 설정</p>
          <p>자동 생성: {data.enabled ? '활성' : '비활성'}</p>
          <p>리뷰 기간: 최근 {data.period_weeks}주</p>
          <p>텔레그램 발송: {data.telegram_enabled ? '활성' : '비활성'}</p>
          <p>
            발송 일정:{' '}
            {data.schedule_times.length > 0
              ? data.schedule_times
                  .map((it) => `${DOW_KO[it.day_of_week] ?? it.day_of_week} ${it.time}`)
                  .join(', ')
              : '(없음)'}
          </p>
          <p>대상 카테고리: {data.categories && data.categories.length > 0 ? data.categories.join(', ') : '전체'}</p>
          <p>대상 채널: {data.channel_pks && data.channel_pks.length > 0 ? `${data.channel_pks.length}개` : '전체'}</p>
          <p>대상 태그: {data.tags && data.tags.length > 0 ? data.tags.join(', ') : '전체'}</p>
        </div>
      )}
    </div>
  )
}
