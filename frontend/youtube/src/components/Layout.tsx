import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { healthApi } from '../api/client'

const NAV_ITEMS = [
  { to: '/youtube/', label: '대시보드', icon: '🏠', end: true },
  { to: '/youtube/channels', label: '채널 관리', icon: '📺' },
  { to: '/youtube/videos', label: '영상 목록', icon: '🎬' },
  { to: '/youtube/instant-analyze', label: '추가 영상 분석', icon: '🔍' },
  { to: '/youtube/tags', label: '태그 클라우드', icon: '🏷' },
  { to: '/youtube/jobs', label: '잡 로그', icon: '📋' },
  { to: '/youtube/settings/database', label: 'DB 설정', icon: '🗄' },
  { to: '/youtube/settings/ai-gateway', label: 'AI Gateway', icon: '🤖' },
  { to: '/youtube/settings/runtime', label: '모니터링 설정', icon: '⚙️' },
  { to: '/youtube/settings/prompts', label: '프롬프트 설정', icon: '📝' },
]

type HealthState = 'unknown' | 'ok' | 'error'

export default function Layout() {
  const [dbHealth, setDbHealth] = useState<HealthState>('unknown')
  const [dbMsg, setDbMsg] = useState('')

  const checkHealth = async () => {
    try {
      const res = await healthApi.dbHealth()
      setDbHealth(res.healthy ? 'ok' : 'error')
      setDbMsg(res.message)
    } catch {
      setDbHealth('error')
      setDbMsg('DB 연결 확인 불가')
    }
  }

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* 전체 헬스 경고 배너 */}
      {dbHealth === 'error' && (
        <div className="bg-red-600 text-white text-sm px-4 py-2 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <span>PostgreSQL 연결 오류: {dbMsg}</span>
          <NavLink to="/youtube/settings/database" className="ml-auto underline font-medium">설정 확인</NavLink>
        </div>
      )}

      {/* 상단 헤더 */}
      <header className="bg-blue-700 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
          <a href="/" className="text-white/70 hover:text-white text-sm mr-2">← My Assistant</a>
          <span className="text-xl font-bold">YouTube Monitor</span>
        </div>
      </header>

      <div className="flex flex-1 max-w-7xl mx-auto w-full px-4 py-6 gap-6">
        {/* 사이드바 */}
        <aside className="w-52 shrink-0">
          <nav className="bg-white rounded-xl shadow-sm p-3 space-y-1 sticky top-6">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white font-medium'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* 메인 콘텐츠 */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
