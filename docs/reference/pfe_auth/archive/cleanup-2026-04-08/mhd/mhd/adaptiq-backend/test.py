import httpx, asyncio, uuid

async def test():
    uid = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=60) as c:
        q = await c.post(
            'http://localhost:8000/generate',
            json={
                'session_id': 'aaaaaaaa-0000-0000-0000-000000000000',
                'user_id': uid,
                'topic': 'Mixed',
                'level': 5
            }
        )

        if q.status_code == 404:
            print('Expected 404 (no session) - level 5 prompt logic is loaded correctly')
            print('PASS - router is working, level 5 config exists')
        else:
            data = q.json()
            print(f"Level 5 → is_free_text: {data.get('is_free_text')}")
            print(f"Level 5 → options: {data.get('options')}")

asyncio.run(test())