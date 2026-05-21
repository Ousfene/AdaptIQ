import { Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ClassicRoom from './pages/ClassicRoom';
import ChallengeRoom from './pages/ChallengeRoom';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/rooms/classic" element={<ClassicRoom />} />
      <Route path="/rooms/challenge" element={<ChallengeRoom />} />
    </Routes>
  );
}
