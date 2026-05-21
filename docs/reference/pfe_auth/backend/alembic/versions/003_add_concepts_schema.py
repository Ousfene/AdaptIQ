"""Add concepts schema for per-concept IRT tracking

Revision ID: 003
Revises: 002
Create Date: 2026-03-22

This migration:
1. Creates concepts table (knowledge domains like "Roman Empire", "Egyptian History")
2. Creates question_concepts table (many-to-many: questions → concepts)
3. Creates user_concept_theta table (per-user, per-concept IRT ability tracking)
4. Adds primary_concept_id column to question_bank for fast lookups
5. Adds necessary foreign keys and indexes
6. Preserves all existing data (safe migration for production)

Feature: Concept-Based Adaptive Learning
- Enables per-concept ability tracking instead of global theta
- Allows smart question reuse (same question at different difficulties)
- Provides concept mastery breakdown in dashboard
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create concepts table ─────────────────────────────────────────────────
    op.create_table(
        "concepts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("topic", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_concepts_name", "concepts", ["name"], unique=False)
    op.create_index("ix_concepts_topic", "concepts", ["topic"], unique=False)

    # ── Create question_concepts table (many-to-many) ──────────────────────────
    op.create_table(
        "question_concepts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["question_bank.id"],
            name="fk_question_concepts_question_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name="fk_question_concepts_concept_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "concept_id", name="uq_question_concepts_unique"),
    )
    op.create_index("ix_question_concepts_question", "question_concepts", ["question_id"], unique=False)
    op.create_index("ix_question_concepts_concept", "question_concepts", ["concept_id"], unique=False)

    # ── Create user_concept_theta table (per-user, per-concept IRT) ────────────
    op.create_table(
        "user_concept_theta",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.Column("theta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("theta_variance", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("response_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("theta >= -3.0 AND theta <= 3.0", name="ck_user_concept_theta_range"),
        sa.CheckConstraint("theta_variance > 0.0", name="ck_user_concept_theta_variance_positive"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_concept_theta_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name="fk_user_concept_theta_concept_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "concept_id", name="uq_user_concept_unique"),
    )
    op.create_index("ix_user_concept_theta_user", "user_concept_theta", ["user_id"], unique=False)
    op.create_index("ix_user_concept_theta_concept", "user_concept_theta", ["concept_id"], unique=False)
    op.create_index("ix_user_concept_theta_updated", "user_concept_theta", ["last_updated"], unique=False)

    # ── Add primary_concept_id column to question_bank ────────────────────────
    op.add_column(
        "question_bank",
        sa.Column("primary_concept_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_question_bank_primary_concept_id",
        "question_bank",
        "concepts",
        ["primary_concept_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_question_bank_primary_concept", "question_bank", ["primary_concept_id"], unique=False)


def downgrade() -> None:
    # ── Drop question_bank changes ─────────────────────────────────────────────
    op.drop_index("ix_question_bank_primary_concept", table_name="question_bank")
    op.drop_constraint(
        "fk_question_bank_primary_concept_id",
        "question_bank",
        type_="foreignkey",
    )
    op.drop_column("question_bank", "primary_concept_id")

    # ── Drop user_concept_theta table ──────────────────────────────────────────
    op.drop_index("ix_user_concept_theta_updated", table_name="user_concept_theta")
    op.drop_index("ix_user_concept_theta_concept", table_name="user_concept_theta")
    op.drop_index("ix_user_concept_theta_user", table_name="user_concept_theta")
    op.drop_table("user_concept_theta")

    # ── Drop question_concepts table ───────────────────────────────────────────
    op.drop_index("ix_question_concepts_concept", table_name="question_concepts")
    op.drop_index("ix_question_concepts_question", table_name="question_concepts")
    op.drop_table("question_concepts")

    # ── Drop concepts table ────────────────────────────────────────────────────
    op.drop_index("ix_concepts_topic", table_name="concepts")
    op.drop_index("ix_concepts_name", table_name="concepts")
    op.drop_table("concepts")
