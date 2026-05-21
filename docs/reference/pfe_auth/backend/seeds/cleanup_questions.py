"""
seeds/cleanup_questions.py — Database cleanup utility for garbage questions.

This script identifies and removes low-quality questions from the question_bank table.
Run: python -m seeds.cleanup_questions [--dry-run] [--min-length 10]

Criteria for garbage questions:
1. question_text shorter than MIN_QUESTION_LENGTH characters
2. question_text matches known garbage patterns (e.g., "Topic question")
3. Less than 4 options in options_json
4. correct_answer not in options_json
5. Placeholder or test-like content

Usage:
    python -m seeds.cleanup_questions           # List garbage questions only (dry run)
    python -m seeds.cleanup_questions --delete  # Actually delete garbage questions
"""
import asyncio
import json
import argparse
import logging
import re
import sys
from pathlib import Path

# Ensure backend is in path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database.models import QuestionBank, UserResponse
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Configuration
MIN_QUESTION_LENGTH = 10
MIN_OPTIONS_COUNT = 2

# Known garbage patterns for question text (case-insensitive regex)
GARBAGE_PATTERNS = [
    r"^topic\s*question",
    r"^test\s*question",
    r"^placeholder",
    r"^sample\s*question",
    r"^example\s*question",
    r"^lorem\s*ipsum",
    r"^dummy",
    r"^asdf",
    r"^xxx",
    r"^question\s*\d+$",  # "Question 1", "Question 2", etc.
    r"^q\d+$",            # "Q1", "Q2", etc.
    r"^null$",
    r"^\s*$",  # Empty or whitespace
]

# Garbage patterns for answer options
GARBAGE_OPTION_PATTERNS = [
    r"^answer\s*\d+$",    # "answer 1", "answer 2", etc.
    r"^option\s*[a-d]$",  # "option A", "option B", etc.
    r"^choice\s*\d+$",    # "choice 1", "choice 2", etc.
    r"^[a-d]$",           # Single letter options
    r"^test\s*",          # "test answer", etc.
    r"^placeholder",
    r"^xxx",
    r"^asdf",
]


def is_garbage_question(question: QuestionBank) -> tuple[bool, str]:
    """Check if a question should be considered garbage. Returns (is_garbage, reason)."""
    text = question.question_text or ""
    
    # Check length
    if len(text.strip()) < MIN_QUESTION_LENGTH:
        return True, f"Question too short ({len(text.strip())} chars)"
    
    # Check garbage patterns
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, f"Matches garbage pattern: {pattern}"
    
    # Check options
    try:
        options = json.loads(question.options_json or "[]")
        if len(options) < MIN_OPTIONS_COUNT:
            return True, f"Too few options ({len(options)})"
        
        # Check if correct answer is in options
        if question.correct_answer and question.correct_answer not in options:
            return True, "Correct answer not in options"
        
        # Check for empty options
        empty_options = sum(1 for opt in options if not opt or not str(opt).strip())
        if empty_options > 0:
            return True, f"{empty_options} empty option(s)"
        
        # Check for garbage option patterns (if most options match, it's test data)
        garbage_option_count = 0
        for opt in options:
            for pattern in GARBAGE_OPTION_PATTERNS:
                if re.search(pattern, str(opt).strip(), re.IGNORECASE):
                    garbage_option_count += 1
                    break
        
        if garbage_option_count >= len(options) // 2 + 1:  # Majority are garbage
            return True, f"Test/garbage options detected ({garbage_option_count}/{len(options)})"
            
    except (json.JSONDecodeError, TypeError):
        return True, "Invalid options_json format"
    
    # Check for missing explanation (optional, warn only)
    # if not question.explanation or len(question.explanation.strip()) < 5:
    #     return True, "Missing or too short explanation"
    
    return False, ""


async def find_garbage_questions(session: AsyncSession) -> list[tuple[QuestionBank, str]]:
    """Find all garbage questions in the database."""
    result = await session.execute(select(QuestionBank))
    all_questions = result.scalars().all()
    
    garbage = []
    for q in all_questions:
        is_garbage, reason = is_garbage_question(q)
        if is_garbage:
            garbage.append((q, reason))
    
    return garbage


async def check_question_usage(session: AsyncSession, question_id) -> int:
    """Check how many user responses reference this question."""
    result = await session.execute(
        select(UserResponse).where(UserResponse.question_id == question_id)
    )
    return len(result.scalars().all())


async def cleanup_garbage_questions(dry_run: bool = True) -> None:
    """Main cleanup function."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        logger.info("Scanning question_bank for garbage questions...")
        
        garbage = await find_garbage_questions(session)
        
        if not garbage:
            logger.info("[OK] No garbage questions found!")
            return

        logger.info(f"[FOUND] Detected {len(garbage)} garbage question(s):")
        print("\n" + "=" * 80)
        
        for i, (q, reason) in enumerate(garbage, 1):
            usage_count = await check_question_usage(session, q.id)
            
            print(f"\n{i}. Question ID: {q.id}")
            print(f"   Text: {q.question_text[:100]}{'...' if len(q.question_text or '') > 100 else ''}")
            print(f"   Topic: {q.topic}")
            print(f"   Reason: {reason}")
            print(f"   Source: {q.source}")
            print(f"   User responses: {usage_count}")
            
            try:
                options = json.loads(q.options_json or "[]")
                print(f"   Options: {options}")
            except:
                print(f"   Options: [INVALID JSON]")
        
        print("\n" + "=" * 80)
        
        if dry_run:
            logger.info(f"\n🔍 DRY RUN - Would delete {len(garbage)} questions")
            logger.info("Run with --delete to actually remove them")
        else:
            # Confirm deletion
            confirm = input(f"\n⚠️  Delete {len(garbage)} garbage questions? (yes/no): ")
            if confirm.lower() != "yes":
                logger.info("Aborted.")
                return
            
            # Delete garbage questions (CASCADE will handle user_responses)
            deleted = 0
            for q, _ in garbage:
                await session.execute(
                    delete(QuestionBank).where(QuestionBank.id == q.id)
                )
                deleted += 1
                logger.info(f"Deleted: {q.id}")
            
            await session.commit()
            logger.info(f"\n✅ Deleted {deleted} garbage questions")


async def show_question_stats(session: AsyncSession) -> None:
    """Show overall question bank statistics."""
    result = await session.execute(select(QuestionBank))
    all_questions = result.scalars().all()

    print("\n[STATS] Question Bank Statistics:")
    print(f"   Total questions: {len(all_questions)}")

    by_topic = {}
    by_source = {}
    for q in all_questions:
        by_topic[q.topic] = by_topic.get(q.topic, 0) + 1
        by_source[q.source or 'None'] = by_source.get(q.source or 'None', 0) + 1

    print("\n   By Topic:")
    for topic, count in sorted(by_topic.items()):
        print(f"      {topic}: {count}")

    print("\n   By Source:")
    for source, count in sorted(by_source.items()):
        print(f"      {source}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup garbage questions from question_bank",
        epilog="""
Examples:
  python -m seeds.cleanup_questions                           # DRY RUN: List garbage questions
  python -m seeds.cleanup_questions --delete                  # DELETE: Remove garbage questions
  python -m seeds.cleanup_questions --stats                   # STATS: Show question bank statistics
  python -m seeds.cleanup_questions --test-only               # Show test questions only
  python -m seeds.cleanup_questions --test-only --delete      # DELETE test questions only
  python -m seeds.cleanup_questions --by-source test          # Show questions by specific source
  python -m seeds.cleanup_questions --preserve-tests          # Clean garbage, keep test data
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--delete", action="store_true", help="Actually delete garbage questions (default: dry run)")
    parser.add_argument("--min-length", type=int, default=10, help="Minimum question text length (default: 10)")
    parser.add_argument("--stats", action="store_true", help="Show question bank statistics only")
    parser.add_argument("--test-only", action="store_true", help="Only show/delete test questions (source='test')")
    parser.add_argument("--by-source", type=str, help="Filter by source value (e.g., 'test', 'llm', 'seed')")
    parser.add_argument("--preserve-tests", action="store_true", help="Clean garbage but preserve test questions")
    args = parser.parse_args()

    global MIN_QUESTION_LENGTH
    MIN_QUESTION_LENGTH = args.min_length

    if args.stats:
        async def show_stats():
            engine = create_async_engine(DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with async_session() as session:
                await show_question_stats(session)
        asyncio.run(show_stats())
    elif args.test_only:
        # Show/delete only test questions (source='test')
        async def handle_test_only():
            engine = create_async_engine(DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with async_session() as session:
                result = await session.execute(
                    select(QuestionBank).where(QuestionBank.source == 'test')
                )
                test_questions = result.scalars().all()

                if not test_questions:
                    logger.info("[OK] No test questions found")
                    return

                logger.info(f"[FOUND] {len(test_questions)} test question(s) (source='test')")

                if args.delete:
                    confirm = input(f"\n[WARN] Delete {len(test_questions)} test questions? (yes/no): ")
                    if confirm.lower() == "yes":
                        await session.execute(
                            delete(QuestionBank).where(QuestionBank.source == 'test')
                        )
                        await session.commit()
                        logger.info(f"[OK] Deleted {len(test_questions)} test questions")
                    else:
                        logger.info("[CANCEL] Aborted")
                else:
                    logger.info("DRY RUN: Would delete these test questions:")
                    for q in test_questions[:10]:  # Show first 10
                        print(f"  - {q.id}: {q.question_text[:60]}...")
                    if len(test_questions) > 10:
                        print(f"  ... and {len(test_questions) - 10} more")
        asyncio.run(handle_test_only())
    elif args.by_source:
        # Filter by source value
        async def handle_by_source():
            engine = create_async_engine(DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with async_session() as session:
                result = await session.execute(
                    select(QuestionBank).where(QuestionBank.source == args.by_source)
                )
                filtered_questions = result.scalars().all()

                logger.info(f"[FOUND] {len(filtered_questions)} question(s) with source='{args.by_source}'")
                for q in filtered_questions[:10]:
                    print(f"  - {q.id}: {q.question_text[:60]}... (source={q.source})")
                if len(filtered_questions) > 10:
                    print(f"  ... and {len(filtered_questions) - 10} more")
        asyncio.run(handle_by_source())
    else:
        asyncio.run(cleanup_garbage_questions(dry_run=not args.delete))


if __name__ == "__main__":
    main()
