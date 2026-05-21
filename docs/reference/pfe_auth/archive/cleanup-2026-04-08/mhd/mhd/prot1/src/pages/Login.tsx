import { useNavigate } from "react-router-dom";
import "../styles/auth.css";
import "../styles/login.css";

export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="auth-page">
      <div className="auth-bg"></div>
      <div className="auth-card">
        <h2 className="auth-title">Log In</h2>

        <input className="auth-input" placeholder="Email" />
        <input className="auth-input" placeholder="Password" type="password" />

        <button className="auth-button" onClick={() => navigate('/dashboard')}>
          Log In
        </button>

        <div className="auth-switch">
          Don’t have an account?{" "}
          <span className="auth-link" onClick={() => navigate("/signup")}>
            Sign up
          </span>
        </div>
      </div>
    </div>
  );
}
