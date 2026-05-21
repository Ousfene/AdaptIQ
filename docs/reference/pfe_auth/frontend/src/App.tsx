import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DevModeProvider } from './context/DevModeContext';
import DevPanel from './components/DevPanel';
import Home from './pages/Home';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ClassicRoom from './pages/ClassicRoom';
import ChallengeRoom from './pages/ChallengeRoom';
import Profile from './pages/Profile';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import ConceptMastery from './components/ConceptMastery';
import InternalLayout from './components/InternalLayout';
import { Loader2 } from 'lucide-react';

// Loading spinner shown during auth check
const LoadingScreen: React.FC = () => (
  <div className="min-h-screen bg-amber-50 flex flex-col items-center justify-center">
    <Loader2 className="w-12 h-12 animate-spin text-amber-600" />
    <p className="mt-4 text-amber-800 font-medium">Loading AdaptIQ...</p>
  </div>
);

// Redirects unauthenticated users to /login
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen />;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
};

// Redirects already-logged-in users away from auth pages
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen />;
  return user ? <Navigate to="/dashboard" replace /> : <>{children}</>;
};

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login"  element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
      <Route path="/forgot-password" element={<PublicRoute><ForgotPassword /></PublicRoute>} />
      <Route path="/reset-password"  element={<PublicRoute><ResetPassword /></PublicRoute>} />
      <Route path="/dashboard"    element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/profile"       element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/rooms/classic" element={<ProtectedRoute><ClassicRoom /></ProtectedRoute>} />
      <Route path="/rooms/challenge" element={<ProtectedRoute><ChallengeRoom /></ProtectedRoute>} />
      <Route path="/concept-mastery" element={<ProtectedRoute><InternalLayout><ConceptMastery /></InternalLayout></ProtectedRoute>} />
      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <DevModeProvider>
      <AuthProvider>
        <AppRoutes />
        <DevPanel />
      </AuthProvider>
    </DevModeProvider>
  );
}
