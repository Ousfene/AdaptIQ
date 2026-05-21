/**
 * frontend/src/services/logAggregator.ts — Structured logging for comprehensive testing
 *
 * Captures frontend events to:
 * 1. IndexedDB for persistent storage
 * 2. In-memory queue for session analysis
 * 3. Export to JSON for post-test review
 *
 * Event categories:
 * - 'ui': Page navigation, component rendering
 * - 'interaction': Button clicks, form submissions
 * - 'api': API request/response timing and status
 * - 'analytics': User behavior metrics
 */

interface LogEntry {
  timestamp: string;
  eventType: string;
  category: string;
  data: Record<string, any>;
}

class FrontendLogAggregator {
  private logs: LogEntry[] = [];
  private readonly MAX_LOGS = 1000;
  private readonly DB_NAME = "AdaptIQ_Logs";
  private readonly STORE_NAME = "events";
  private db: IDBDatabase | null = null;

  constructor() {
    this.initIndexedDB();
  }

  /**
   * Initialize IndexedDB for persistent storage
   */
  private initIndexedDB(): void {
    const request = indexedDB.open(this.DB_NAME, 1);

    request.onerror = () => {
      console.warn("Failed to initialize IndexedDB for logging");
    };

    request.onsuccess = (event) => {
      this.db = (event.target as IDBOpenDBRequest).result;
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(this.STORE_NAME)) {
        db.createObjectStore(this.STORE_NAME, { autoIncrement: true });
      }
    };
  }

  /**
   * Log a structured event
   */
  private logEvent(
    eventType: string,
    category: string,
    data: Record<string, any>
  ): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      eventType,
      category,
      data,
    };

    // Store in memory
    this.logs.push(entry);
    if (this.logs.length > this.MAX_LOGS) {
      this.logs.shift(); // Remove oldest entry
    }

    // Store in IndexedDB asynchronously
    if (this.db) {
      const store = this.db
        .transaction(this.STORE_NAME, "readwrite")
        .objectStore(this.STORE_NAME);
      store.add(entry);
    }

    // Log to console in development
    if (process.env.NODE_ENV === "development") {
      console.log(`[${category.toUpperCase()}] ${eventType}:`, data);
    }
  }

  /**
   * Log page view
   */
  logPageView(pageName: string): void {
    this.logEvent("page_view", "ui", {
      page: pageName,
      url: window.location.href,
    });
  }

  /**
   * Log user action (click, form submission, etc.)
   */
  logUserAction(
    actionType: string,
    data: Record<string, any> = {}
  ): void {
    this.logEvent("user_action", "interaction", {
      action: actionType,
      ...data,
    });
  }

  /**
   * Log API call with timing and status
   */
  logApiCall(
    endpoint: string,
    method: string,
    status: number,
    durationMs: number
  ): void {
    this.logEvent("api_call", "api", {
      endpoint,
      method,
      status,
      durationMs,
      timestamp: new Date().toISOString(),
    });
  }

  /**
   * Log session event (start, answer, etc.)
   */
  logSessionEvent(
    sessionId: string,
    eventType: string,
    data: Record<string, any> = {}
  ): void {
    this.logEvent(eventType, "session", {
      sessionId,
      ...data,
    });
  }

  /**
   * Log question shown to user
   */
  logQuestionShown(
    sessionId: string,
    questionId: string,
    difficulty: number
  ): void {
    this.logEvent("question_shown", "session", {
      sessionId,
      questionId,
      difficulty,
      userAgent: navigator.userAgent,
    });
  }

  /**
   * Log answer submission
   */
  logAnswerSubmitted(
    sessionId: string,
    questionId: string,
    selectedIndex: number,
    timeTakenMs: number
  ): void {
    this.logEvent("answer_submitted", "session", {
      sessionId,
      questionId,
      selectedIndex,
      timeTakenMs,
    });
  }

  /**
   * Log session completion
   */
  logSessionEnd(
    sessionId: string,
    topic: string,
    questionsAnswered: number,
    correctCount: number
  ): void {
    const accuracy =
      questionsAnswered > 0 ? (correctCount / questionsAnswered) * 100 : 0;
    this.logEvent("session_end", "session", {
      sessionId,
      topic,
      questionsAnswered,
      correctCount,
      accuracy: Math.round(accuracy * 100) / 100,
    });
  }

  /**
   * Log rank change in challenge room
   */
  logRankChange(oldRank: string, newRank: string): void {
    this.logEvent("rank_changed", "session", {
      oldRank,
      newRank,
      timestamp: new Date().toISOString(),
    });
  }

  /**
   * Get all logged events
   */
  getLogs(): LogEntry[] {
    return [...this.logs];
  }

  /**
   * Get recent logs (last N entries)
   */
  getRecentLogs(count: number): LogEntry[] {
    return this.logs.slice(-count);
  }

  /**
   * Get logs by category
   */
  getLogsByCategory(category: string): LogEntry[] {
    return this.logs.filter((log) => log.category === category);
  }

  /**
   * Get analytics summary
   */
  getStats(): Record<string, any> {
    const eventCounts: Record<string, number> = {};
    const categoryCounts: Record<string, number> = {};

    this.logs.forEach((log) => {
      eventCounts[log.eventType] = (eventCounts[log.eventType] || 0) + 1;
      categoryCounts[log.category] = (categoryCounts[log.category] || 0) + 1;
    });

    return {
      totalEvents: this.logs.length,
      eventTypes: eventCounts,
      categories: categoryCounts,
      oldestEvent: this.logs[0]?.timestamp || null,
      newestEvent: this.logs[this.logs.length - 1]?.timestamp || null,
    };
  }

  /**
   * Export logs as JSON
   */
  exportAsJson(): string {
    return JSON.stringify(this.logs, null, 2);
  }

  /**
   * Download logs as file
   */
  downloadLogs(filename: string = "adaptiq_logs.json"): void {
    const json = this.exportAsJson();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Clear all logs
   */
  clearLogs(): void {
    this.logs = [];
    if (this.db) {
      this.db
        .transaction(this.STORE_NAME, "readwrite")
        .objectStore(this.STORE_NAME)
        .clear();
    }
  }

  /**
   * Clear logs older than specified hours
   */
  clearOldLogs(hoursOld: number): void {
    const cutoff = new Date(Date.now() - hoursOld * 60 * 60 * 1000);
    this.logs = this.logs.filter((log) => new Date(log.timestamp) > cutoff);
  }
}

// Global instance
let loggerInstance: FrontendLogAggregator | null = null;

export function getLogAggregator(): FrontendLogAggregator {
  if (!loggerInstance) {
    loggerInstance = new FrontendLogAggregator();
  }
  return loggerInstance;
}

// Expose to window for browser console debugging
if (typeof window !== "undefined") {
  (window as any).logAggregator = getLogAggregator();
}

export default FrontendLogAggregator;
