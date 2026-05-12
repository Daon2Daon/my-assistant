/**
 * 설정 화면 — P10에서 상세 구현 예정.
 * 현재는 API 링크와 간단한 안내만 표시.
 */
import { useParams } from 'react-router-dom'

const PAGE_INFO: Record<string, { title: string; description: string }> = {
  database: {
    title: 'PostgreSQL 연결 설정',
    description: '데이터베이스 호스트, 포트, 인증 정보를 설정합니다.',
  },
  'ai-gateway': {
    title: 'AI Gateway 설정',
    description: 'litellm Gateway 주소, API 키, 사용 모델을 설정합니다.',
  },
  runtime: {
    title: '모니터링 / 알림 설정',
    description: '모니터링 주기, YouTube API 할당량, Telegram 알림 옵션을 설정합니다.',
  },
}

export default function Settings() {
  const { section } = useParams<{ section: string }>()
  const info = section ? PAGE_INFO[section] : null

  if (!info) {
    return (
      <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
        <p className="text-4xl mb-3">⚙️</p>
        <p>알 수 없는 설정 페이지입니다.</p>
      </div>
    )
  }

  const apiPath = section === 'database'
    ? '/api/youtube/settings/database'
    : section === 'ai-gateway'
    ? '/api/youtube/settings/ai_gateway'
    : '/api/youtube/settings/runtime'

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">{info.title}</h1>
      <p className="text-gray-500 text-sm">{info.description}</p>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-800 text-sm space-y-2">
        <p className="font-semibold">P10 구현 예정</p>
        <p>
          설정 UI는 P10 단계에서 구현됩니다.
          현재는 아래 REST API를 직접 사용하거나 <a href="/docs" target="_blank" className="underline">OpenAPI 문서</a>를
          통해 설정을 변경할 수 있습니다.
        </p>
        <code className="block bg-amber-100 rounded px-3 py-2 text-xs font-mono">
          GET / PUT {apiPath}
        </code>
      </div>
    </div>
  )
}
