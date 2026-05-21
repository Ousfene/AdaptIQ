#!/usr/bin/env python
"""Test first question generation - simple version without emoji."""

import asyncio
import httpx
import json
import uuid

async def test_first_question():
    """Test that the first question is returned from backend."""
    async with httpx.AsyncClient() as client:
        try:
            # Step 1: Register a test user
            user_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
            print(f"Registering user: {user_email}")
            register_resp = await client.post(
                "http://localhost:8000/api/auth/register",
                json={
                    "email": user_email,
                    "username": f"user_{uuid.uuid4().hex[:8]}",
                    "password": "TestPassword123!"
                },
                timeout=10
            )
            print(f"Register: {register_resp.status_code}")
            if register_resp.status_code != 201:
                print(f"  Error: {register_resp.text}")
                return False
            
            user_data = register_resp.json()
            user_id = user_data.get("user", {}).get("id")
            token = user_data.get("access_token")
            print(f"  User ID: {user_id}")
            
            # Step 2: Start a classic session
            print(f"\nStarting classic room session...")
            session_resp = await client.post(
                "http://localhost:8000/api/rooms/classic/start",
                json={"topic": "history"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            print(f"Start Session: {session_resp.status_code}")
            if session_resp.status_code != 200:
                print(f"  Error: {session_resp.text}")
                return False
            
            session_data = session_resp.json()
            print(f"Response keys: {session_data.keys()}")
            print(f"full response: {json.dumps(session_data, indent=2)}")
            
            first_question = session_data.get("first_question")
            print(f"\nFirst question value: {first_question}")
            
            if not first_question:
                print("ERROR: No first_question in response!")
                return False
            
            print(f"\nFirst question received:")
            print(f"  ID: {first_question.get('id')}")
            print(f"  Text: {first_question.get('text')[:80]}...")
            print(f"  Options: {len(first_question.get('options', []))} provided")
            
            print("\n[SUCCESS] First question was returned correctly!")
            return True
            
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = asyncio.run(test_first_question())
    exit(0 if success else 1)
