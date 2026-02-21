import { Link } from 'react-router-dom';
import { Button } from '../components/ui';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center animate-fade-in">
      <h1 className="text-4xl font-bold text-neutral-900">Page not found</h1>
      <p className="mt-3 text-neutral-500">The page you're looking for doesn't exist or has been moved.</p>
      <Link to="/dashboard" className="mt-6">
        <Button size="md">Back to Dashboard</Button>
      </Link>
    </div>
  );
}
