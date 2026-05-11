import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import dayjs from 'dayjs'
import { videoApi } from '../api/client'
import type { VideoDetail as VideoDetailType } from '../api/client'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'
import StatusBadge from '../components/StatusBadge'

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = score >= 0.7 ? 'bg-green-500' : score >= 0.4 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

export default function VideoDetail() {
  const { videoPk } = useParams<{ videoPk: string }>()
  const [video, setVideo] = useState<VideoDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reanalyzing, setReanalyzing] = useState(false)

  const load = async () => {
    if (!videoPk) return
    setLoading(true)
    setError(null)
    try {
      setVideo(await videoApi.get(Number(videoPk)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [videoPk])

  const handleReanalyze = async () => {
    if (!videoPk) return
    setReanalyzing(true)
    try {
      const r = await videoApi.reanalyze(Number(videoPk))
      alert(r.message)
      await load()
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setReanalyzing(false)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!video) return null

  return (
    <div className="space-y-5">
      {/* 상단 네비 */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link to="/youtube/videos" className="hover:text-blue-600">영상 목록</Link>
        <span>/</span>
        <span className="text-gray-700 truncate max-w-xs">{video.title}</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* 좌측: 영상 정보 + 분석 결과 */}
        <div className="xl:col-span-2 space-y-5">
          {/* 영상 헤더 */}
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {video.thumbnail_url && (
              <img src={video.thumbnail_url} alt={video.title} className="w-full aspect-video object-cover" />
            )}
            <div className="p-5 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <h1 className="text-xl font-bold text-gray-900 leading-snug">{video.title}</h1>
                <div className="flex gap-2 shrink-0">
                  <a
                    href={video.video_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 font-medium"
                  >
                    YouTube에서 보기
                  </a>
                  <button
                    onClick={handleReanalyze}
                    disabled={reanalyzing}
                    className="px-3 py-1.5 bg-blue-50 text-blue-600 text-xs rounded-lg hover:bg-blue-100 disabled:opacity-60 font-medium"
                  >
                    {reanalyzing ? '요청 중...' : '재분석'}
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-3 flex-wrap text-xs text-gray-500">
                <StatusBadge status={video.analysis_status} />
                <span>📅 {dayjs(video.published_at).format('YYYY-MM-DD HH:mm')}</span>
                {video.view_count != null && <span>👁 {video.view_count.toLocaleString()}</span>}
                {video.like_count != null && <span>👍 {video.like_count.toLocaleString()}</span>}
                {video.duration_seconds != null && (
                  <span>⏱ {Math.floor(video.duration_seconds / 60)}분 {video.duration_seconds % 60}초</span>
                )}
              </div>

              {/* 태그 */}
              {video.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {video.tags.map((t) => (
                    <Link
                      key={t}
                      to={`/youtube/videos?tag=${encodeURIComponent(t)}`}
                      className="px-2.5 py-0.5 bg-gray-100 hover:bg-blue-50 hover:text-blue-600 text-gray-600 rounded-full text-xs transition-colors"
                    >
                      {t}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 분석 결과 */}
          {video.full_analysis_md ? (
            <div className="bg-white rounded-xl shadow-sm p-5">
              <h2 className="font-semibold text-gray-800 mb-4">상세 분석</h2>
              <article className="prose prose-sm max-w-none text-gray-700">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{video.full_analysis_md}</ReactMarkdown>
              </article>
            </div>
          ) : video.analysis_status === 'pending' || video.analysis_status === 'processing' ? (
            <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
              <div className="text-4xl mb-2">⏳</div>
              <p>분석이 진행 중입니다...</p>
            </div>
          ) : null}
        </div>

        {/* 우측: 요약 + 메타 정보 */}
        <div className="space-y-4">
          {/* 요약 카드 */}
          {(video.headline || video.one_line || video.short_summary_md) && (
            <div className="bg-white rounded-xl shadow-sm p-4 space-y-3">
              <h2 className="font-semibold text-gray-800">요약</h2>
              {video.headline && (
                <p className="font-medium text-gray-900">{video.headline}</p>
              )}
              {video.one_line && (
                <p className="text-sm text-gray-600 italic">{video.one_line}</p>
              )}
              {video.short_summary_md && (
                <article className="prose prose-sm max-w-none text-gray-700">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{video.short_summary_md}</ReactMarkdown>
                </article>
              )}
              {video.bullet_points && video.bullet_points.length > 0 && (
                <ul className="space-y-1">
                  {video.bullet_points.map((bp, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700">
                      <span className="text-blue-400 shrink-0">•</span>
                      <span>{bp}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 분석 메타 */}
          {(video.sentiment || video.confidence_score != null || video.model_name) && (
            <div className="bg-white rounded-xl shadow-sm p-4 space-y-3">
              <h2 className="font-semibold text-gray-800">분석 정보</h2>
              {video.sentiment && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">감성</span>
                  <span className="font-medium text-gray-700">{video.sentiment}</span>
                </div>
              )}
              {video.confidence_score != null && (
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">신뢰도</span>
                  </div>
                  <ConfidenceBar score={video.confidence_score} />
                </div>
              )}
              {video.model_name && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">모델</span>
                  <span className="font-medium text-gray-700 text-xs">{video.model_name}</span>
                </div>
              )}
              {video.analyzed_at && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">분석 시각</span>
                  <span className="text-gray-700 text-xs">{dayjs(video.analyzed_at).format('MM/DD HH:mm')}</span>
                </div>
              )}
            </div>
          )}

          {/* 알림 미리보기 패널 */}
          {video.short_summary_md && (
            <div className="bg-gray-800 rounded-xl p-4 text-gray-100 text-xs font-mono space-y-2">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Telegram 알림 미리보기</p>
              <p className="font-bold">🎬 신규 영상</p>
              {video.headline && <p className="font-semibold">{video.headline}</p>}
              {video.one_line && <p className="italic text-gray-300">{video.one_line}</p>}
              {video.tags.length > 0 && <p className="text-blue-300">🏷 {video.tags.slice(0, 5).join(', ')}</p>}
              <p className="text-blue-400 underline">🔗 영상 보러가기</p>
              {video.notified_at && (
                <p className="text-green-400 mt-2">✅ 발송됨: {dayjs(video.notified_at).format('MM/DD HH:mm')}</p>
              )}
            </div>
          )}

          {/* 오류 정보 */}
          {video.analysis_error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-700 space-y-1">
              <p className="font-semibold">분석 오류</p>
              <p className="font-mono whitespace-pre-wrap">{video.analysis_error}</p>
              <p className="text-gray-500">재시도: {video.retry_count}회</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
