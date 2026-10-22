// Top-level React application shell.
// This component decides whether the user is seeing the login/register flow or the
// main authenticated view. It is responsible for navigating between screens and for
// keeping the UI state aligned with the backend auth flow.

import { useState } from 'react';
import Login from './components/Login';
import Register from './components/Register';
import ToolDashboard from './pages/ToolDashboard';
import ToolWorkspace from './pages/ToolWorkspace';
import TractionForceWorkspace from './pages/TractionForceWorkspace';
import type { Tool } from './types/tool';
import labLogo from './assets/LabLogo_cropped.png';

function App() {
  const [currentView, setCurrentView] = useState<'login' | 'register' | 'dashboard' | 'tool'>('login');
  const [activeTool, setActiveTool] = useState<Tool | null>(null);

  const handleLoginSuccess = () => {
    setCurrentView('dashboard');
  };

  const handleRegisterSuccess = () => {
    setCurrentView('login');
    alert('Registration successful! Please login.');
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setActiveTool(null);
    setCurrentView('login');
  };

  const handleOpenTool = (tool: Tool) => {
    setActiveTool(tool);
    setCurrentView('tool');
  };

  return (
    <div className="app-shell" style={{ padding: '20px', minHeight: '100vh' }}>
      <div className="app-logo-anchor" aria-hidden="true">
        <img className="app-logo" src={labLogo} alt="" />
      </div>
      <h1 className="app-title" style={{ textAlign: 'center', color: '#007bff', fontSize: '32px', marginBottom: '30px' }}>
        BetzLab Toolbox
      </h1>

      {currentView === 'login' && (
        <Login
          onLoginSuccess={handleLoginSuccess}
          onRegisterClick={() => setCurrentView('register')}
        />
      )}

      {currentView === 'register' && (
        <Register
          onRegisterSuccess={handleRegisterSuccess}
          onLoginClick={() => setCurrentView('login')}
        />
      )}

      {currentView === 'dashboard' && (
        <ToolDashboard onOpenTool={handleOpenTool} onLogout={handleLogout} />
      )}

      {currentView === 'tool' && activeTool && activeTool.id !== 'traction_force' && (
        <ToolWorkspace tool={activeTool} onBack={() => setCurrentView('dashboard')} />
      )}

      {currentView === 'tool' && activeTool?.id === 'traction_force' && (
        <TractionForceWorkspace tool={activeTool} onBack={() => setCurrentView('dashboard')} />
      )}
    </div>
  );
}

export default App;
