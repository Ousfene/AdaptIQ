"""
scripts/cleanup_test_data.py — Simple CLI tool for developers to manage test data.

This script provides easy commands to view and clean up test questions from
the database without needing to remember SQL or complex flags.

Usage:
    python scripts/cleanup_test_data.py status           # Show test data count
    python scripts/cleanup_test_data.py show             # List test questions
    python scripts/cleanup_test_data.py show --limit 10  # Show 10 most recent
    python scripts/cleanup_test_data.py clean            # Interactive cleanup
    python scripts/cleanup_test_data.py clean --force    # Auto-confirm cleanup
"""

import asyncio
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Ensure backend is in path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database.models import QuestionBank
from config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


async def show_test_data_status() -> None:
    """Show count of test questions."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Count test questions
        test_count = await session.scalar(
            select(func.count(QuestionBank.id)).where(
                QuestionBank.source == "test"
            )
        )

        # Count all questions
        total_count = await session.scalar(
            select(func.count(QuestionBank.id))
        )

        print(f"\nTest Data Status:")
        print(f"  Test questions: {test_count}")
        print(f"  Total questions: {total_count}")
        print(f"  Production questions: {total_count - (test_count or 0)}")

        if test_count and test_count > 0:
            print(f"\n[WARNING] {test_count} test question(s) found")
            print(
                f"Run 'python scripts/cleanup_test_data.py clean' to remove them"
            )
        else:
            print(f"\n[OK] No test data found")

    await engine.dispose()


async def show_test_questions(limit: int = None) -> None:
    """Show test questions."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        query = select(QuestionBank).where(
            QuestionBank.source == "test"
        ).order_by(QuestionBank.created_at.desc())

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        test_questions = result.scalars().all()

        if not test_questions:
            print("\n[OK] No test questions found\n")
            return

        print(f"\nTest Questions ({len(test_questions)} total):")
        print("=" * 80)

        for i, q in enumerate(test_questions, 1):
            created = (
                q.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if q.created_at
                else "unknown"
            )
            text_preview = q.question_text[:60] + (
                "..." if len(q.question_text or "") > 60 else ""
            )
            print(f"\n{i}. {q.id}")
            print(f"   Text: {text_preview}")
            print(f"   Topic: {q.topic}")
            print(f"   Created: {created}")

        print("\n" + "=" * 80)

    await engine.dispose()


async def clean_test_data(force: bool = False) -> None:
    """Delete test questions."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Count test questions
        test_count = await session.scalar(
            select(func.count(QuestionBank.id)).where(
                QuestionBank.source == "test"
            )
        )

        if not test_count or test_count == 0:
            print("\n[OK] No test data to clean\n")
            return

        print(f"\n[WARNING] Found {test_count} test question(s)")

        if not force:
            confirm = input(
                f"\nDelete {test_count} test question(s)? (yes/no): "
            )
            if confirm.lower() != "yes":
                print("[CANCEL] Cleanup cancelled\n")
                return

        # Delete test questions
        await session.execute(
            delete(QuestionBank).where(QuestionBank.source == "test")
        )
        await session.commit()

        print(f"[OK] Deleted {test_count} test question(s)\n")

    await engine.dispose()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage test questions in the database",
        epilog="""
Examples:
  python scripts/cleanup_test_data.py status           # Show test data count
  python scripts/cleanup_test_data.py show             # List all test questions
  python scripts/cleanup_test_data.py show --limit 5   # Show 5 most recent
  python scripts/cleanup_test_data.py clean            # Delete with confirmation
  python scripts/cleanup_test_data.py clean --force    # Delete without confirmation
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status command
    subparsers.add_parser("status", help="Show test data count")

    # Show command
    show_parser = subparsers.add_parser("show", help="List test questions")
    show_parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of questions to show",
    )

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Delete test questions")
    clean_parser.add_argument(
        "--force",
        action="store_true",
        help="Delete without confirmation",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "status":
            asyncio.run(show_test_data_status())
        elif args.command == "show":
            asyncio.run(show_test_questions(limit=args.limit))
        elif args.command == "clean":
            asyncio.run(clean_test_data(force=args.force))
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
