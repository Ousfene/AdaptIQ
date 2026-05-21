import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/auth.css';

const API_BASE = (() => {
  const url = import.meta.env.VITE_API_URL;
  if (!url) {
    throw new Error("VITE_API_URL environment variable is not configured");
  }
  return url;
})();

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [sent, setSent] = useState(false);

  const handleSubmit = async () => {
    if (!email.trim()) { setError('Please enter your email address.'); return; }
    setError('');
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Error ${res.status}`);
      }
      setSent(true);
    } catch (err: any) {
      setError(err.message ?? 'Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-bg"></div>
      <div className="auth-card">
        <h2 className="auth-title">Forgot Password</h2>

        {sent ? (
          <div style={{ textAlign: 'center' }}>
            <p style={{ color: '#2D1B14', marginBottom: 16 }}>
              If an account exists for <strong>{email}</strong>, a reset code has been sent
              (check the server console in dev mode).
            </p>
            <button
              className="auth-button"
              onClick={() => navigate('/reset-password', { state: { email } })}
            >
              Enter Reset Code
            </button>
          </div>
        ) : (
          <>
            {error && (
              <div style={{ color: '#c0392b', fontSize: 13, marginBottom: 10, textAlign: 'center', background: 'rgba(192,57,43,0.07)', borderRadius: 8, padding: '8px 12px' }}>
                {error}
              </div>
            )}

            <input
              className="auth-input"
              placeholder="Email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              disabled={isLoading}
            />

            <button className="auth-button" onClick={handleSubmit} disabled={isLoading}>
              {isLoading ? 'Sending…' : 'Send Reset Code'}
            </button>

            <div className="auth-switch">
              <span className="auth-link" onClick={() => navigate('/login')}>
                Back to Login
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
