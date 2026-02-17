import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './hooks/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './components/Login';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import Missions from './pages/Missions';
import Evidence from './pages/Evidence';
import Profile from './pages/Profile';
import CoachingPage from './pages/CoachingPage';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="coaching" element={<CoachingPage />} />
            <Route path="missions" element={<Missions />} />
            <Route path="evidence" element={<Evidence />} />
            <Route path="profile" element={<Profile />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
