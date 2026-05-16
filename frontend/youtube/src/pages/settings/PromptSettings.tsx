import { useEffect, useState } from 'react'
import { promptApi } from '../../api/client'
import type { PromptSettings } from '../../api/client'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

type SaveState = 'idle' | 'saving' | 'ok' | 'fail'

const PROMPT_HELP = `사용 가능한 변수:
  {channel_name}      채널명
  {published_at_kst}  업로드 일시 (KST)
  {video_url}         유튜브 영상 URL`

export default function PromptSettings() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<PromptSettings | null>(null)

  const [primaryDraft, setPrimaryDraft] = useState('')
  const [fallbackDraft, setFallbackDraft] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveMsg, setSaveMsg] = useState('')
  const [resetConfirm, setResetConfirm] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await promptApi.get()
      setData(res)
      setPrimaryDraft(res.primary_prompt)
      setFallbackDraft(res.fallback_prompt)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSave = async () => {
    setSaveState('saving')
    setSaveMsg('')
    try {
      const res = await promptApi.update({
        primary_prompt: primaryDraft,
        fallback_prompt: fallbackDraft,
      })
      setData(res)
      setSaveState('ok')
      setSaveMsg('저장되었습니다.')
    } catch (e) {
      setSaveState('fail')
      setSaveMsg((e as Error).message)
    }
  }

  const handleReset = async () => {
    if (!resetConfirm) {
      setResetConfirm(true)
      return
    }
    setSaveState('saving')
    setSaveMsg('')
    setResetConfirm(false)
    try {
      const res = await promptApi.reset()
      setData(res)
      setPrimaryDraft(res.primary_prompt)
      setFallbackDraft(res.fallback_prompt)
      setSaveState('ok')
      setSaveMsg('기본값으로 초기화되었습니다.')
    } catch (e) {
      setSaveState('fail')
      setSaveMsg((e as Error).message)
    }
  }

  const isDirty =
    data !== null &&
    (primaryDraft !== data.primary_prompt || fallbackDraft !== data.fallback_prompt)

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">프롬프트</h1>
          <p className="text-sm text-gray-500 mt-1">
            영상 분석 시 LLM에 전달할 기본 프롬프트를 수정합니다.
            버전: <span className="font-mono text-blue-600">{data?.prompt_version}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saveState === 'ok' && (
            <span className="text-sm text-green-600 font-medium">{saveMsg}</span>
          )}
          {saveState === 'fail' && (
            <span className="text-sm text-red-600">{saveMsg}</span>
          )}
          <button
            onClick={handleReset}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              resetConfirm
                ? 'bg-red-600 text-white border-red-600 hover:bg-red-700'
                : 'border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {resetConfirm ? '확인: 초기화' : '기본값으로 초기화'}
          </button>
          {resetConfirm && (
            <button
              onClick={() => setResetConfirm(false)}
              className="px-3 py-1.5 rounded-lg text-sm border border-gray-300 text-gray-600 hover:bg-gray-50"
            >
              취소
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!isDirty || saveState === 'saving'}
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saveState === 'saving' ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>

      {/* 변수 안내 */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <p className="text-sm font-semibold text-blue-700 mb-1">프롬프트 템플릿 변수</p>
        <pre className="text-xs text-blue-600 font-mono whitespace-pre-wrap">{PROMPT_HELP}</pre>
      </div>

      {/* 경로 A 프롬프트 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">경로 A — 기본 프롬프트 (Gemini Native)</h2>
          <p className="text-xs text-gray-500 mt-0.5">Primary 모델에 전달. 영상 파일을 직접 분석합니다.</p>
        </div>
        <textarea
          value={primaryDraft}
          onChange={(e) => {
            setPrimaryDraft(e.target.value)
            if (saveState === 'ok') setSaveState('idle')
          }}
          rows={18}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder="경로 A 프롬프트를 입력하세요..."
          spellCheck={false}
        />
      </div>

      {/* 경로 B 프롬프트 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">경로 B — 폴백 프롬프트 (OpenAI 호환)</h2>
          <p className="text-xs text-gray-500 mt-0.5">경로 A 실패 시 Fallback 모델에 전달. 텍스트 기반 분석입니다.</p>
        </div>
        <textarea
          value={fallbackDraft}
          onChange={(e) => {
            setFallbackDraft(e.target.value)
            if (saveState === 'ok') setSaveState('idle')
          }}
          rows={18}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder="경로 B 프롬프트를 입력하세요..."
          spellCheck={false}
        />
      </div>
    </div>
  )
}
