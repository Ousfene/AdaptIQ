#!/usr/bin/env python3
"""Diagnose 422 validation errors in answer and hint endpoints."""

import asyncio
import httpx
import json
from uuid import uuid4

BASE_URL = "http://localhost:8000/api"

async def diagnose():
    async with httpx.AsyncClient() as client:
        print("="*80)
        print("PHASE 1: Register & Login")
        print("="*80)

        user_email = f"test_{uuid4().hex[:8]}@example.com"
        reg_resp = await client.post(
            f"{BASE_URL}/auth/register",
            json={
                "username": f"user_{uuid4().hex[:8]}",
                "email": user_email,
                "password": "TestPass123!"
            }
        )
        print(f"Register: {reg_resp.status_code}")

        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": user_email, "password": "TestPass123!"}
        )
        print(f"Login: {login_resp.status_code}")
        token = login_resp.json()["access_token"]
        user_id = login_resp.json()["user"]["id"]
        print(f"User ID: {user_id}")

        # Create authenticated client
        auth_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})

        print("\n" + "="*80)
        print("PHASE 2: Start Session & Get Question")
        print("="*80)

        start_resp = await auth_client.post(
            f"{BASE_URL}/rooms/classic/start",
            json={"topic": "history"}
        )
        print(f"Start Session: {start_resp.status_code}")
        session_id = start_resp.json()["session_id"]
        print(f"Session ID: {session_id}")

        q_resp = await auth_client.post(
            f"{BASE_URL}/rooms/classic/questions",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "topic": "history",
                "difficulty": 2
            }
        )
        print(f"Get Question: {q_resp.status_code}")
        if q_resp.status_code != 200:
            print(f"Error: {q_resp.text}")
        else:
            q_data = q_resp.json()
            question_id = q_data["id"]
            options = q_data["options"]
            print(f"Question ID: {question_id}")
            print(f"Options: {options}")

        print("\n" + "="*80)
        print("PHASE 3: Test Answer Submission (MINIMAL PAYLOAD)")
        print("="*80)

        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "question_id": question_id,
            "selected_answer": options[0] if options else "test"
        }
        print(f"Payload: {json.dumps(payload, default=str, indent=2)}")

        ans_resp = await auth_client.post(
            f"{BASE_URL}/rooms/classic/answers",
            json=payload
        )
        print(f"Response Status: {ans_resp.status_code}")
        print(f"Response Body: {ans_resp.text}")

        if ans_resp.status_code == 422:
            # Parse validation error details
            try:
                error_data = ans_resp.json()
                print("\nValidation Error Details:")
                print(json.dumps(error_data, indent=2))
            except:
                pass

        print("\n" + "="*80)
        print("PHASE 4: Test with EXPLICIT used_hint")
        print("="*80)

        payload2 = {
            "user_id": user_id,
            "session_id": session_id,
            "question_id": question_id,
            "selected_answer": options[1] if len(options) > 1 else options[0],
            "used_hint": False
        }
        print(f"Payload with used_hint: {json.dumps(payload2, default=str, indent=2)}")

        ans_resp2 = await auth_client.post(
            f"{BASE_URL}/rooms/classic/answers",
            json=payload2
        )
        print(f"Response Status: {ans_resp2.status_code}")
        if ans_resp2.status_code != 200:
            print(f"Response Body: {ans_resp2.text}")

        print("\n" + "="*80)
        print("PHASE 5: Test Hint Endpoint (WITH CORRECT FIELD NAME)")
        print("="*80)

        # Get another question for hint
        q_resp2 = await auth_client.post(
            f"{BASE_URL}/rooms/classic/questions",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "topic": "history",
                "difficulty": 2
            }
        )
        question_text = q_resp2.json()["text"]

        hint_payload_wrong = {
            "user_id": user_id,
            "session_id": session_id,
            "question_text": question_text  # WRONG: snake_case
        }
        print(f"WRONG payload (snake_case): {json.dumps(hint_payload_wrong, default=str, indent=2)}")

        hint_resp_wrong = await auth_client.post(
            f"{BASE_URL}/rooms/classic/hints",
            json=hint_payload_wrong
        )
        print(f"Response Status: {hint_resp_wrong.status_code}")
        if hint_resp_wrong.status_code != 200:
            print(f"Response Body: {hint_resp_wrong.text}")

        print()
        hint_payload_right = {
            "session_id": session_id,
            "questionText": question_text  # CORRECT: camelCase
        }
        print(f"CORRECT payload (camelCase): {json.dumps(hint_payload_right, default=str, indent=2)}")

        hint_resp_right = await auth_client.post(
            f"{BASE_URL}/rooms/classic/hints",
            json=hint_payload_right
        )
        print(f"Response Status: {hint_resp_right.status_code}")
        if hint_resp_right.status_code == 200:
            print(f"Hint: {hint_resp_right.json()['hint'][:80]}...")
        else:
            print(f"Response Body: {hint_resp_right.text}")

if __name__ == "__main__":
    asyncio.run(diagnose())
