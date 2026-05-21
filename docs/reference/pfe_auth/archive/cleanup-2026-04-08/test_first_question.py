#!/usr/bin/env python
"""Test first question generation after FK fix."""

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
            # The response structure is {'user': {...}, 'access_token': ...}
            user_id = user_data.get("user", {}).get("id") or user_data.get("user_id") or user_data.get("id")
            token = user_data.get("access_token")
            print(f"  User ID: {user_id}")
            if token:
                print(f"  Token: {token[:20]}...")
            
            # Step 2: Start a classic session
            session_resp = await client.post(
                "http://localhost:8000/api/rooms/classic/start",
                json={"topic": "history"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            print(f"\nStart Session: {session_resp.status_code}")
            if session_resp.status_code != 200:
                print(f"  Error: {session_resp.text}")
                return False
            
            session_data = session_resp.json()
            session_id = session_data.get("session_id")
            print(f"  Session ID: {session_id}")
            
            # Step 3: Request first question
            question_resp = await client.post(
                "http://localhost:8000/api/rooms/classic/questions",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "topic": "history",
                    "difficulty": 3
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=20
            )
            print(f"\nGenerate Question: {question_resp.status_code}")
            if question_resp.status_code != 200:
                print(f"  Error: {question_resp.text}")
                return False
            
            question_data = question_resp.json()
            print(f"  Question received:")
            print(f"    ID: {question_data.get('id')}")
            print(f"    Text: {question_data.get('text')[:80]}...")
            print(f"    Options: {len(question_data.get('options', []))} provided")
            print(f"    Locked: {question_data.get('locked')}")
            
            # Check that essential fields are present
            if not all([
                question_data.get('id'),
                question_data.get('text'),
                question_data.get('options'),
                'locked' in question_data
            ]):
                print("  ERROR: Missing essential fields!")
                return False
            
            print("\n✅ SUCCESS: First question was returned correctly!")
            return True
            
        except Exception as e:
            print(f"\n❌ ERROR: {type(e).__name__}: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_first_question())
    exit(0 if success else 1)
