/**
 * services/errorTracking.ts
 * Client-side error tracking for debugging frontend issues.
 *
 * Logs API errors with context and timing information.
 */

export interface ErrorLogEntry {
  timestamp: string;
  message: string;
  endpoint: string;
  status?: number;
  errorType: string;
  duration_ms?: number;
  requestId?: string;
  context?: Record<string, any>;
}

class ErrorTracker {
  private logs: ErrorLogEntry[] = [];
  private readonly maxLogs = 100;

  /**
   * Log an API error with full context.
   */
  logApiError(entry: ErrorLogEntry): void {
    this.logs.push({
      ...entry,
      timestamp: entry.timestamp || new Date().toISOString(),
    });

    // Keep only recent logs in memory
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(-this.maxLogs);
    }

    // Also log to console in development
    if (import.meta.env.DEV) {
      console.error(`[${entry.errorType}] ${entry.message}`, entry);
    }
  }

  /**
   * Get recent errors for display or debugging.
   */
  getRecentErrors(limit = 10): ErrorLogEntry[] {
    return this.logs.slice(-limit).reverse();
  }

  /**
   * Get error statistics.
   */
  getStats() {
    return {
      totalErrors: this.logs.length,
      recentErrors: this.getRecentErrors(5),
      errorsByType: this.getErrorTypeDistribution(),
    };
  }

  /**
   * Get distribution of errors by type.
   */
  private getErrorTypeDistribution(): Record<string, number> {
    const distribution: Record<string, number> = {};
    for (const log of this.logs) {
      distribution[log.errorType] = (distribution[log.errorType] || 0) + 1;
    }
    return distribution;
  }

  /**
   * Clear all logs.
   */
  clear(): void {
    this.logs = [];
  }

  /**
   * Export logs as JSON for debugging.
   */
  exportAsJson(): string {
    return JSON.stringify({
      exportedAt: new Date().toISOString(),
      totalErrors: this.logs.length,
      errors: this.logs,
    }, null, 2);
  }
}

// Global singleton instance
export const errorTracker = new ErrorTracker();

/**
 * Log API error with standardized format.
 */
export function logApiErrorWithContext(
  message: string,
  endpoint: string,
  options?: {
    status?: number;
    duration_ms?: number;
    requestId?: string;
    errorType?: string;
    context?: Record<string, any>;
  }
): void {
  errorTracker.logApiError({
    timestamp: new Date().toISOString(),
    message,
    endpoint,
    status: options?.status,
    duration_ms: options?.duration_ms,
    requestId: options?.requestId,
    errorType: options?.errorType || 'APIError',
    context: options?.context,
  });
}
