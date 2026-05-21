"""services/monitoring.py — In-memory monitoring for rate limits and API errors.

Provides:
    - Request/error/rate-limit counters
    - Bounded recent-event queues for diagnostics
    - Singleton accessor helpers for app-wide reuse
"""
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Optional


class Monitoring:
    """In-memory monitoring service for tracking API metrics."""

    # Initialize aggregate counters and bounded recent-event buffers.
    def __init__(self):
        self.request_stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_rate_limits": 0,
        }
        self.recent_errors = deque(maxlen=100)  # Keep last 100 errors
        self.recent_rate_limits = deque(maxlen=50)  # Keep last 50 rate limits
        self.request_counts = defaultdict(int)  # Per-endpoint counters

    def record_request(self, endpoint: str) -> None:
        """Record a successful request."""
        self.request_stats["total_requests"] += 1
        self.request_counts[endpoint] += 1

    def record_error(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        error_type: str,
        error_message: str,
        duration_ms: float,
    ) -> None:
        """Record an error."""
        self.request_stats["total_errors"] += 1
        self.recent_errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "error_type": error_type,
            "error_message": error_message,
            "duration_ms": duration_ms,
        })

    def record_rate_limit(self, client_ip: str, endpoint: str, method: str) -> None:
        """Record a rate limit hit."""
        self.request_stats["total_rate_limits"] += 1
        self.recent_rate_limits.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "endpoint": endpoint,
            "method": method,
        })

    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            **self.request_stats,
            "endpoints": dict(self.request_counts),
            "recent_errors_count": len(self.recent_errors),
            "recent_rate_limits_count": len(self.recent_rate_limits),
        }


# Singleton instance
_monitoring: Optional[Monitoring] = None


# Return process-wide monitoring singleton, creating it lazily.
def get_monitoring() -> Monitoring:
    """Get or create the monitoring singleton."""
    global _monitoring
    if _monitoring is None:
        _monitoring = Monitoring()
    return _monitoring


# Reset singleton monitoring state (used in tests/diagnostics).
def reset_monitoring() -> None:
    """Reset monitoring (for testing)."""
    global _monitoring
    _monitoring = Monitoring()
