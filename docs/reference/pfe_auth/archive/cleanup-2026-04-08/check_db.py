#!/usr/bin/env python
"""Check database for questions and concept links."""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_database():
    """Query database to check questions and concept links."""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://pfe:pfe@localhost:5433/adaptive_learning"
    )
    
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # Count total questions
        result = await conn.execute(text("SELECT COUNT(*) FROM question_bank"))
        total_q = result.scalar()
        print(f"Total questions in question_bank: {total_q}")
        
        # Count total concept links
        result = await conn.execute(text("SELECT COUNT(*) FROM question_concepts"))
        total_links = result.scalar()
        print(f"Total links in question_concepts: {total_links}")
        
        # Count questions with at least one concept link
        result = await conn.execute(text("""
            SELECT COUNT(DISTINCT question_id) 
            FROM question_concepts
        """))
        q_with_links = result.scalar()
        print(f"Questions with at least one concept link: {q_with_links}")
        
        # Count concepts
        result = await conn.execute(text("SELECT COUNT(*) FROM concepts"))
        total_concepts = result.scalar()
        print(f"Total concepts: {total_concepts}")
        
        # Show some questions and their concepts
        print("\n___ Sample Questions with Concepts ___")
        result = await conn.execute(text("""
            SELECT DISTINCT
                qb.id as question_id,
                qb.question_text,
                qb.topic,
                COUNT(qc.concept_id) as concept_count
            FROM question_bank qb
            LEFT JOIN question_concepts qc ON qb.id = qc.question_id
            GROUP BY qb.id
            LIMIT 5
        """))
        for row in result:
            print(f"Q: {str(row[0])[:8]}... Topic: {row[2]} Concepts: {row[3]}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_database())
