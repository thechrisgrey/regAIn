import { lazy } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { AuthProvider } from './hooks/AuthContext';
import { CoachingProvider } from './hooks/CoachingContext';
import { DataProvider } from './hooks/DataContext';
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

const VoicePracticePage = lazy(() => import('./pages/VoicePracticePage'));
const VoiceSessionDetailPage = lazy(() => import('./pages/VoiceSessionDetailPage'));
const ResumePage = lazy(() => import('./pages/ResumePage'));
const OnetPage = lazy(() => import('./pages/OnetPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const ImpactScorecardPage = lazy(() => import('./pages/ImpactScorecardPage'));
const PublicScorecardPage = lazy(() => import('./pages/PublicScorecardPage'));
const CalendarPage = lazy(() => import('./pages/CalendarPage'));

const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/s/:shortCode',
    element: <PublicScorecardPage />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <DataProvider>
          <CoachingProvider>
            <NetworkStatusProvider>
              <Layout />
            </NetworkStatusProvider>
          </CoachingProvider>
        </DataProvider>
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" /> },
      { path: 'onboarding', element: <Onboarding /> },
      { path: 'dashboard', element: <Dashboard /> },
{ path: 'voice-practice', element: <VoicePracticePage /> },
      { path: 'voice-practice/:sessionId', element: <VoiceSessionDetailPage /> },
      { path: 'missions', element: <Missions /> },
      { path: 'evidence', element: <Evidence /> },
      { path: 'analytics', element: <AnalyticsPage /> },
      { path: 'calendar', element: <CalendarPage /> },
      { path: 'scorecard', element: <ImpactScorecardPage /> },
      { path: 'resume', element: <ResumePage /> },
      { path: 'onet', element: <OnetPage /> },
      { path: 'profile', element: <Profile /> },
    ],
  },
  {
    path: '*',
    element: <NotFound />,
  },
]);

function App() {
  return (
    <AuthProvider>
      <MutationBusProvider>
      <ToastProvider>
      <GlobalErrorHandler />
      <IntroVideo />
      <RouterProvider router={router} />
      </ToastProvider>
      </MutationBusProvider>
    </AuthProvider>
  );
}

export default App;
