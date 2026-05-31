import { useEffect, useState } from 'react'
import { promptApi } from '../../api/client'
import type { PromptSettings } from '../../api/client'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

type SaveState = 'idle' | 'saving' | 'ok' | 'fail'

const ANALYSIS_HELP = `사용 가능한 변수:
  {channel_name}      채널명
  {published_at_kst}  업로드 일시 (KST)
  {video_url}         유튜브 영상 URL
  {today}             오늘 날짜 (KST)`

const DIGEST_HELP = `사용 가능한 변수:
  {category}          대상 라벨 (전체 또는 선택 카테고리)
  {period_label}      집계 기간 (예: 2026-05-24 ~ 05-31)
  {video_count}       분석 영상 수
  {sentiment_summary} 감성 분포 요약
  {top_tags}          주요 태그 목록
  {videos_block}      영상별 자료 블록`

export default function PromptSettings() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<PromptSettings | null>(null)

  const [analysisDraft, setAnalysisDraft] = useState('')
  const [digestDraft, setDigestDraft] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveMsg, setSaveMsg] = useState('')
  const [resetConfirm, setResetConfirm] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await promptApi.get()
      setData(res)
      setAnalysisDraft(res.analysis_prompt)
      setDigestDraft(res.digest_prompt)
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
        analysis_prompt: analysisDraft,
        digest_prompt: digestDraft,
      })
      setData(res)
      setAnalysisDraft(res.analysis_prompt)
      setDigestDraft(res.digest_prompt)
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
      setAnalysisDraft(res.analysis_prompt)
      setDigestDraft(res.digest_prompt)
      setSaveState('ok')
      setSaveMsg('기본값으로 초기화되었습니다.')
    } catch (e) {
      setSaveState('fail')
      setSaveMsg((e as Error).message)
    }
  }

  const isDirty =
    data !== null &&
    (analysisDraft !== data.analysis_prompt || digestDraft !== data.digest_prompt)

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">프롬프트</h1>
          <p className="text-sm text-gray-500 mt-1">
            영상 분석과 주간 리뷰 합성에 사용할 프롬프트를 수정합니다.
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
            {resetConfirm ? '확인: 전체 초기화' : '기본값으로 초기화'}
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

      {/* 영상 분석 프롬프트 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">영상 분석 프롬프트</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            신규 영상 분석 시 LLM에 전달합니다. (Gemini Native / OpenAI 호환 경로 공통)
          </p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <pre className="text-xs text-blue-600 font-mono whitespace-pre-wrap">{ANALYSIS_HELP}</pre>
        </div>
        <textarea
          value={analysisDraft}
          onChange={(e) => {
            setAnalysisDraft(e.target.value)
            if (saveState === 'ok') setSaveState('idle')
          }}
          rows={18}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder="영상 분석 프롬프트를 입력하세요..."
          spellCheck={false}
        />
      </div>

      {/* 주간 리뷰 프롬프트 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">주간 리뷰 프롬프트</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            주간 리뷰 합성 시 LLM에 전달합니다. 출력은 headline / summary_md / telegram_summary JSON 형식이어야 합니다.
          </p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <pre className="text-xs text-blue-600 font-mono whitespace-pre-wrap">{DIGEST_HELP}</pre>
        </div>
        <textarea
          value={digestDraft}
          onChange={(e) => {
            setDigestDraft(e.target.value)
            if (saveState === 'ok') setSaveState('idle')
          }}
          rows={18}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder="주간 리뷰 프롬프트를 입력하세요..."
          spellCheck={false}
        />
      </div>
    </div>
  )
}
