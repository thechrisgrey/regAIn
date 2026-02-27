import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './hooks/AuthContext';
import { CoachingProvider } from './hooks/CoachingContext';
import { MutationBusProvider } from './hooks/MutationBusContext';
import { ToastProvider } from './components/ui';
import { ProtectedRoute } from './components/ProtectedRoute';
import IntroVideo from './components/IntroVideo';
import Layout from './components/Layout';
import Login from './components/Login';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import Missions from './pages/Missions';
import Evidence from './pages/Evidence';
import ResumePage from './pages/ResumePage';
import Profile from './pages/Profile';
import CoachingPage from './pages/CoachingPage';
import VoicePracticePage from './pages/VoicePracticePage';
import VoiceSessionDetailPage from './pages/VoiceSessionDetailPage';
import OnetPage from './pages/OnetPage';
import NotFound from './pages/NotFound';

function App() {
  return (
    <AuthProvider>
      <MutationBusProvider>
      <ToastProvider>
      <IntroVideo />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <CoachingProvider>
                  <Layout />
                </CoachingProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" />} />
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="coaching" element={<CoachingPage />} />
            <Route path="voice-practice" element={<VoicePracticePage />} />
            <Route path="voice-practice/:sessionId" element={<VoiceSessionDetailPage />} />
            <Route path="missions" element={<Missions />} />
            <Route path="evidence" element={<Evidence />} />
            <Route path="resume" element={<ResumePage />} />
            <Route path="onet" element={<OnetPage />} />
            <Route path="profile" element={<Profile />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
      </MutationBusProvider>
    </AuthProvider>
  );
}

export default App;
