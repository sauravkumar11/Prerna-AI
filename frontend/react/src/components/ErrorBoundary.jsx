import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Prerna crashed:", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: "16px",
        background: "#0a0a0a",
        color: "#fff",
        fontFamily: "sans-serif",
        textAlign: "center",
        padding: "32px",
      }}>
        <div style={{ fontSize: "48px" }}>💫</div>
        <h2 style={{ margin: 0, color: "#38bdf8" }}>Prerna ran into a problem</h2>
        <p style={{ margin: 0, color: "#94a3b8", maxWidth: "360px", fontSize: "14px" }}>
          {this.state.error?.message || "Something unexpected happened."}
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: "8px",
            padding: "10px 28px",
            background: "linear-gradient(135deg, #38bdf8, #818cf8)",
            border: "none",
            borderRadius: "24px",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
            fontSize: "15px",
          }}
        >
          Restart Prerna
        </button>
      </div>
    );
  }
}
