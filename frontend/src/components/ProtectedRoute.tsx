import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import RouteLoader from './RouteLoader';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <RouteLoader />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
