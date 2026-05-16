import { useEffect, useState } from 'react'
import { dbSettingsApi } from '../../api/settings'
import type { DatabaseSettingsResponse, DatabaseSettingsUpdate } from '../../api/settings'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

type TestState = { status: 'idle' | 'running' | 'ok' | 'fail'; message: string; latency?: number }
type SchemaState = { status: 'idle' | 'running' | 'ok' | 'fail'; message: string }

const SSL_MODES = ['prefer', 'require', 'disable', 'allow', 'verify-ca', 'verify-full']

function PasswordInput({ value, onChange, placeholder }: {
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
      <button
        type="button"
        onClick={() => setShow(!show)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
      >
        {show ? '숨김' : '표시'}
      </button>
    </div>
  )
}

export default function DatabaseSettings() {
  const [data, setData] = useState<DatabaseSettingsResponse | null>(null)
  const [form, setForm] = useState<DatabaseSettingsUpdate>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [test, setTest] = useState<TestState>({ status: 'idle', message: '' })
  const [schema, setSchema] = useState<SchemaState>({ status: 'idle', message: '' })

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await dbSettingsApi.get()
      setData(d)
      setForm({
        host: d.host,
        port: d.port,
        dbname: d.dbname,
        username: d.username,
        password: '',
        schema_name: d.schema_name,
        sslmode: d.sslmode,
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
      const payload: DatabaseSettingsUpdate = { ...form }
      if (!payload.password) delete payload.password
      const updated = await dbSettingsApi.update(payload)
      setData(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTest({ status: 'running', message: '연결 테스트 중...' })
    try {
      const r = await dbSettingsApi.testConnection()
      setTest({
        status: r.success ? 'ok' : 'fail',
        message: r.message,
        latency: r.latency_ms ?? undefined,
      })
    } catch (e) {
      setTest({ status: 'fail', message: (e as Error).message })
    }
  }

  const handleApplySchema = async () => {
    setSchema({ status: 'running', message: '스키마 마이그레이션 적용 중...' })
    try {
      const r = await dbSettingsApi.applySchema()
      setSchema({ status: r.success ? 'ok' : 'fail', message: r.message })
    } catch (e) {
      setSchema({ status: 'fail', message: (e as Error).message })
    }
  }

  const setF = <K extends keyof DatabaseSettingsUpdate>(k: K, v: DatabaseSettingsUpdate[K]) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  const isDirty = JSON.stringify(form) !== JSON.stringify({
    host: data?.host, port: data?.port, dbname: data?.dbname,
    username: data?.username, password: '',
    schema_name: data?.schema_name, sslmode: data?.sslmode,
  })

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">DB</h1>
        {data && (
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${data.is_configured ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
            {data.is_configured ? '설정됨' : '미설정'}
          </span>
        )}
      </div>

      {/* 연결 상태 배너 */}
      {test.status === 'fail' && (
        <div className="rounded-lg bg-red-50 border border-red-300 px-4 py-3 text-red-700 text-sm flex gap-2">
          <span>🔴</span><span>{test.message}</span>
        </div>
      )}
      {test.status === 'ok' && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm flex gap-2">
          <span>🟢</span>
          <span>{test.message}{test.latency != null && ` (${test.latency}ms)`}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="bg-white rounded-xl shadow-sm p-6 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Host */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
            <input
              type="text"
              value={form.host ?? ''}
              onChange={(e) => setF('host', e.target.value)}
              placeholder="localhost"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {/* Port */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
            <input
              type="number"
              value={form.port ?? 5432}
              onChange={(e) => setF('port', Number(e.target.value))}
              min={1} max={65535}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {/* Database */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Database</label>
            <input
              type="text"
              value={form.dbname ?? ''}
              onChange={(e) => setF('dbname', e.target.value)}
              placeholder="youtube_monitor"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {/* Schema */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Schema</label>
            <input
              type="text"
              value={form.schema_name ?? ''}
              onChange={(e) => setF('schema_name', e.target.value)}
              placeholder="youtube"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {/* Username */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              type="text"
              value={form.username ?? ''}
              onChange={(e) => setF('username', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {/* Password */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Password
              {data?.password_masked && (
                <span className="ml-2 text-xs text-gray-400 font-normal">현재: {data.password_masked}</span>
              )}
            </label>
            <PasswordInput
              value={form.password ?? ''}
              onChange={(v) => setF('password', v)}
              placeholder="변경 시에만 입력"
            />
          </div>
          {/* SSL Mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">SSL Mode</label>
            <select
              value={form.sslmode ?? 'prefer'}
              onChange={(e) => setF('sslmode', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {SSL_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>

        {/* 변경 경고 */}
        {isDirty && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
            ⚠️ 저장 후 새로운 데이터는 변경된 DB로 저장됩니다. 기존 데이터는 이전 DB에 남습니다.
          </div>
        )}

        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
            ✅ 저장되었습니다.
          </div>
        )}

        {/* 버튼 그룹 */}
        <div className="flex flex-wrap gap-3 pt-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={test.status === 'running'}
            className="px-4 py-2 border border-blue-300 text-blue-600 rounded-lg text-sm hover:bg-blue-50 disabled:opacity-60"
          >
            {test.status === 'running' ? '테스트 중...' : '연결 테스트'}
          </button>
          <button
            type="button"
            onClick={handleApplySchema}
            disabled={schema.status === 'running'}
            className="px-4 py-2 border border-indigo-300 text-indigo-600 rounded-lg text-sm hover:bg-indigo-50 disabled:opacity-60"
          >
            {schema.status === 'running' ? '적용 중...' : '스키마 적용'}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="ml-auto px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>

        {/* 스키마 적용 결과 */}
        {schema.status !== 'idle' && (
          <div className={`rounded-lg px-4 py-3 text-sm ${schema.status === 'ok' ? 'bg-green-50 text-green-700' : schema.status === 'fail' ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-600'}`}>
            {schema.status === 'running' && '⏳ '}{schema.status === 'ok' && '✅ '}{schema.status === 'fail' && '❌ '}
            {schema.message}
          </div>
        )}
      </form>
    </div>
  )
}
