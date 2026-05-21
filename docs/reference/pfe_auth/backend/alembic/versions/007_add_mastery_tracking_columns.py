"""Add mastery tracking columns to user_concept_theta.

These columns are required for tracking user progress through concepts:
- mastery_level: BEGINNER, LEARNING, PROFICIENT, ADVANCED
- last_played_at: When this concept was last practiced
- updated_at: Schema timestamp
- concept_state: EXPLORING, LEARNING, MASTERED

Revision ID: 007
Revises: 006
Create Date: 2024-03-31
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check and add mastery_level column
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_concept_theta')]
    
    if 'mastery_level' not in columns:
        op.add_column(
            'user_concept_theta',
            sa.Column('mastery_level', sa.String(20), server_default='BEGINNER', nullable=False)
        )
    
    if 'last_played_at' not in columns:
        op.add_column(
            'user_concept_theta',
            sa.Column('last_played_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
        )
    
    if 'updated_at' not in columns:
        op.add_column(
            'user_concept_theta',
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
        )
    
    if 'concept_state' not in columns:
        op.add_column(
            'user_concept_theta',
            sa.Column('concept_state', sa.String(20), server_default='EXPLORING', nullable=False)
        )


def downgrade() -> None:
    # Only drop if they exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_concept_theta')]
    
    if 'concept_state' in columns:
        op.drop_column('user_concept_theta', 'concept_state')
    if 'updated_at' in columns:
        op.drop_column('user_concept_theta', 'updated_at')
    if 'last_played_at' in columns:
        op.drop_column('user_concept_theta', 'last_played_at')
    if 'mastery_level' in columns:
        op.drop_column('user_concept_theta', 'mastery_level')
