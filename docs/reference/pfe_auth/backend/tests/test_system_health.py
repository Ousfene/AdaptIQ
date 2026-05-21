import pytest


@pytest.mark.asyncio
async def test_health_endpoint_shape(api_client):
    response = await api_client.get('/api/system/health')
    assert response.status_code == 200

    payload = response.json()
    assert payload['status'] == 'ok'
    assert 'services' in payload
    assert 'database' in payload['services']
    assert 'redis' in payload['services']
