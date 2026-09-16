// Tool selection page shown after authentication.
// Cards are generated entirely from the backend tool registry, so a new tool
// only needs a Tool(...) entry in backend/tool_registry.py to appear here.
import { useEffect, useState } from 'react';
import type { Tool } from '../types/tool';
import { getTools } from '../services/api';

interface ToolDashboardProps {
  onOpenTool: (tool: Tool) => void;
  onLogout: () => void;
}

// Cosmetic accent per tool id. Tools without an entry fall back to a default.
const CARD_CLASS_BY_ID: Record<string, string> = {
  mbr_analysis: 'tool-card-mbr',
  traction_force: 'tool-card-traction',
  beadbuddy: 'tool-card-beadbuddy',
  segmentation_3d: 'tool-card-segmentation',
};

const ToolDashboard = ({ onOpenTool, onLogout }: ToolDashboardProps) => {
  const [tools, setTools] = useState<Tool[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getTools();
        if (!cancelled) setTools(data);
      } catch (fetchError: any) {
        if (!cancelled) setError(fetchError?.response?.data?.detail || 'Unable to load tools.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="tool-dashboard">
      <div className="dashboard-heading">
        <p className="dashboard-kicker">Your workspace</p>
        <h2>Choose a tool</h2>
        <p>Select an analysis or utility to continue.</p>
      </div>

      {error && <div className="dashboard-error">{error}</div>}

      <div className="tool-grid">
        {tools.map((tool, index) => (
          <button
            key={tool.id}
            className={`tool-card ${CARD_CLASS_BY_ID[tool.id] || 'tool-card-beadbuddy'}`}
            type="button"
            disabled={!tool.enabled}
            onClick={() => onOpenTool(tool)}
          >
            <span className="tool-card-number">{String(index + 1).padStart(2, '0')}</span>
            <span className="tool-card-title">{tool.name}</span>
            <span className="tool-card-status">{tool.enabled ? 'Open tool' : 'Coming soon'}</span>
          </button>
        ))}
      </div>

      <button className="dashboard-logout" onClick={onLogout} type="button">
        Logout
      </button>
    </div>
  );
};

export default ToolDashboard;

