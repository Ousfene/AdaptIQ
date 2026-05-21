"""Add Challenge Room and Classic Session tables.

Revision ID: 006
Revises: 005_add_concept_discovery_tracking
Create Date: 2026-03-31

Adds:
- elo_global column to users
- hint and times_seen columns to question_bank
- user_concept_repeat_queue table
- classic_sessions table
- challenge_ranks table
- user_challenge_rank table
- challenge_matches table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # Add elo_global to users (idempotent)
    if not column_exists('users', 'elo_global'):
        op.add_column('users', sa.Column('elo_global', sa.Float(), nullable=False, server_default='0.0'))

    # Add hint and times_seen to question_bank (idempotent)
    if not column_exists('question_bank', 'hint'):
        op.add_column('question_bank', sa.Column('hint', sa.Text(), nullable=True))
    if not column_exists('question_bank', 'times_seen'):
        op.add_column('question_bank', sa.Column('times_seen', sa.Integer(), nullable=False, server_default='0'))

    # Create user_concept_repeat_queue (idempotent)
    if not table_exists('user_concept_repeat_queue'):
        op.create_table(
            'user_concept_repeat_queue',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('concept_id', UUID(as_uuid=True), sa.ForeignKey('concepts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('question_bank.id', ondelete='CASCADE'), nullable=False),
            sa.Column('repeat_probability', sa.Float(), nullable=False, server_default='0.5'),
            sa.Column('due_after_session', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_repeat_queue_user_due', 'user_concept_repeat_queue', ['user_id', 'due_after_session'])
        op.create_index('ix_repeat_queue_user', 'user_concept_repeat_queue', ['user_id'])
        op.create_index('ix_repeat_queue_concept', 'user_concept_repeat_queue', ['concept_id'])
        op.create_index('ix_repeat_queue_question', 'user_concept_repeat_queue', ['question_id'])

    # Create classic_sessions (idempotent)
    if not table_exists('classic_sessions'):
        op.create_table(
            'classic_sessions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('topic', sa.String(20), nullable=False),
            sa.Column('questions_answered', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('correct_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_classic_sessions_user', 'classic_sessions', ['user_id'])

    # Create challenge_ranks (idempotent)
    if not table_exists('challenge_ranks'):
        op.create_table(
            'challenge_ranks',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(50), unique=True, nullable=False),
            sa.Column('min_elo', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('n_options', sa.Integer(), nullable=False, server_default='4'),
            sa.Column('has_timer', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('timer_seconds', sa.Integer(), nullable=True),
        )

        # Seed challenge ranks
        op.execute("""
            INSERT INTO challenge_ranks (id, name, min_elo, n_options, has_timer, timer_seconds)
            VALUES
                (1, 'Bronze', 0.0, 2, false, NULL),
                (2, 'Silver', 0.5, 4, false, NULL),
                (3, 'Gold', 1.0, 4, true, 45),
                (4, 'Platinum', 1.5, 4, true, 30),
                (5, 'Diamond', 2.0, 4, true, 25)
        """)

    # Create user_challenge_rank (idempotent)
    if not table_exists('user_challenge_rank'):
        op.create_table(
            'user_challenge_rank',
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('current_rank_id', sa.Integer(), sa.ForeignKey('challenge_ranks.id'), nullable=False, server_default='1'),
            sa.Column('wins', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('losses', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('skip_attempts_remaining', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('last_skip_at', sa.DateTime(), nullable=True),
        )

    # Create challenge_matches (idempotent)
    if not table_exists('challenge_matches'):
        op.create_table(
            'challenge_matches',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('rank_id', sa.Integer(), sa.ForeignKey('challenge_ranks.id'), nullable=False),
            sa.Column('questions_answered', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('score', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('time_taken', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('result', sa.String(20), nullable=False, server_default="'incomplete'"),
            sa.Column('is_skip_attempt', sa.Boolean(), nullable=False, server_default='false'),
        )
        op.create_index('ix_challenge_matches_user', 'challenge_matches', ['user_id'])
        op.create_index('ix_challenge_matches_result', 'challenge_matches', ['result'])


def downgrade() -> None:
    if table_exists('challenge_matches'):
        op.drop_table('challenge_matches')
    if table_exists('user_challenge_rank'):
        op.drop_table('user_challenge_rank')
    if table_exists('challenge_ranks'):
        op.drop_table('challenge_ranks')
    if table_exists('classic_sessions'):
        op.drop_table('classic_sessions')
    if table_exists('user_concept_repeat_queue'):
        op.drop_table('user_concept_repeat_queue')
    if column_exists('question_bank', 'times_seen'):
        op.drop_column('question_bank', 'times_seen')
    if column_exists('question_bank', 'hint'):
        op.drop_column('question_bank', 'hint')
    if column_exists('users', 'elo_global'):
        op.drop_column('users', 'elo_global')
