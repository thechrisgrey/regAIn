import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <h1 className="text-4xl font-bold text-gray-900">Page not found</h1>
      <p className="mt-3 text-gray-500">The page you're looking for doesn't exist or has been moved.</p>
      <Link
        to="/dashboard"
        className="mt-6 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
