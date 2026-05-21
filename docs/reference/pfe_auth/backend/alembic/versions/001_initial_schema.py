"""Initial schema — users, user_responses, question_bank

Revision ID: 001
Revises: 
Create Date: 2026-03-14

NOTE: If your database already has these tables (created by SQLAlchemy's
      create_all on an earlier run), stamp this migration as applied instead
      of running it:

          cd backend
          alembic stamp 001

      For a brand-new database, run normally:

          alembic upgrade head
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("points", sa.Integer(), server_default="0"),
        sa.Column("level", sa.String(30), server_default="Novice"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── user_responses ────────────────────────────────────────────────────
    op.create_table(
        "user_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(20), nullable=False),
        sa.Column("difficulty_sent", sa.Integer(), nullable=False),
        sa.Column("answered_correct", sa.Boolean(), nullable=False),
        sa.Column("time_taken", sa.Integer(), nullable=False),
        sa.Column("used_hint", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_user_responses_user_id", "user_responses", ["user_id"])
    op.create_index("ix_user_responses_session_id", "user_responses", ["session_id"])
    op.create_index(
        "ix_user_responses_user_topic", "user_responses", ["user_id", "topic"]
    )

    # ── question_bank ─────────────────────────────────────────────────────
    op.create_table(
        "question_bank",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(20), nullable=False),
        sa.Column("difficulty_irt", sa.Float(), server_default="2.5"),
        sa.Column("discrimination", sa.Float(), server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("source", sa.String(30), server_default="llm"),
    )
    op.create_index("ix_question_bank_topic", "question_bank", ["topic"])
    op.create_index(
        "ix_question_bank_topic_diff", "question_bank", ["topic", "difficulty_irt"]
    )


def downgrade() -> None:
    op.drop_table("question_bank")
    op.drop_table("user_responses")
    op.drop_table("users")
