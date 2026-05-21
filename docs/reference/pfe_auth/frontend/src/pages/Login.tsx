import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/auth.css';
import '../styles/login.css';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) { setError('Please fill in all fields.'); return; }
    setError('');
    setIsLoading(true);
    try {
      await login(email.trim(), password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message ?? 'Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-bg"></div>
      <div className="auth-card">
        <h2 className="auth-title">Log In</h2>

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
          onKeyDown={e => e.key === 'Enter' && handleLogin()}
          disabled={isLoading}
        />
        <input
          className="auth-input"
          placeholder="Password"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleLogin()}
          disabled={isLoading}
        />

        <div style={{ alignSelf: 'flex-end', marginBottom: 4, fontSize: 12 }}>
          <span
            className="auth-link"
            style={{ cursor: 'pointer' }}
            onClick={() => navigate('/forgot-password')}
          >
            Forgot password?
          </span>
        </div>

        <button className="auth-button" onClick={handleLogin} disabled={isLoading}>
          {isLoading ? 'Logging in…' : 'Log In'}
        </button>

        <div className="auth-switch">
          Don't have an account?{' '}
          <span className="auth-link" onClick={() => navigate('/signup')}>
            Sign up
          </span>
        </div>
      </div>
    </div>
  );
}
