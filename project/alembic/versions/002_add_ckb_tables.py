"""Add CKB (Candidate Knowledge Base) tables

Revision ID: 002
Revises: 001
Create Date: 2024-01-15

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create candidate_profiles table (Layer 2 - 派生画像)
    op.create_table(
        'candidate_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('parsed_data', sa.Text()),  # JSON: structured resume data
        sa.Column('inferred_traits', sa.Text()),  # JSON: AI-inferred personality/traits
        sa.Column('highlights', sa.Text()),  # JSON: key achievements/highlights
        sa.Column('potential_concerns', sa.Text()),  # JSON: potential red flags/concerns
        sa.Column('one_liner', sa.String(500)),  # One-line summary
        sa.Column('search_keywords', sa.Text()),  # JSON: keywords for search
        sa.Column('skills_with_confidence', sa.Text()),  # JSON: SkillEntry[] with confidence levels
        sa.Column('conflicts', sa.Text()),  # JSON: LayerConflict[] records
        sa.Column('profile_version', sa.Integer(), default=1),
        sa.Column('model_version', sa.String(50)),  # AI model version used
        sa.Column('generated_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create candidate_knowledge table (Layer 3 - 累积知识)
    op.create_table(
        'candidate_knowledge',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('status', sa.String(20), default='new'),  # new, contacted, interviewing, offered, hired, rejected, withdrawn
        sa.Column('status_history', sa.Text()),  # JSON: history of status changes
        sa.Column('contact_history', sa.Text()),  # JSON: contact attempts/results
        sa.Column('interview_feedback', sa.Text()),  # JSON: interview notes/scores
        sa.Column('recruiter_notes', sa.Text()),  # JSON: free-form notes from recruiters
        sa.Column('job_matches', sa.Text()),  # JSON: jobs this candidate was matched to
        sa.Column('skill_overrides', sa.Text()),  # JSON: human-verified/denied skills
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create candidate_session_contexts table (Layer 4 - 会话上下文)
    op.create_table(
        'candidate_session_contexts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.String(36), index=True, nullable=False),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_context_id', sa.String(36)),  # Reference to a job posting
        sa.Column('search_relevance', sa.Text()),  # JSON: why this candidate appeared in search
        sa.Column('job_fit_analysis', sa.Text()),  # JSON: detailed fit analysis for a job
        sa.Column('comparison_context', sa.Text()),  # JSON: comparison with other candidates
        sa.Column('session_notes', sa.Text()),  # JSON: notes specific to this session
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime()),  # Session contexts can expire
    )

    # Create indexes
    op.create_index('ix_candidate_profiles_candidate_id', 'candidate_profiles', ['candidate_id'])
    op.create_index('ix_candidate_knowledge_candidate_id', 'candidate_knowledge', ['candidate_id'])
    op.create_index('ix_candidate_knowledge_status', 'candidate_knowledge', ['status'])
    op.create_index('ix_candidate_session_contexts_session_id', 'candidate_session_contexts', ['session_id'])
    op.create_index('ix_candidate_session_contexts_candidate_id', 'candidate_session_contexts', ['candidate_id'])


def downgrade() -> None:
    op.drop_index('ix_candidate_session_contexts_candidate_id', 'candidate_session_contexts')
    op.drop_index('ix_candidate_session_contexts_session_id', 'candidate_session_contexts')
    op.drop_index('ix_candidate_knowledge_status', 'candidate_knowledge')
    op.drop_index('ix_candidate_knowledge_candidate_id', 'candidate_knowledge')
    op.drop_index('ix_candidate_profiles_candidate_id', 'candidate_profiles')
    op.drop_table('candidate_session_contexts')
    op.drop_table('candidate_knowledge')
    op.drop_table('candidate_profiles')
