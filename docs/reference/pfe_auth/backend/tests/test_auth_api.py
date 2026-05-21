from __future__ import annotations

import time

import pytest
from main import app


@pytest.mark.asyncio
async def test_auth_register_login_me_and_stats_contract(api_client):
    run_id = int(time.time() * 1000)
    email = f'auth_{run_id}@example.com'
    username = f'auth_{run_id}'
    password = 'Strong!123'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': password},
    )
    assert register.status_code == 201
    body = register.json()
    assert set(body.keys()) == {'user', 'access_token', 'token_type'}
    assert body['token_type'] == 'bearer'
    assert isinstance(body['access_token'], str)
    assert set(body['user'].keys()) == {'id', 'email', 'username'}
    assert body['user']['email'] == email

    token = body['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    me = await api_client.get('/api/auth/me', headers=headers)
    assert me.status_code == 200
    me_payload = me.json()
    assert set(me_payload.keys()) == {'id', 'email', 'username'}
    assert me_payload['email'] == email

    stats = await api_client.get('/api/auth/stats', headers=headers)
    assert stats.status_code == 200
    stats_body = stats.json()
    expected_stats_keys = {
        'id',
        'points',
        'level',
        'total_questions',
        'correct_questions',
        'global_accuracy',
        'daily_questions',
        'daily_correct',
        'daily_accuracy',
        'learning_time_minutes',
    }
    assert set(stats_body.keys()) == expected_stats_keys
    assert isinstance(stats_body['points'], int)
    assert isinstance(stats_body['global_accuracy'], float)
    assert isinstance(stats_body['daily_accuracy'], float)

    login = await api_client.post(
        '/api/auth/login',
        json={'email': email, 'password': password},
    )
    assert login.status_code == 200
    login_body = login.json()
    assert set(login_body.keys()) == {'user', 'access_token', 'token_type'}
    assert set(login_body['user'].keys()) == {'id', 'email', 'username'}
    assert login_body['user']['email'] == email


@pytest.mark.asyncio
async def test_auth_requires_token_for_me_and_stats(api_client):
    me = await api_client.get('/api/auth/me')
    assert me.status_code == 401

    stats = await api_client.get('/api/auth/stats')
    assert stats.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_password_returns_401(api_client):
    run_id = int(time.time() * 1000)
    email = f'auth_bad_{run_id}@example.com'
    username = f'auth_bad_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    bad_login = await api_client.post(
        '/api/auth/login',
        json={'email': email, 'password': 'Wrong!123'},
    )
    assert bad_login.status_code == 401


@pytest.mark.asyncio
async def test_register_rate_limit_returns_429_with_retry_after(api_client, monkeypatch):
    async def _deny(**_kwargs):
        return False, 17

    monkeypatch.setattr('auth.services.auth_service.check_rate_limit', _deny)

    resp = await api_client.post(
        '/api/auth/register',
        json={'email': 'rl@example.com', 'username': 'rluser', 'password': 'Strong!123'},
    )
    assert resp.status_code == 429
    assert resp.headers.get('Retry-After') == '17'


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429_with_retry_after(api_client, monkeypatch):
    async def _deny(_redis, _ip, _email):
        return False, 12

    monkeypatch.setattr('auth.services.auth_service.check_login_rate_limit', _deny)

    resp = await api_client.post(
        '/api/auth/login',
        json={'email': 'rl@example.com', 'password': 'Strong!123'},
    )
    assert resp.status_code == 429
    assert resp.headers.get('Retry-After') == '12'


@pytest.mark.asyncio
async def test_forgot_and_reset_password_paths(api_client):
    run_id = int(time.time() * 1000)
    email = f'reset_{run_id}@example.com'
    username = f'reset_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    forgot = await api_client.post('/api/auth/forgot-password', json={'email': email})
    assert forgot.status_code == 200
    forgot_payload = forgot.json()
    assert set(forgot_payload.keys()) == {'message', 'email', 'purpose'}
    assert forgot_payload['email'] == email
    assert forgot_payload['purpose'] == 'password_reset'

    # In test/local mode Redis may be unavailable; route should fail gracefully.
    reset = await api_client.post(
        '/api/auth/reset-password',
        json={'email': email, 'code': '000000', 'new_password': 'NewStrong!123'},
    )
    assert reset.status_code in (400, 429)


@pytest.mark.asyncio
async def test_forgot_password_does_not_leak_account_existence(api_client):
    unknown_email = f'no_such_{int(time.time() * 1000)}@example.com'

    resp = await api_client.post('/api/auth/forgot-password', json={'email': unknown_email})
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload.keys()) == {'message', 'email', 'purpose'}
    assert payload['email'] == unknown_email
    assert 'If an account exists' in payload['message']


@pytest.mark.asyncio
async def test_reset_password_when_redis_offline_returns_safe_error(api_client):
    run_id = int(time.time() * 1000)
    email = f'redis_off_{run_id}@example.com'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': f'redis_off_{run_id}', 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    original_redis = app.state.redis
    app.state.redis = None
    try:
        reset = await api_client.post(
            '/api/auth/reset-password',
            json={'email': email, 'code': '123456', 'new_password': 'NewStrong!123'},
        )
        assert reset.status_code == 400
        assert 'Redis is offline' in reset.json().get('detail', '')
    finally:
        app.state.redis = original_redis


@pytest.mark.asyncio
async def test_reset_password_recovery_path_uses_generic_invalid_code(api_client, monkeypatch):
    run_id = int(time.time() * 1000)
    email = f'redis_recover_{run_id}@example.com'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': f'redis_recover_{run_id}', 'password': 'Strong!123'},
    )
    assert register.status_code == 201

    async def _allow_rate_limit(**_kwargs):
        return True, 0

    async def _invalid_otp(_redis, _email, _purpose, _code):
        return False

    class _FakeRedis:
        pass

    monkeypatch.setattr('auth.services.auth_service.check_rate_limit', _allow_rate_limit)
    monkeypatch.setattr('auth.services.auth_service.verify_otp', _invalid_otp)

    original_redis = app.state.redis
    app.state.redis = _FakeRedis()
    try:
        reset = await api_client.post(
            '/api/auth/reset-password',
            json={'email': email, 'code': '123456', 'new_password': 'NewStrong!123'},
        )
        assert reset.status_code == 400
        assert reset.json().get('detail') == 'Invalid or expired reset code'
    finally:
        app.state.redis = original_redis


@pytest.mark.asyncio
async def test_auth_db_outage_and_recovery(api_client):
    run_id = int(time.time() * 1000)
    payload = {
        'email': f'db_out_{run_id}@example.com',
        'username': f'db_out_{run_id}',
        'password': 'Strong!123',
    }

    original_factory = app.state.db_session_factory
    app.state.db_session_factory = None
    try:
        register = await api_client.post('/api/auth/register', json=payload)
        assert register.status_code == 503
        assert register.json().get('detail') == 'Database unavailable'
    finally:
        app.state.db_session_factory = original_factory

    recovered = await api_client.post('/api/auth/register', json=payload)
    assert recovered.status_code == 201


@pytest.mark.asyncio
async def test_stats_topic_breakdown_and_daily_trend_contract(api_client):
    run_id = int(time.time() * 1000)
    email = f'viz_{run_id}@example.com'
    username = f'viz_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201
    token = register.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    topic_breakdown = await api_client.get('/api/auth/stats/topic-breakdown', headers=headers)
    assert topic_breakdown.status_code == 200
    tb = topic_breakdown.json()
    assert set(tb.keys()) == {'topics'}
    assert isinstance(tb['topics'], list)
    assert len(tb['topics']) == 3
    expected_topic_keys = {
        'topic',
        'total_questions',
        'correct_questions',
        'accuracy',
        'hints_used',
        'avg_time_seconds',
    }
    for item in tb['topics']:
        assert set(item.keys()) == expected_topic_keys

    daily_trend = await api_client.get('/api/auth/stats/daily-trend?days=7', headers=headers)
    assert daily_trend.status_code == 200
    dt = daily_trend.json()
    assert set(dt.keys()) == {'days', 'points'}
    assert dt['days'] == 7
    assert isinstance(dt['points'], list)
    assert len(dt['points']) == 7
    expected_point_keys = {
        'date',
        'total_questions',
        'correct_questions',
        'accuracy',
        'avg_time_seconds',
    }
    for point in dt['points']:
        assert set(point.keys()) == expected_point_keys


@pytest.mark.asyncio
async def test_stats_redis_ops_contract_and_fallback(api_client):
    run_id = int(time.time() * 1000)
    email = f'ops_{run_id}@example.com'
    username = f'ops_{run_id}'

    register = await api_client.post(
        '/api/auth/register',
        json={'email': email, 'username': username, 'password': 'Strong!123'},
    )
    assert register.status_code == 201
    token = register.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    ops = await api_client.get('/api/auth/stats/redis-ops', headers=headers)
    assert ops.status_code == 200
    payload = ops.json()
    expected_keys = {
        'status',
        'active_sessions',
        'session_ttl_buckets',
        'otp_keys',
        'rate_limit_keys',
        'revoked_token_keys',
    }
    assert set(payload.keys()) == expected_keys
    assert isinstance(payload['session_ttl_buckets'], dict)

    original_redis = app.state.redis
    app.state.redis = None
    try:
        ops_fallback = await api_client.get('/api/auth/stats/redis-ops', headers=headers)
        assert ops_fallback.status_code == 200
        fb = ops_fallback.json()
        assert fb['status'] == 'in-memory-fallback'
        assert fb['active_sessions'] == 0
    finally:
        app.state.redis = original_redis
