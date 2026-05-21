from __future__ import annotations

import time
import uuid

import pytest
from main import app


class _FakeLLM:
    async def generate_hint(self, _question_text: str, _correct_answer: str) -> str:
        return 'Focus on the main capital city clue.'

    async def close(self) -> None:
        return None


async def _no_cache(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_classic_room_question_hint_answer_and_stats_flow(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'What is the capital of France?',
            'options': ['Paris', 'Rome', 'Madrid', 'Berlin'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris is the capital of France.',
        }

    # Keep RAG logic untouched; replace runtime calls only for deterministic tests.
    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    email = f'classic_{run_id}@example.com'
    username = f'classic_{run_id}'
    password = 'Strong!123'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': password},
    )
    assert register.status_code == 201
    data = register.json()

    token = data['access_token']
    user_id = data['user']['id']
    headers = {'Authorization': f'Bearer {token}'}

    session_id = str(uuid.uuid4())

    q_resp = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q_resp.status_code == 200
    question = q_resp.json()
    assert set(question.keys()) == {'id', 'text', 'options', 'correctAnswer', 'explanation', 'locked'}
    assert isinstance(question['id'], str)
    assert isinstance(question['text'], str)
    assert isinstance(question['options'], list)
    assert isinstance(question['correctAnswer'], str)
    assert isinstance(question['explanation'], str)
    assert question['correctAnswer'] == 'Paris'
    assert question['locked'] is False

    hint_resp = await api_client.post(
        '/api/rooms/classic/hints',
        headers=headers,
        json={
            'questionText': question['text'],
            'correctAnswer': question['correctAnswer'],
        },
    )
    assert hint_resp.status_code == 200
    hint_payload = hint_resp.json()
    assert set(hint_payload.keys()) == {'hint'}
    assert isinstance(hint_payload['hint'], str)

    answer_resp = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question['id'],
            'selected_answer': 'Paris',
            'time_taken': 3,
            'used_hint': False,
        },
    )
    assert answer_resp.status_code == 200
    answer_payload = answer_resp.json()
    assert set(answer_payload.keys()) == {'success', 'updated_difficulty', 'locked'}
    assert answer_payload['success'] is True
    assert isinstance(answer_payload['updated_difficulty'], int)
    assert answer_payload['locked'] is True

    stats_resp = await api_client.get('/api/auth/stats', headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats['total_questions'] >= 1
    assert stats['correct_questions'] >= 1


@pytest.mark.asyncio
async def test_classic_room_answer_normalization_counts_equivalent_answer_correct(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital of France?',
            'options': ['  PARIS  ', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris is the capital of France.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    email = f'classic_mismatch_{run_id}@example.com'
    username = f'classic_mismatch_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    data = register.json()
    token = data['access_token']
    user_id = data['user']['id']
    headers = {'Authorization': f'Bearer {token}'}
    session_id = str(uuid.uuid4())

    q_resp = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q_resp.status_code == 200
    question = q_resp.json()

    answer_resp = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question['id'],
            'selected_answer': '  paris  ',
            'time_taken': 4,
            'used_hint': False,
        },
    )
    assert answer_resp.status_code == 200

    stats_resp = await api_client.get('/api/auth/stats', headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats['total_questions'] >= 1
    assert stats['correct_questions'] >= 1


@pytest.mark.asyncio
async def test_classic_room_incorrect_answer_still_counted_wrong(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital of France?',
            'options': ['Paris', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris is the capital of France.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    email = f'classic_wrong_{run_id}@example.com'
    username = f'classic_wrong_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    data = register.json()
    headers = {'Authorization': f"Bearer {data['access_token']}"}
    user_id = data['user']['id']
    session_id = str(uuid.uuid4())

    q_resp = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q_resp.status_code == 200
    question = q_resp.json()

    answer_resp = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question['id'],
            'selected_answer': 'Rome',
            'time_taken': 4,
            'used_hint': False,
        },
    )
    assert answer_resp.status_code == 200

    stats_resp = await api_client.get('/api/auth/stats', headers=headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json()['correct_questions'] == 0


@pytest.mark.asyncio
async def test_classic_room_requires_bearer_token(api_client):
    session_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())

    q = await api_client.post(
        '/api/rooms/classic/questions',
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': str(uuid.uuid4()),
            'session_id': session_id,
        },
    )
    assert q.status_code == 401

    h = await api_client.post(
        '/api/rooms/classic/hints',
        json={'questionText': 'Q?', 'correctAnswer': 'A'},
    )
    assert h.status_code == 401

    a = await api_client.post(
        '/api/rooms/classic/answers',
        json={
            'user_id': str(uuid.uuid4()),
            'session_id': session_id,
            'question_id': question_id,
            'selected_answer': 'A',
            'time_taken': 3,
            'used_hint': False,
        },
    )
    assert a.status_code == 401


@pytest.mark.asyncio
async def test_classic_room_user_id_mismatch_returns_403(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital?',
            'options': ['Paris', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    register = await api_client.post(
        '/api/auth/register',
        json={
            'email': f'mismatch_{run_id}@example.com',
            'username': f'mismatch_{run_id}',
            'password': 'Strong!123',
        },
    )
    assert register.status_code == 201
    token = register.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    wrong_user = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    q = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': wrong_user,
            'session_id': session_id,
        },
    )
    assert q.status_code == 403

    a = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': wrong_user,
            'session_id': session_id,
            'question_id': str(uuid.uuid4()),
            'selected_answer': 'Paris',
            'time_taken': 2,
            'used_hint': False,
        },
    )
    assert a.status_code == 403


@pytest.mark.asyncio
async def test_classic_room_db_unavailable_returns_503(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital?',
            'options': ['Paris', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    register = await api_client.post(
        '/api/auth/register',
        json={
            'email': f'no_db_{run_id}@example.com',
            'username': f'no_db_{run_id}',
            'password': 'Strong!123',
        },
    )
    assert register.status_code == 201

    token = register.json()['access_token']
    user_id = register.json()['user']['id']
    headers = {'Authorization': f'Bearer {token}'}
    session_id = str(uuid.uuid4())

    q = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q.status_code == 200
    question_id = q.json()['id']

    original_factory = app.state.db_session_factory
    app.state.db_session_factory = None
    try:
        a = await api_client.post(
            '/api/rooms/classic/answers',
            headers=headers,
            json={
                'user_id': user_id,
                'session_id': session_id,
                'question_id': question_id,
                'selected_answer': 'Paris',
                'time_taken': 2,
                'used_hint': False,
            },
        )
        assert a.status_code == 503
        assert a.json().get('detail') == 'Database unavailable'
    finally:
        app.state.db_session_factory = original_factory

    recovered = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question_id,
            'selected_answer': 'Paris',
            'time_taken': 2,
            'used_hint': False,
        },
    )
    assert recovered.status_code == 200


@pytest.mark.asyncio
async def test_classic_room_rejects_duplicate_answer_for_same_question(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital of France?',
            'options': ['Paris', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris is the capital of France.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    register = await api_client.post(
        '/api/auth/register',
        json={
            'email': f'duplicate_answer_{run_id}@example.com',
            'username': f'duplicate_answer_{run_id}',
            'password': 'Strong!123',
        },
    )
    assert register.status_code == 201

    token = register.json()['access_token']
    user_id = register.json()['user']['id']
    headers = {'Authorization': f'Bearer {token}'}
    session_id = str(uuid.uuid4())

    q = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q.status_code == 200
    question_id = q.json()['id']

    first = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question_id,
            'selected_answer': 'Paris',
            'time_taken': 2,
            'used_hint': False,
        },
    )
    assert first.status_code == 200

    second = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question_id,
            'selected_answer': 'Rome',
            'time_taken': 1,
            'used_hint': False,
        },
    )
    assert second.status_code == 409
    assert second.json().get('detail') == 'Question already answered in this session'


@pytest.mark.asyncio
async def test_classic_room_rejects_whitespace_only_answer(api_client, monkeypatch):
    async def _fake_run(**_kwargs):
        return {
            'id': str(uuid.uuid4()),
            'text': 'Capital of France?',
            'options': ['Paris', 'Rome'],
            'correctAnswer': 'Paris',
            'explanation': 'Paris is the capital of France.',
        }

    monkeypatch.setattr('routers.classic_room.rag_pipeline.run', _fake_run)
    monkeypatch.setattr('routers.classic_room.get_cached_question', _no_cache)
    monkeypatch.setattr('routers.classic_room.get_llm', lambda: _FakeLLM())

    run_id = int(time.time() * 1000)
    register = await api_client.post(
        '/api/auth/register',
        json={
            'email': f'blank_answer_{run_id}@example.com',
            'username': f'blank_answer_{run_id}',
            'password': 'Strong!123',
        },
    )
    assert register.status_code == 201

    token = register.json()['access_token']
    user_id = register.json()['user']['id']
    headers = {'Authorization': f'Bearer {token}'}
    session_id = str(uuid.uuid4())

    q = await api_client.post(
        '/api/rooms/classic/questions',
        headers=headers,
        json={
            'topic': 'History',
            'difficulty': 2,
            'user_id': user_id,
            'session_id': session_id,
        },
    )
    assert q.status_code == 200
    question_id = q.json()['id']

    answer = await api_client.post(
        '/api/rooms/classic/answers',
        headers=headers,
        json={
            'user_id': user_id,
            'session_id': session_id,
            'question_id': question_id,
            'selected_answer': '   ',
            'time_taken': 2,
            'used_hint': False,
        },
    )
    assert answer.status_code == 422
    assert answer.json().get('detail') == 'selected_answer cannot be empty'
