import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Channels from './pages/Channels'
import Videos from './pages/Videos'
import VideoDetail from './pages/VideoDetail'
import Tags from './pages/Tags'
import Jobs from './pages/Jobs'
import DatabaseSettings from './pages/settings/DatabaseSettings'
import AIGatewaySettings from './pages/settings/AIGatewaySettings'
import RuntimeSettings from './pages/settings/RuntimeSettings'

export default function App() {
  return (
    <Routes>
      <Route path="/youtube" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="channels" element={<Channels />} />
        <Route path="videos" element={<Videos />} />
        <Route path="videos/:videoPk" element={<VideoDetail />} />
        <Route path="tags" element={<Tags />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="settings/database" element={<DatabaseSettings />} />
        <Route path="settings/ai-gateway" element={<AIGatewaySettings />} />
        <Route path="settings/runtime" element={<RuntimeSettings />} />
        <Route path="*" element={<Navigate to="/youtube/" replace />} />
      </Route>
    </Routes>
  )
}
