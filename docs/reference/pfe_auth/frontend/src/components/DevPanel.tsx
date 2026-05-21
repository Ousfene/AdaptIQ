import React, { useState } from 'react';
import { ChevronUp, X, RotateCcw, Zap } from 'lucide-react';
import { useDevMode } from '../context/DevModeContext';

export const DevPanel: React.FC = () => {
  const { dev, setDifficulty, setAccuracy, setSkipTimer, resetToDefaults } = useDevMode();
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (!dev.isEnabled) return null;

  return (
    <>
      {/* Dev Mode Active Banner */}
      <div className="fixed top-0 left-0 right-0 h-1 bg-gradient-to-r from-red-500 via-red-600 to-red-500 animate-pulse z-50" />

      {/* Dev Panel */}
      <div className="fixed bottom-4 right-4 w-80 bg-gray-900 border-2 border-red-500 rounded-lg shadow-2xl z-50 text-white font-mono text-xs">
        {/* Header */}
        <div className="bg-red-900 px-4 py-3 flex items-center justify-between rounded-t-md">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-red-400" />
            <span className="font-bold uppercase tracking-wide">DEV MODE ACTIVE</span>
          </div>
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1 hover:bg-red-800 rounded transition-colors"
          >
            <ChevronUp className={`w-4 h-4 transition-transform ${isCollapsed ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {/* Content */}
        {!isCollapsed && (
          <div className="p-4 space-y-4 bg-gray-800 rounded-b-md max-h-96 overflow-y-auto">
            {/* Difficulty Slider */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-gray-300">Difficulty</label>
                <span className="text-cyan-400 font-bold">{dev.difficulty}</span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                value={dev.difficulty}
                onChange={(e) => setDifficulty(parseInt(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
              />
              <div className="text-gray-500 text-[10px] mt-1">1 = Easy, 5 = Hard</div>
            </div>

            {/* Accuracy Slider */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-gray-300">Accuracy</label>
                <span className="text-green-400 font-bold">{dev.accuracy}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={dev.accuracy}
                onChange={(e) => setAccuracy(parseInt(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500"
              />
              <div className="text-gray-500 text-[10px] mt-1">Simulates correct answer rate</div>
            </div>

            {/* Skip Timer Toggle */}
            <div>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-gray-700 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={dev.skipTimer}
                  onChange={(e) => setSkipTimer(e.target.checked)}
                  className="w-4 h-4 rounded accent-yellow-500"
                />
                <span className="text-gray-300">Skip Timer</span>
              </label>
              <div className="text-gray-500 text-[10px] ml-6">Instant answer submission</div>
            </div>

            {/* Current Settings */}
            <div className="border-t border-gray-700 pt-3 mt-3">
              <div className="text-gray-400 text-[11px] space-y-1">
                <div>URL: <span className="text-blue-400">{window.location.origin}/rooms/classic?dev=true</span></div>
                <div>Mode: <span className="text-yellow-400">DEVELOPMENT</span></div>
              </div>
            </div>

            {/* Reset Button */}
            <button
              onClick={resetToDefaults}
              className="w-full bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-3 rounded text-xs flex items-center justify-center gap-2 transition-colors mt-4"
            >
              <RotateCcw className="w-3 h-3" />
              Reset to Defaults
            </button>
          </div>
        )}

        {/* Collapse indicator */}
        {isCollapsed && (
          <div className="px-4 py-2 bg-gray-800 text-gray-400 text-[10px] text-center rounded-b-md">
            [{dev.difficulty}] [{dev.accuracy}%] {dev.skipTimer ? '[SKIP]' : ''}
          </div>
        )}
      </div>
    </>
  );
};

export default DevPanel;
