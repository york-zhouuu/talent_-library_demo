from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, Table, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

# Association tables
candidate_tags = Table(
    "candidate_tags",
    Base.metadata,
    Column("candidate_id", Integer, ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

candidate_pools = Table(
    "candidate_pools",
    Base.metadata,
    Column("candidate_id", Integer, ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True),
    Column("pool_id", Integer, ForeignKey("talent_pools.id", ondelete="CASCADE"), primary_key=True),
)

# Pool sharing association table
pool_shares = Table(
    "pool_shares",
    Base.metadata,
    Column("pool_id", Integer, ForeignKey("talent_pools.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", String(100), primary_key=True),  # Shared with user
    Column("permission", String(20), default="view"),  # view, edit, admin
)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(100), index=True)
    city: Mapped[str | None] = mapped_column(String(50), index=True)

    # Professional info
    current_company: Mapped[str | None] = mapped_column(String(200))
    current_title: Mapped[str | None] = mapped_column(String(100))
    years_of_experience: Mapped[float | None] = mapped_column(Float)
    expected_salary: Mapped[float | None] = mapped_column(Float)  # 万/年

    # Skills and summary
    skills: Mapped[str | None] = mapped_column(Text)  # JSON array as string
    summary: Mapped[str | None] = mapped_column(Text)

    # Vector embedding stored as JSON string (for SQLite compatibility)
    embedding: Mapped[str | None] = mapped_column(Text)

    # Track who imported this candidate
    imported_by: Mapped[str | None] = mapped_column(String(100), index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tags: Mapped[list["Tag"]] = relationship(secondary=candidate_tags, back_populates="candidates")
    pools: Mapped[list["TalentPool"]] = relationship(secondary=candidate_pools, back_populates="candidates")
    resumes: Mapped[list["Resume"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")

    # CKB Relationships (Layer 2, 3, 4)
    profile: Mapped["CandidateProfile | None"] = relationship(back_populates="candidate", uselist=False, cascade="all, delete-orphan")
    knowledge: Mapped["CandidateKnowledge | None"] = relationship(back_populates="candidate", uselist=False, cascade="all, delete-orphan")
    session_contexts: Mapped[list["CandidateSessionContext"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(50))  # skill, industry, level, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidates: Mapped[list["Candidate"]] = relationship(secondary=candidate_tags, back_populates="tags")


class TalentPool(Base):
    """
    人才库 - 所有库都是私有的，可通过共享机制分享给他人

    share_scope:
    - private: 仅所有者可见
    - team: 团队成员可见 (需要 team_id)
    - org: 全组织可见
    - custom: 自定义共享 (通过 pool_shares 表)
    """
    __tablename__ = "talent_pools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # 所有者 (必填)
    owner_id: Mapped[str] = mapped_column(String(100), index=True)

    # 共享范围
    share_scope: Mapped[str] = mapped_column(String(20), default="private")  # private, team, org, custom
    team_id: Mapped[str | None] = mapped_column(String(100), index=True)  # 当 scope=team 时使用

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidates: Mapped[list["Candidate"]] = relationship(secondary=candidate_pools, back_populates="pools")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(200))
    file_type: Mapped[str] = mapped_column(String(20))  # pdf, docx
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[str | None] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="resumes")


# ==================== CKB (Candidate Knowledge Base) Models ====================

class CandidateProfile(Base):
    """
    Layer 2 - 派生画像 (Derived Profile)
    AI-generated insights and structured data derived from Layer 1 (raw resume data)
    """
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), unique=True)

    # Parsed and structured data
    parsed_data: Mapped[str | None] = mapped_column(Text)  # JSON: structured resume data
    inferred_traits: Mapped[str | None] = mapped_column(Text)  # JSON: AI-inferred personality/traits
    highlights: Mapped[str | None] = mapped_column(Text)  # JSON: key achievements
    potential_concerns: Mapped[str | None] = mapped_column(Text)  # JSON: potential red flags

    # Search optimization
    one_liner: Mapped[str | None] = mapped_column(String(500))  # One-line summary
    search_keywords: Mapped[str | None] = mapped_column(Text)  # JSON: keywords for search

    # Skills with confidence tracking
    skills_with_confidence: Mapped[str | None] = mapped_column(Text)  # JSON: SkillEntry[]

    # Layer conflict tracking
    conflicts: Mapped[str | None] = mapped_column(Text)  # JSON: LayerConflict[]

    # Versioning
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    model_version: Mapped[str | None] = mapped_column(String(50))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    candidate: Mapped["Candidate"] = relationship(back_populates="profile")


class CandidateKnowledge(Base):
    """
    Layer 3 - 累积知识 (Accumulated Knowledge)
    Human-verified information, feedback, and status tracking
    This layer has highest priority and overrides Layer 1 and Layer 2
    """
    __tablename__ = "candidate_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), unique=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="new")  # new, contacted, interviewing, offered, hired, rejected, withdrawn
    status_history: Mapped[str | None] = mapped_column(Text)  # JSON: history of status changes

    # Interaction history
    contact_history: Mapped[str | None] = mapped_column(Text)  # JSON: contact attempts/results
    interview_feedback: Mapped[str | None] = mapped_column(Text)  # JSON: interview notes/scores
    recruiter_notes: Mapped[str | None] = mapped_column(Text)  # JSON: free-form notes

    # Job matching history
    job_matches: Mapped[str | None] = mapped_column(Text)  # JSON: jobs this candidate was matched to

    # Human overrides for skills (highest priority)
    skill_overrides: Mapped[str | None] = mapped_column(Text)  # JSON: {skill: "verified"|"denied"}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    candidate: Mapped["Candidate"] = relationship(back_populates="knowledge")


class CandidateSessionContext(Base):
    """
    Layer 4 - 会话上下文 (Session Context)
    Ephemeral, session-specific information for a particular search or job matching context
    """
    __tablename__ = "candidate_session_contexts"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))

    # Job context (if applicable)
    job_context_id: Mapped[str | None] = mapped_column(String(36))

    # Session-specific analysis
    search_relevance: Mapped[str | None] = mapped_column(Text)  # JSON: why this candidate appeared in search
    job_fit_analysis: Mapped[str | None] = mapped_column(Text)  # JSON: detailed fit analysis
    comparison_context: Mapped[str | None] = mapped_column(Text)  # JSON: comparison with other candidates
    session_notes: Mapped[str | None] = mapped_column(Text)  # JSON: notes specific to this session

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)  # Session contexts can expire

    # Relationship
    candidate: Mapped["Candidate"] = relationship(back_populates="session_contexts")
