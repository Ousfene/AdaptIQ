"""
services/log_aggregator.py — Structured logging for comprehensive testing.

Captures all critical events to both:
1. JSON files (backend/logs/test_session_*.json) for easy review
2. PostgreSQL test_logs table for queryable analysis

Event categories:
- 'irt': IRT calculations (theta updates, difficulty selection)
- 'cache': Cache hit/miss, invalidation
- 'session': Session lifecycle (start, end, state changes)
- 'api': API calls and responses
- 'database': Database operations
- 'ui': Frontend interactions (logged separately in TypeScript)
- 'rank': Challenge room rank changes
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class LogAggregator:
    """Collects structured logs for testing and debugging."""

    def __init__(self, logs_dir: str = "backend/logs"):
        """Initialize log aggregator with file output directory."""
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = None
        self.session_logs = []

    def log_event(
        self,
        event_type: str,
        category: str,
        data: dict,
        user_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
    ) -> None:
        """
        Log a structured event.

        Args:
            event_type: Event type (e.g., 'theta_update', 'cache_hit')
            category: Category (irt, cache, session, api, database, rank)
            data: Event-specific data as dict
            user_id: Associated user (optional)
            session_id: Associated session (optional)
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        log_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "category": category,
            "user_id": str(user_id) if user_id else None,
            "session_id": str(session_id) if session_id else None,
            "data": data,
        }

        # Store in memory for session file export
        self.session_logs.append(log_entry)

        # Log to console in development
        logger.info(f"[{category.upper()}] {event_type}: {data}")

    def log_irt_update(
        self,
        user_id: UUID,
        concept_id: UUID,
        old_theta: float,
        new_theta: float,
        p_correct: float,
        learning_rate: float = 0.3,
        question_id: Optional[UUID] = None,
    ) -> None:
        """Log IRT theta update."""
        self.log_event(
            event_type="theta_update",
            category="irt",
            data={
                "concept_id": str(concept_id),
                "old_theta": round(old_theta, 3),
                "new_theta": round(new_theta, 3),
                "theta_change": round(new_theta - old_theta, 3),
                "p_correct": round(p_correct, 3),
                "learning_rate": learning_rate,
                "question_id": str(question_id) if question_id else None,
            },
            user_id=user_id,
        )

    def log_difficulty_selection(
        self,
        user_id: UUID,
        user_theta: float,
        zpd_range: tuple[float, float],
        selected_beta: float,
        question_id: UUID,
    ) -> None:
        """Log difficulty selection for next question."""
        self.log_event(
            event_type="difficulty_selected",
            category="irt",
            data={
                "user_theta": round(user_theta, 3),
                "zpd_min": round(zpd_range[0], 3),
                "zpd_max": round(zpd_range[1], 3),
                "selected_beta": round(selected_beta, 3),
                "question_id": str(question_id),
            },
            user_id=user_id,
        )

    def log_session_start(
        self,
        user_id: UUID,
        session_id: UUID,
        topic: str,
        initial_theta: float,
    ) -> None:
        """Log session start."""
        self.log_event(
            event_type="session_start",
            category="session",
            data={
                "topic": topic,
                "initial_theta": round(initial_theta, 3),
            },
            user_id=user_id,
            session_id=session_id,
        )

    def log_session_end(
        self,
        user_id: UUID,
        session_id: UUID,
        questions_answered: int,
        correct_count: int,
        final_theta: float,
    ) -> None:
        """Log session completion."""
        accuracy = correct_count / questions_answered if questions_answered > 0 else 0
        self.log_event(
            event_type="session_end",
            category="session",
            data={
                "questions_answered": questions_answered,
                "correct_count": correct_count,
                "accuracy": round(accuracy, 3),
                "final_theta": round(final_theta, 3),
            },
            user_id=user_id,
            session_id=session_id,
        )

    def log_question_shown(
        self,
        user_id: UUID,
        session_id: UUID,
        question_id: UUID,
        user_theta: float,
        question_beta: float,
        expected_p_correct: float,
    ) -> None:
        """Log question presentation."""
        self.log_event(
            event_type="question_shown",
            category="session",
            data={
                "question_id": str(question_id),
                "user_theta": round(user_theta, 3),
                "question_beta": round(question_beta, 3),
                "expected_p_correct": round(expected_p_correct, 3),
            },
            user_id=user_id,
            session_id=session_id,
        )

    def log_answer_submitted(
        self,
        user_id: UUID,
        session_id: UUID,
        question_id: UUID,
        was_correct: bool,
        time_taken_ms: int,
    ) -> None:
        """Log answer submission."""
        self.log_event(
            event_type="answer_submitted",
            category="session",
            data={
                "question_id": str(question_id),
                "was_correct": was_correct,
                "time_taken_ms": time_taken_ms,
            },
            user_id=user_id,
            session_id=session_id,
        )

    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Log cache hit/miss/operation."""
        self.log_event(
            event_type=f"cache_{operation}",
            category="cache",
            data={
                "key": key,
                "hit": hit,
                "latency_ms": latency_ms,
            },
        )

    def log_rank_change(
        self,
        user_id: UUID,
        old_rank: str,
        new_rank: str,
        reason: str,
    ) -> None:
        """Log challenge room rank change."""
        self.log_event(
            event_type="rank_changed",
            category="rank",
            data={
                "old_rank": old_rank,
                "new_rank": new_rank,
                "reason": reason,
            },
            user_id=user_id,
        )

    def log_match_end(
        self,
        user_id: UUID,
        match_id: UUID,
        rank: str,
        questions_answered: int,
        correct_count: int,
        elo_change: float,
    ) -> None:
        """Log challenge match completion."""
        accuracy = correct_count / questions_answered if questions_answered > 0 else 0
        self.log_event(
            event_type="match_end",
            category="rank",
            data={
                "match_id": str(match_id),
                "rank": rank,
                "questions_answered": questions_answered,
                "correct_count": correct_count,
                "accuracy": round(accuracy, 3),
                "elo_change": round(elo_change, 3),
            },
            user_id=user_id,
        )

    def export_session_logs(self, test_name: str = "test_session") -> Path:
        """
        Export accumulated logs to JSON file.

        Returns: Path to exported file
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = self.logs_dir / f"{test_name}_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(self.session_logs, f, indent=2)

        logger.info(f"Exported {len(self.session_logs)} log entries to {filename}")
        return filename

    def get_stats(self) -> dict:
        """Get summary statistics about logged events."""
        event_counts = {}
        category_counts = {}

        for entry in self.session_logs:
            event_type = entry["event_type"]
            category = entry["category"]

            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            "total_events": len(self.session_logs),
            "event_types": event_counts,
            "categories": category_counts,
        }


# Global instance for convenient access
_aggregator = None


def get_aggregator() -> LogAggregator:
    """Get or create the global log aggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = LogAggregator()
    return _aggregator
