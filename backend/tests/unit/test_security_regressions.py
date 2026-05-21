import uuid

from database.challenge_models import ChallengeAnswer
from database.pvp_models import PvPMatchAnswer
from schemas.custom import CustomQuestionResponse, GenerateCustomHintRequest, SubmitAnswerRequest


def _unique_constraint_columns(model) -> set[tuple[str, ...]]:
    out: set[tuple[str, ...]] = set()
    for constraint in model.__table__.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            out.add(tuple(col.name for col in constraint.columns))
    return out


def test_challenge_answer_has_unique_session_question_constraint() -> None:
    uniques = _unique_constraint_columns(ChallengeAnswer)
    assert ("session_id", "question_id") in uniques


def test_pvp_answer_has_unique_match_user_index_constraint() -> None:
    uniques = _unique_constraint_columns(PvPMatchAnswer)
    assert ("match_id", "user_id", "question_index") in uniques


def test_custom_submit_request_does_not_require_client_correct_answer() -> None:
    payload = SubmitAnswerRequest(
        session_id=str(uuid.uuid4()),
        question_id=str(uuid.uuid4()),
        answer="A",
    )
    assert payload.correct_answer is None
    assert payload.explanation is None


def test_custom_question_response_does_not_expose_pre_answer_correct_answer() -> None:
    payload = CustomQuestionResponse(
        id=str(uuid.uuid4()),
        text="Question",
        options=["A", "B", "C", "D"],
        explanation="Explanation",
    )
    assert "correct_answer" not in payload.model_dump()


def test_custom_hint_request_accepts_question_id_without_client_correct_answer() -> None:
    payload = GenerateCustomHintRequest(question_id=str(uuid.uuid4()))
    assert payload.correct_answer is None
