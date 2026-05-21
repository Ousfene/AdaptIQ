"""Create test_logs table for comprehensive testing audit trail.

Stores detailed events during testing phases:
- Theta updates and IRT calculations
- Cache hit/miss operations
- Session state changes
- API calls and responses
- User interactions and analytics

Revision ID: 009
Revises: 008
Create Date: 2026-04-02 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create test_logs table with JSONB event data storage."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Only create table if it doesn't exist
    if 'test_logs' not in inspector.get_table_names():
        op.create_table(
            'test_logs',
            sa.Column('id', PG_UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()'), primary_key=True),
            sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('event_type', sa.String(50), nullable=False),
            sa.Column('user_id', PG_UUID(as_uuid=True), nullable=True),
            sa.Column('session_id', PG_UUID(as_uuid=True), nullable=True),
            sa.Column('category', sa.String(30), nullable=True),
            sa.Column('event_data', JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        )

    # Create indices using IF NOT EXISTS (PostgreSQL 9.5+)
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_test_logs_user_timestamp ON test_logs (user_id, timestamp)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_test_logs_event_type_timestamp ON test_logs (event_type, timestamp)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_test_logs_category ON test_logs (category)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_test_logs_created_at ON test_logs (created_at)'))


def downgrade() -> None:
    """Drop test_logs table and indices."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'test_logs' in inspector.get_table_names():
        # Drop indices first
        try:
            op.drop_index('ix_test_logs_created_at')
        except:
            pass
        try:
            op.drop_index('ix_test_logs_category')
        except:
            pass
        try:
            op.drop_index('ix_test_logs_event_type_timestamp')
        except:
            pass
        try:
            op.drop_index('ix_test_logs_user_timestamp')
        except:
            pass

        # Drop table
        op.drop_table('test_logs')
