import React, { createContext, useContext, useState, useEffect } from 'react';

export interface DevModeState {
  isEnabled: boolean;
  difficulty: number;           // 1-5
  accuracy: number;             // 0-100
  skipTimer: boolean;
}

interface DevModeContextType {
  dev: DevModeState;
  setDifficulty: (val: number) => void;
  setAccuracy: (val: number) => void;
  setSkipTimer: (val: boolean) => void;
  resetToDefaults: () => void;
}

const DevModeContext = createContext<DevModeContextType | undefined>(undefined);

const DEFAULT_STATE: DevModeState = {
  isEnabled: false,
  difficulty: 3,
  accuracy: 70,
  skipTimer: false,
};

export const DevModeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [dev, setDev] = useState<DevModeState>(DEFAULT_STATE);

  useEffect(() => {
    // SECURITY: Only allow dev mode in development environment
    // In production (import.meta.env.PROD), dev mode is completely disabled
    if (import.meta.env.PROD) {
      return; // Dev mode disabled in production
    }

    // Check URL for ?dev=true (development only)
    const params = new URLSearchParams(window.location.search);
    const devEnabled = params.get('dev') === 'true';

    if (devEnabled) {
      // Load saved dev state from sessionStorage
      const savedDev = sessionStorage.getItem('adaptiq_dev_mode');
      if (savedDev) {
        try {
          setDev(JSON.parse(savedDev));
        } catch {
          setDev({ ...DEFAULT_STATE, isEnabled: true });
        }
      } else {
        setDev({ ...DEFAULT_STATE, isEnabled: true });
      }
    }
  }, []);

  useEffect(() => {
    // Persist dev state whenever it changes
    if (dev.isEnabled) {
      sessionStorage.setItem('adaptiq_dev_mode', JSON.stringify(dev));
    }
  }, [dev]);

  const setDifficulty = (val: number) => {
    const clamped = Math.max(1, Math.min(5, Math.round(val)));
    setDev(prev => ({ ...prev, difficulty: clamped }));
  };

  const setAccuracy = (val: number) => {
    const clamped = Math.max(0, Math.min(100, Math.round(val)));
    setDev(prev => ({ ...prev, accuracy: clamped }));
  };

  const setSkipTimer = (val: boolean) => {
    setDev(prev => ({ ...prev, skipTimer: val }));
  };

  const resetToDefaults = () => {
    setDev({ ...DEFAULT_STATE, isEnabled: true });
  };

  return (
    <DevModeContext.Provider value={{ dev, setDifficulty, setAccuracy, setSkipTimer, resetToDefaults }}>
      {children}
    </DevModeContext.Provider>
  );
};

export const useDevMode = () => {
  const context = useContext(DevModeContext);
  if (!context) {
    throw new Error('useDevMode must be used within DevModeProvider');
  }
  return context;
};
