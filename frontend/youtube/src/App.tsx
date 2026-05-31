import { Routes, Route, Navigate } from 'react-router-dom'
import TopNav from './components/TopNav'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Channels from './pages/Channels'
import Videos from './pages/Videos'
import VideoDetail from './pages/VideoDetail'
import Tags from './pages/Tags'
import Jobs from './pages/Jobs'
import Digests from './pages/Digests'
import DigestDetail from './pages/DigestDetail'
import DatabaseSettings from './pages/settings/DatabaseSettings'
import AIGatewaySettings from './pages/settings/AIGatewaySettings'
import RuntimeSettings from './pages/settings/RuntimeSettings'
import NotificationSettings from './pages/settings/NotificationSettings'
import PromptSettings from './pages/settings/PromptSettings'
import DigestSettings from './pages/settings/DigestSettings'
import InstantAnalyze from './pages/InstantAnalyze'

export default function App() {
  return (
    <>
      <TopNav />
      <Routes>
      <Route path="/youtube" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="channels" element={<Channels />} />
        <Route path="videos" element={<Videos />} />
        <Route path="videos/:videoPk" element={<VideoDetail />} />
        <Route path="tags" element={<Tags />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="digests" element={<Digests />} />
        <Route path="digests/:digestPk" element={<DigestDetail />} />
        <Route path="settings/database" element={<DatabaseSettings />} />
        <Route path="settings/ai-gateway" element={<AIGatewaySettings />} />
        <Route path="settings/runtime" element={<RuntimeSettings />} />
        <Route path="settings/notification" element={<NotificationSettings />} />
        <Route path="settings/prompts" element={<PromptSettings />} />
        <Route path="settings/digest" element={<DigestSettings />} />
        <Route path="instant-analyze" element={<InstantAnalyze />} />
        <Route path="*" element={<Navigate to="/youtube/" replace />} />
      </Route>
    </Routes>
    </>
  )
}
