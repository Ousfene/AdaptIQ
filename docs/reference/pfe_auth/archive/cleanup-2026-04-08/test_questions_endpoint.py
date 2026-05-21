#!/usr/bin/env python3
"""Detailed test of the classic room questions endpoint with error capture."""

import httpx
import json
import asyncio
import uuid
import sys

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create fresh user
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        username = f"test_{uuid.uuid4().hex[:8]}"
        password = "TestPassword123!"

        # 1. Register
        reg = await client.post(
            "http://localhost:8000/api/auth/register",
            json={"email": email, "username": username, "password": password}
        )
        print(f"[1/5] Register: {reg.status_code}")
        if reg.status_code != 201:
            print(f"  ERROR: {reg.text}")
            return

        # 2. Login
        login = await client.post(
            "http://localhost:8000/api/auth/login",
            json={"email": email, "password": password}
        )
        print(f"[2/5] Login: {login.status_code}")
        if login.status_code != 200:
            print(f"  ERROR: {login.text}")
            return

        data = login.json()
        user_id = data["user"]["id"]
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print(f"     User ID: {user_id}")

        # 3. Start session
        start = await client.post(
            "http://localhost:8000/api/rooms/classic/start",
            json={"topic": "history"},
            headers=headers
        )
        print(f"[3/5] Start session: {start.status_code}")
        if start.status_code != 200:
            print(f"  ERROR: {start.text}")
            return

        session_data = start.json()
        session_id = session_data["session_id"]
        first_q = session_data.get("first_question")
        print(f"     Session ID: {session_id}")
        if first_q:
            print(f"     First question received: {first_q['text'][:60]}...")

        # 4. Request next question (this is where it fails)
        print(f"\n[4/5] Testing /questions endpoint:")
        print(f"     Sending: user_id={user_id}, session_id={session_id}")

        q_resp = await client.post(
            "http://localhost:8000/api/rooms/classic/questions",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "topic": "history",
                "difficulty": 2
            },
            headers=headers
        )

        print(f"     Response status: {q_resp.status_code}")

        if q_resp.status_code == 200:
            print("     SUCCESS!")
            q_data = q_resp.json()
            print(f"     Question: {q_data.get('text')[:100]}")
        else:
            print(f"     FAILED with status {q_resp.status_code}")
            print(f"     Response text: {q_resp.text[:2000]}")

            # Try to extract useful error info
            try:
                error_data = q_resp.json()
                if "detail" in error_data:
                    print(f"     Detail: {error_data['detail']}")
            except:
                pass

if __name__ == "__main__":
    asyncio.run(main())
