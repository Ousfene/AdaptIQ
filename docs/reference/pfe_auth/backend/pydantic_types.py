"""Compatibility exports for older imports. Prefer importing from schemas.py."""

from schemas import (
    GenerateHintRequest,
    GenerateQuestionRequest,
    HealthOut,
    HintOut,
    QuestionOut,
    QuizSessionState,
    SubmitAnswerOut,
    SubmitAnswerRequest,
    TopicType,
)

__all__ = [
    "GenerateHintRequest",
    "GenerateQuestionRequest",
    "HealthOut",
    "HintOut",
    "QuestionOut",
    "QuizSessionState",
    "SubmitAnswerOut",
    "SubmitAnswerRequest",
    "TopicType",
]