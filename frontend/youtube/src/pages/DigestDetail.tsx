import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { digestApi, SENTIMENT_KO } from '../api/digest'
import type { DigestDetail as DigestDetailType } from '../api/digest'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'

const SENTIMENT_COLOR: Record<string, string> = {
  bullish: 'text-green-700 bg-green-50 border-green-200',
  bearish: 'text-red-700 bg-red-50 border-red-200',
  neutral: 'text-gray-700 bg-gray-50 border-gray-200',
  mixed: 'text-amber-700 bg-amber-50 border-amber-200',
  unknown: 'text-gray-500 bg-gray-50 border-gray-200',
}

export default function DigestDetail() {
  const { digestPk } = useParams()
  const [digest, setDigest] = useState<DigestDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await digestApi.get(Number(digestPk))
      setDigest(d)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [digestPk])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!digest) return null

  const sentiments = Object.entries(digest.sentiment_breakdown ?? {}).filter(([, v]) => v > 0)

  return (
    <div className="space-y-4">
      <Link to="/youtube/digests" className="text-sm text-blue-600 hover:underline">
        ← 주간 리뷰 목록
      </Link>

      {/* 헤더 */}
      <div className="bg-white rounded-xl shadow-sm p-5 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
            {digest.category || '미분류'}
          </span>
          <span className="text-xs text-gray-400">
            {dayjs(digest.period_start).format('YYYY-MM-DD')} ~ {dayjs(digest.period_end).format('MM-DD')}
            {' · '}{digest.period_weeks}주
          </span>
          <span className="text-xs text-gray-400">· 영상 {digest.video_count}건</span>
        </div>
        <h1 className="text-xl font-bold text-gray-900 leading-snug">
          {digest.headline || '(제목 없음)'}
        </h1>

        {/* 감성 분포 */}
        {sentiments.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap pt-1">
            {sentiments.map(([k, v]) => (
              <span
                key={k}
                className={`text-xs px-2 py-0.5 rounded-full border ${SENTIMENT_COLOR[k] ?? SENTIMENT_COLOR.unknown}`}
              >
                {SENTIMENT_KO[k] ?? k} {v}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 본문 (마크다운) */}
      {digest.summary_md && (
        <div className="bg-white rounded-xl shadow-sm p-4 sm:p-5">
          <h2 className="font-semibold text-gray-800 mb-4">리뷰 본문</h2>
          <article className="prose prose-sm max-w-none text-gray-700 break-words overflow-x-auto">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{digest.summary_md}</ReactMarkdown>
          </article>
        </div>
      )}

      {/* 주요 태그 / 채널 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {digest.top_tags && digest.top_tags.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-4">
            <h2 className="font-semibold text-gray-800 mb-3">주요 태그</h2>
            <div className="flex flex-wrap gap-2">
              {digest.top_tags.map((t) => (
                <span
                  key={t.name}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-gray-50 border border-gray-200 rounded-full text-gray-700"
                >
                  {t.name}
                  <span className="text-gray-400">×{t.count}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {digest.top_channels && digest.top_channels.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-4">
            <h2 className="font-semibold text-gray-800 mb-3">주요 채널</h2>
            <ul className="space-y-1.5">
              {digest.top_channels.map((c) => (
                <li key={c.name} className="flex items-center justify-between text-sm text-gray-700">
                  <span className="truncate">{c.name}</span>
                  <span className="text-gray-400 shrink-0 ml-2">{c.count}건</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 텔레그램 요약 / 메타 */}
      <div className="bg-gray-50 rounded-xl border p-4 text-xs text-gray-500 space-y-1">
        {digest.telegram_summary && (
          <p className="text-gray-600 mb-2">
            <span className="font-medium">텔레그램 요약:</span> {digest.telegram_summary}
          </p>
        )}
        {digest.model_name && <p>모델: {digest.model_name}</p>}
        {digest.cost_usd != null && <p>합성 비용: ${digest.cost_usd.toFixed(4)}</p>}
        {(digest.token_input != null || digest.token_output != null) && (
          <p>토큰: 입력 {digest.token_input ?? 0} / 출력 {digest.token_output ?? 0}</p>
        )}
        {digest.created_at && <p>생성: {dayjs(digest.created_at).format('YYYY-MM-DD HH:mm')}</p>}
      </div>
    </div>
  )
}
