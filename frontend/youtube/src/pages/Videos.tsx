import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { videoApi, channelApi, tagApi } from '../api/client'
import type { Video, Channel, Tag } from '../api/client'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'
import StatusBadge from '../components/StatusBadge'
import Pagination from '../components/Pagination'

function formatDuration(sec: number | null) {
  if (!sec) return ''
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

export default function Videos() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [videos, setVideos] = useState<Video[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [tags, setTags] = useState<Tag[]>([])

  const page = Number(searchParams.get('page') ?? 1)
  const channelPk = searchParams.get('channel_pk') ? Number(searchParams.get('channel_pk')) : undefined
  const tagFilter = searchParams.get('tag') ?? undefined
  const statusFilter = searchParams.get('status') ?? undefined
  const PAGE_SIZE = 20

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [r, chs, tgs] = await Promise.all([
        videoApi.list({ channel_pk: channelPk, tag: tagFilter, analysis_status: statusFilter, page, page_size: PAGE_SIZE }),
        channelApi.list(),
        tagApi.list(2, 50),
      ])
      setVideos(r.items)
      setTotal(r.total)
      setChannels(chs)
      setTags(tgs)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [page, channelPk, tagFilter, statusFilter])

  const setFilter = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.set('page', '1')
    setSearchParams(next)
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">영상 목록</h1>

      {/* 필터 바 */}
      <div className="bg-white rounded-xl shadow-sm p-4 flex flex-wrap gap-3">
        <select
          value={channelPk ?? ''}
          onChange={(e) => setFilter('channel_pk', e.target.value || undefined)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">전체 채널</option>
          {channels.map((c) => <option key={c.channel_pk} value={c.channel_pk}>{c.channel_name}</option>)}
        </select>

        <select
          value={statusFilter ?? ''}
          onChange={(e) => setFilter('status', e.target.value || undefined)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">전체 상태</option>
          <option value="pending">대기</option>
          <option value="processing">분석 중</option>
          <option value="done">완료</option>
          <option value="failed">실패</option>
        </select>

        <select
          value={tagFilter ?? ''}
          onChange={(e) => setFilter('tag', e.target.value || undefined)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">전체 태그</option>
          {tags.map((t) => <option key={t.tag_pk} value={t.name}>{t.name} ({t.video_count})</option>)}
        </select>

        {(channelPk || tagFilter || statusFilter) && (
          <button
            onClick={() => setSearchParams({ page: '1' })}
            className="text-sm text-gray-500 hover:text-red-500 underline"
          >
            필터 초기화
          </button>
        )}

        <span className="ml-auto text-sm text-gray-400 self-center">총 {total}개</span>
      </div>

      {/* 영상 목록 */}
      {videos.length === 0 ? (
        <div className="bg-white rounded-xl py-16 text-center text-gray-400 shadow-sm">
          <p className="text-5xl mb-3">🎬</p>
          <p>조건에 맞는 영상이 없습니다.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {videos.map((v) => (
            <Link
              key={v.video_pk}
              to={`/youtube/videos/${v.video_pk}`}
              className="bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow flex gap-4 p-3"
            >
              <div className="relative shrink-0">
                {v.thumbnail_url ? (
                  <img src={v.thumbnail_url} alt={v.title} className="w-40 aspect-video rounded-lg object-cover" />
                ) : (
                  <div className="w-40 aspect-video rounded-lg bg-gray-100 flex items-center justify-center text-2xl">🎬</div>
                )}
                {v.duration_seconds && (
                  <span className="absolute bottom-1 right-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
                    {formatDuration(v.duration_seconds)}
                  </span>
                )}
              </div>
                <div className="flex-1 min-w-0 py-1 space-y-1.5">
                <p className="font-medium text-gray-900 line-clamp-2 text-sm leading-snug">{v.title}</p>
                {v.summary?.one_line && (
                  <p className="text-xs text-gray-500 line-clamp-1">{v.summary.one_line}</p>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  <StatusBadge status={v.analysis_status} />
                  {v.source_channel_name && (
                    <span className="text-xs text-purple-600 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">
                      추가 · {v.source_channel_name}
                    </span>
                  )}
                  {v.notified_at && (
                    <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">알림 발송</span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span>📅 {dayjs(v.published_at).format('YYYY-MM-DD HH:mm')}</span>
                  {v.view_count != null && <span>👁 {v.view_count.toLocaleString()}</span>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={(p) => {
        const next = new URLSearchParams(searchParams)
        next.set('page', String(p))
        setSearchParams(next)
      }} />
    </div>
  )
}
