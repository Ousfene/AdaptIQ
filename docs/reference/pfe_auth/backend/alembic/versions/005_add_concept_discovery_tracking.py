"""Add first_seen_at and exposure_count tracking for concept auto-discovery."""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add first_seen_at column to track when user first encountered a concept
    op.add_column(
        'user_concept_theta',
        sa.Column('first_seen_at', sa.DateTime(), nullable=True)
    )
    # Add exposure_count to track how many times concept was shown to user
    op.add_column(
        'user_concept_theta',
        sa.Column('exposure_count', sa.Integer(), server_default='0', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('user_concept_theta', 'exposure_count')
    op.drop_column('user_concept_theta', 'first_seen_at')
