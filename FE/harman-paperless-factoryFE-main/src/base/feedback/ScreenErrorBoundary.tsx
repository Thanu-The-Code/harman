import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from ".";

interface State {
  error: Error | null;
}

/**
 * Keeps a crash in one screen from blanking the whole app: the sidebar and
 * header stay, the screen shows what failed. Keyed by the path in MainLayout,
 * so moving to another screen starts clean.
 */
class ScreenErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Screen crashed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorState
          message={`Something went wrong on this screen: ${this.state.error.message}`}
          onRetry={() => window.location.reload()}
        />
      );
    }
    return this.props.children;
  }
}

export default ScreenErrorBoundary;
