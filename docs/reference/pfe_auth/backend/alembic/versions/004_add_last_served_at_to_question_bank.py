"""Add last_served_at tracking to question_bank for cache metrics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_served_at column to track cache usage
    op.add_column(
        'question_bank',
        sa.Column('last_served_at', sa.DateTime(), nullable=True)
    )
    # Add index for cache invalidation queries
    op.create_index(
        'ix_question_bank_last_served',
        'question_bank',
        ['last_served_at']
    )


def downgrade() -> None:
    op.drop_index('ix_question_bank_last_served', table_name='question_bank')
    op.drop_column('question_bank', 'last_served_at')
