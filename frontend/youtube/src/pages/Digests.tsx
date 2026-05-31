import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { digestApi } from '../api/digest'
import type { DigestListItem } from '../api/digest'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 20

function periodLabel(start: string, end: string) {
  return `${dayjs(start).format('YYYY-MM-DD')} ~ ${dayjs(end).format('MM-DD')}`
}

export default function Digests() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<DigestListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [generating, setGenerating] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DigestListItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const page = Number(searchParams.get('page') ?? 1)
  const categoryFilter = searchParams.get('category') ?? undefined

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await digestApi.list({ category: categoryFilter, page, page_size: PAGE_SIZE })
      setItems(r.items)
      setTotal(r.total)
      // 필터 드롭다운: 실제 저장된 다이제스트의 라벨로 채운다 (전체/카테고리명).
      // 현재 페이지 항목 기준으로 보강하되, 기존 선택값은 유지.
      setCategories((prev) => {
        const set = new Set(prev)
        for (const it of r.items) {
          if (it.category) set.add(it.category)
        }
        if (categoryFilter) set.add(categoryFilter)
        return Array.from(set).sort((a, b) => a.localeCompare(b, 'ko'))
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [page, categoryFilter])

  const setFilter = (value: string | undefined) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set('category', value)
    else next.delete('category')
    next.set('page', '1')
    setSearchParams(next)
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setToast(null)
    try {
      const res = await digestApi.generate({ save: true })
      setToast(res.message)
      const next = new URLSearchParams(searchParams)
      next.set('page', '1')
      setSearchParams(next)
      await load()
    } catch (e) {
      setToast(`생성 실패: ${(e as Error).message}`)
    } finally {
      setGenerating(false)
      setTimeout(() => setToast(null), 6000)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await digestApi.remove(deleteTarget.digest_pk)
      setDeleteTarget(null)
      // 마지막 페이지에서 1건 삭제 후 페이지가 비면 이전 페이지로 이동
      if (items.length === 1 && page > 1) {
        const next = new URLSearchParams(searchParams)
        next.set('page', String(page - 1))
        setSearchParams(next)
      } else {
        await load()
      }
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`)
    } finally {
      setDeleting(false)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-2xl font-bold text-gray-900">주간 리뷰</h1>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
        >
          {generating ? '생성 중...' : '지금 생성'}
        </button>
      </div>
      <p className="text-sm text-gray-500">
        설정된 기간의 분석 완료 영상을 카테고리별로 묶어 합성한 리뷰입니다. 발송 일정·기간은
        <Link to="/youtube/settings/digest" className="text-blue-600 underline ml-1">설정 → 주간 리뷰</Link>
        에서 변경할 수 있습니다.
      </p>

      {toast && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
          {toast}
        </div>
      )}

      {/* 필터 바 */}
      <div className="bg-white rounded-xl shadow-sm p-4 flex flex-wrap gap-3 items-center">
        <select
          value={categoryFilter ?? ''}
          onChange={(e) => setFilter(e.target.value || undefined)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">전체 카테고리</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        {categoryFilter && (
          <button
            onClick={() => setFilter(undefined)}
            className="text-sm text-gray-500 hover:text-red-500 underline"
          >
            필터 초기화
          </button>
        )}
        <span className="ml-auto text-sm text-gray-400">총 {total}개</span>
      </div>

      {/* 목록 */}
      {items.length === 0 ? (
        <div className="bg-white rounded-xl py-16 text-center text-gray-400 shadow-sm">
          <p className="text-5xl mb-3">📊</p>
          <p>아직 생성된 주간 리뷰가 없습니다.</p>
          <p className="text-sm mt-1">상단의 &quot;지금 생성&quot; 버튼으로 즉시 생성할 수 있습니다.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((d) => (
            <div
              key={d.digest_pk}
              className="bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow flex gap-3 p-4"
            >
              {/* 클릭 영역: 상세 페이지 이동 */}
              <Link
                to={`/youtube/digests/${d.digest_pk}`}
                className="flex-1 min-w-0"
              >
                <div className="flex items-center gap-2 flex-wrap mb-1.5">
                  <span className="text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                    {d.category || '미분류'}
                  </span>
                  <span className="text-xs text-gray-400">{periodLabel(d.period_start, d.period_end)}</span>
                  <span className="text-xs text-gray-400">· 영상 {d.video_count}건</span>
                  {d.status !== 'done' && (
                    <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                      {d.status}
                    </span>
                  )}
                </div>
                <p className="font-medium text-gray-900 leading-snug">
                  {d.headline || '(제목 없음)'}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  생성 {dayjs(d.created_at).format('YYYY-MM-DD HH:mm')}
                </p>
              </Link>

              {/* 삭제 버튼 */}
              <div className="flex items-center shrink-0">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(d)}
                  className="px-2.5 py-1.5 text-xs rounded bg-red-50 text-red-500 hover:bg-red-100 transition-colors"
                  title="삭제"
                >
                  삭제
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onChange={(p) => {
          const next = new URLSearchParams(searchParams)
          next.set('page', String(p))
          setSearchParams(next)
        }}
      />

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full space-y-4">
            <h3 className="font-bold text-gray-900">주간 리뷰 삭제</h3>
            <p className="text-sm text-gray-600">
              아래 리뷰를 삭제합니다. 복구할 수 없습니다.
            </p>
            <div className="bg-gray-50 rounded-lg px-4 py-3 text-sm text-gray-700 space-y-1">
              <p>
                <span className="text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full mr-1">
                  {deleteTarget.category || '미분류'}
                </span>
                {periodLabel(deleteTarget.period_start, deleteTarget.period_end)}
              </p>
              <p className="font-medium line-clamp-2">{deleteTarget.headline || '(제목 없음)'}</p>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? '삭제 중...' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
