import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Card, Button } from './ui';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[60vh] items-center justify-center">
          <Card variant="elevated" className="max-w-md p-8 text-center">
            <h2 className="text-lg font-semibold text-neutral-900">
              Something went wrong
            </h2>
            <p className="mt-2 text-sm text-neutral-500">
              An unexpected error occurred. Reloading the page should fix it.
            </p>
            <Button
              variant="primary"
              className="mt-6"
              onClick={() => window.location.reload()}
            >
              Reload page
            </Button>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
