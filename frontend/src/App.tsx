import { lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './hooks/AuthContext';
import { CoachingProvider } from './hooks/CoachingContext';
import { NetworkStatusProvider } from './hooks/useNetworkStatus';
import { MutationBusProvider } from './hooks/MutationBusContext';
import { ToastProvider } from './components/ui';
import { ProtectedRoute } from './components/ProtectedRoute';
import GlobalErrorHandler from './components/GlobalErrorHandler';
import IntroVideo from './components/IntroVideo';
import Layout from './components/Layout';
import Login from './components/Login';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import Missions from './pages/Missions';
import Evidence from './pages/Evidence';
import Profile from './pages/Profile';
import NotFound from './pages/NotFound';

const CoachingPage = lazy(() => import('./pages/CoachingPage'));
const VoicePracticePage = lazy(() => import('./pages/VoicePracticePage'));
const VoiceSessionDetailPage = lazy(() => import('./pages/VoiceSessionDetailPage'));
const ResumePage = lazy(() => import('./pages/ResumePage'));
const OnetPage = lazy(() => import('./pages/OnetPage'));

function App() {
  return (
    <AuthProvider>
      <MutationBusProvider>
      <ToastProvider>
      <GlobalErrorHandler />
      <IntroVideo />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <CoachingProvider>
                  <NetworkStatusProvider>
                    <Layout />
                  </NetworkStatusProvider>
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
