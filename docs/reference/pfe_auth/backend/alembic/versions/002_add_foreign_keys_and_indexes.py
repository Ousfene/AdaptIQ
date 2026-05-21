"""Add foreign keys and performance indexes

Revision ID: 002
Revises: 001
Create Date: 2026-03-22

This migration:
1. Adds foreign key constraints for referential integrity and cascade deletes
2. Adds missing performance indexes for frequently-queried columns
3. Preserves all existing data (safe migration)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add foreign key constraints ────────────────────────────────────────

    # user_responses.user_id → users.id (CASCADE DELETE)
    op.create_foreign_key(
        "fk_user_responses_user_id",
        "user_responses",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # user_responses.question_id → question_bank.id (CASCADE DELETE)
    op.create_foreign_key(
        "fk_user_responses_question_id",
        "user_responses",
        "question_bank",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── Add missing performance indexes ────────────────────────────────────

    # Index on question_id for recalibration queries that filter by question
    op.create_index(
        "ix_user_responses_question_id",
        "user_responses",
        ["question_id"],
    )

    # Index on created_at for time-based analytics and trend queries
    op.create_index(
        "ix_user_responses_created_at",
        "user_responses",
        ["created_at"],
    )

    # Index on username for registration validation (uniqueness verification)
    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )

    # Index on difficulty_irt alone for range queries (in addition to composite)
    op.create_index(
        "ix_question_bank_difficulty_irt",
        "question_bank",
        ["difficulty_irt"],
    )


def downgrade() -> None:
    # ── Drop indexes ──────────────────────────────────────────────────────
    op.drop_index("ix_question_bank_difficulty_irt", table_name="question_bank")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_user_responses_created_at", table_name="user_responses")
    op.drop_index("ix_user_responses_question_id", table_name="user_responses")

    # ── Drop foreign keys ─────────────────────────────────────────────────
    op.drop_constraint(
        "fk_user_responses_question_id",
        "user_responses",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_user_responses_user_id",
        "user_responses",
        type_="foreignkey",
    )
