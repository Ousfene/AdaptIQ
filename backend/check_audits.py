import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import config

async def run():
    engine = create_async_engine(config.DATABASE_URL)
    async with engine.begin() as conn:
        print("--- RECENT AUDITS ---")
        res = await conn.execute(text("SELECT created_at, room, question_text, correct_answer, options_json FROM question_audits ORDER BY created_at DESC LIMIT 10"))
        for row in res.fetchall():
            print(row)
            
        print("--- QUESTION BANK LAST 5 ---")
        res2 = await conn.execute(text("SELECT created_at, topic, question_text FROM question_bank ORDER BY created_at DESC LIMIT 5"))
        for row in res2.fetchall():
            print(row)

        print("--- VISUAL QUESTIONS LAST 5 ---")
        res3 = await conn.execute(text("SELECT created_at, topic, question_text FROM visual_questions WHERE question_text IS NOT NULL ORDER BY updated_at DESC LIMIT 5"))
        for row in res3.fetchall():
            print(row)
            
    await engine.dispose()

asyncio.run(run())
