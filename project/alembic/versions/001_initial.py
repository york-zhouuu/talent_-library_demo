"""Initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create candidates table
    op.create_table(
        'candidates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(20), index=True),
        sa.Column('email', sa.String(100), index=True),
        sa.Column('city', sa.String(50), index=True),
        sa.Column('current_company', sa.String(200)),
        sa.Column('current_title', sa.String(100)),
        sa.Column('years_of_experience', sa.Float()),
        sa.Column('expected_salary', sa.Float()),
        sa.Column('skills', sa.Text()),
        sa.Column('summary', sa.Text()),
        sa.Column('embedding', Vector(1536)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create tags table
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, index=True, nullable=False),
        sa.Column('category', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Create talent_pools table
    op.create_table(
        'talent_pools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), index=True, nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('is_public', sa.Boolean(), default=False),
        sa.Column('owner_id', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create resumes table
    op.create_table(
        'resumes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(200), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False),
        sa.Column('raw_text', sa.Text()),
        sa.Column('parsed_data', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Create association tables
    op.create_table(
        'candidate_tags',
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'candidate_pools',
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('talent_pools.id', ondelete='CASCADE'), primary_key=True),
    )

    # Create vector index for semantic search
    op.execute('''
        CREATE INDEX IF NOT EXISTS candidates_embedding_idx
        ON candidates
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    ''')


def downgrade() -> None:
    op.drop_table('candidate_pools')
    op.drop_table('candidate_tags')
    op.drop_table('resumes')
    op.drop_table('talent_pools')
    op.drop_table('tags')
    op.drop_table('candidates')
