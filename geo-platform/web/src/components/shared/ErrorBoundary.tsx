import React from "react";
import { Result, Button } from "antd";

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="Something went wrong"
          subTitle={this.state.message}
          extra={
            <Button onClick={() => this.setState({ hasError: false, message: "" })}>
              Try again
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
