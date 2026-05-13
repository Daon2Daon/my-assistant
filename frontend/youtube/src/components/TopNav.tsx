import { useState } from 'react'
import { useLocation } from 'react-router-dom'

/** `app/templates/base.html` 상단 네비와 동일한 항목·순서 */
const NAV_ITEMS: {
  href: string
  label: string
  icon: string
  /** 현재 경로에서 이 메뉴를 active로 표시할지 */
  isActive: (pathname: string) => boolean
}[] = [
  { href: '/', label: 'Home', icon: 'bi-house', isActive: (p) => p === '/' || p === '' },
  { href: '/reminders', label: 'Reminders', icon: 'bi-bell', isActive: (p) => p.startsWith('/reminders') },
  { href: '/finance', label: 'Finance', icon: 'bi-graph-up', isActive: (p) => p.startsWith('/finance') },
  { href: '/chartbot', label: 'Chartbot', icon: 'bi-bar-chart-line', isActive: (p) => p.startsWith('/chartbot') },
  { href: '/youtube', label: 'YouTube', icon: 'bi-youtube', isActive: (p) => p.startsWith('/youtube') },
  { href: '/calendar', label: 'Calendar', icon: 'bi-calendar-event', isActive: (p) => p.startsWith('/calendar') },
  { href: '/weather', label: 'Weather', icon: 'bi-cloud-sun', isActive: (p) => p.startsWith('/weather') },
  { href: '/logs', label: 'Logs', icon: 'bi-journal-text', isActive: (p) => p.startsWith('/logs') },
  { href: '/settings', label: 'Settings', icon: 'bi-gear', isActive: (p) => p.startsWith('/settings') },
]

/**
 * My Assistant 전역 네비게이션 (Bootstrap primary 톤에 맞춘 Tailwind 구현).
 * `base.html` 의 navbar 와 동일한 링크를 제공한다.
 */
export default function TopNav() {
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <nav className="relative bg-[#0d6efd] text-white shadow-md">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          <a href="/" className="flex items-center gap-2 font-semibold text-white no-underline hover:text-white shrink-0">
            <i className="bi bi-chat-dots-fill" aria-hidden />
            My Assistant
          </a>

          <button
            type="button"
            className="md:hidden inline-flex items-center justify-center p-2 rounded border border-white/40 text-white"
            aria-expanded={menuOpen}
            aria-label="메뉴 열기"
            onClick={() => setMenuOpen((o) => !o)}
          >
            <i className={`bi ${menuOpen ? 'bi-x-lg' : 'bi-list'}`} aria-hidden />
          </button>

          <div
            className={`${
              menuOpen ? 'flex' : 'hidden'
            } md:flex flex-col md:flex-row md:items-center gap-0 md:gap-1 absolute md:static top-14 left-0 right-0 md:top-auto bg-[#0d6efd] md:bg-transparent border-t md:border-t-0 border-white/20 px-4 py-2 md:p-0 z-50 shadow-lg md:shadow-none`}
          >
            {NAV_ITEMS.map((item) => {
              const active = item.isActive(pathname)
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded text-sm no-underline transition-colors ${
                    active ? 'bg-white/20 text-white font-medium' : 'text-white/90 hover:bg-white/10 hover:text-white'
                  }`}
                  onClick={() => setMenuOpen(false)}
                >
                  <i className={`bi ${item.icon}`} aria-hidden />
                  {item.label}
                </a>
              )
            })}
            <form action="/auth/logout" method="post" className="md:inline md:ml-0">
              <button
                type="submit"
                className="w-full md:w-auto text-left flex items-center gap-1.5 px-3 py-2 rounded text-sm text-white/90 hover:bg-white/10 hover:text-white bg-transparent border-0 cursor-pointer"
              >
                <i className="bi bi-box-arrow-right" aria-hidden />
                Logout
              </button>
            </form>
          </div>
        </div>
      </div>
    </nav>
  )
}
