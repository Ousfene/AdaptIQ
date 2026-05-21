import pytest
from services.visual_room_service import (
    LEVEL_OPTIONS_COUNT, SHAPE_PROBABILITY,
    should_show_shape, visual_question_needs_generation
)
from database.visual_models import VisualQuestion

def test_visual_level_options_count():
    assert LEVEL_OPTIONS_COUNT[1] == 2
    assert LEVEL_OPTIONS_COUNT[2] == 4
    assert LEVEL_OPTIONS_COUNT[5] == 0  # Text input

def test_should_show_shape():
    # History never has shapes
    assert not should_show_shape(4, "history", True)
    
    # Geography with no shape never has shape
    assert not should_show_shape(4, "geography", False)
    
    # Level 1 geography never has shape
    assert not should_show_shape(1, "geography", True)

def test_visual_question_needs_generation():
    # MCQ missing correct answer
    q1 = VisualQuestion(question_text="Q?", correct_answer=None, options_json="[]", question_type='M')
    assert visual_question_needs_generation(q1, 2) is True
    
    # Text input (L5) missing correct answer
    q2 = VisualQuestion(question_text="Q?", correct_answer=None, options_json="[]", question_type='T')
    assert visual_question_needs_generation(q2, 5) is True
    
    # Correct
    q3 = VisualQuestion(question_text="Q?", correct_answer="A", options_json='["A", "B"]', question_type='M')
    assert visual_question_needs_generation(q3, 2) is False

def test_visual_question_placeholder_detection():
    from services.visual_room_service import looks_like_placeholder_options
    q = VisualQuestion(options_json='["Option A", "Option B", "Option C"]')
    assert looks_like_placeholder_options(q) is True
    
    q_good = VisualQuestion(options_json='["France", "Germany"]')
    assert looks_like_placeholder_options(q_good) is False
