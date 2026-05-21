"""
services/monitoring.py — In-memory monitoring for rate limits and API errors.

Tracks recent errors and rate limit hits for debugging and analytics.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Optional


class MonitoringService:
    """Track recent rate limits and errors for debugging."""

    def __init__(self, max_events: int = 100):
        """max_events: Keep last N events in memory."""
        self.max_events = max_events
        self.rate_limits: deque = deque(maxlen=max_events)
        self.errors: deque = deque(maxlen=max_events)
        self.request_stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_rate_limits": 0,
        }

    def record_rate_limit(self, client_ip: str, path: str, method: str) -> None:
        """Record a rate limit hit."""
        self.rate_limits.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "path": path,
            "method": method,
            "endpoint": f"{method} {path}",
        })
        self.request_stats["total_rate_limits"] += 1

    def record_error(
        self,
        path: str,
        method: str,
        status_code: int,
        error_type: str,
        error_message: str,
        duration_ms: float,
    ) -> None:
        """Record an API error."""
        self.errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "method": method,
            "status_code": status_code,
            "error_type": error_type,
            "error_message": error_message[:200],  # Truncate long messages
            "duration_ms": duration_ms,
            "endpoint": f"{method} {path}",
        })
        self.request_stats["total_errors"] += 1

    def record_request(self, path: str) -> None:
        """Record a successful request."""
        self.request_stats["total_requests"] += 1

    def get_recent_rate_limits(self, limit: int = 20) -> list[dict]:
        """Get recent rate limit hits."""
        return list(self.rate_limits)[-limit:]

    def get_recent_errors(self, limit: int = 20) -> list[dict]:
        """Get recent errors."""
        return list(self.errors)[-limit:]

    def get_stats(self) -> dict:
        """Get overall stats."""
        return {
            "total_requests": self.request_stats["total_requests"],
            "total_errors": self.request_stats["total_errors"],
            "total_rate_limits": self.request_stats["total_rate_limits"],
            "error_rate": (
                self.request_stats["total_errors"] / self.request_stats["total_requests"]
                if self.request_stats["total_requests"] > 0
                else 0
            ),
            "rate_limit_count": len(self.rate_limits),
            "recent_errors": self.get_recent_errors(5),
            "recent_rate_limits": self.get_recent_rate_limits(5),
        }

    def clear(self) -> None:
        """Clear all collected data."""
        self.rate_limits.clear()
        self.errors.clear()
        self.request_stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_rate_limits": 0,
        }


# Global instance
_monitoring: Optional[MonitoringService] = None


def get_monitoring() -> MonitoringService:
    """Get or create monitoring service."""
    global _monitoring
    if _monitoring is None:
        _monitoring = MonitoringService(max_events=200)
    return _monitoring
