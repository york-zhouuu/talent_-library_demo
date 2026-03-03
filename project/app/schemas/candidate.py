from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, EmailStr


# ==================== CKB Enums and Types ====================

class SkillSource(str, Enum):
    RESUME = "resume"  # Extracted from resume text
    AI_INFERRED = "ai_inferred"  # AI inferred from context
    HUMAN_VERIFIED = "human_verified"  # Verified by human recruiter
    HUMAN_DENIED = "human_denied"  # Denied/corrected by human


class SkillEntry(BaseModel):
    """Skill with confidence level and source tracking"""
    skill: str
    confidence: Literal["high", "medium", "low"]
    source: SkillSource
    correction: dict | None = None  # If overridden, original value


class LayerConflict(BaseModel):
    """Records conflicts between CKB layers"""
    field: str
    layer2_value: str | None
    layer3_value: str | None
    resolution: Literal["layer3_wins", "pending_review"]
    resolved_at: datetime | None = None


class CandidateStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# ==================== Base Schemas ====================


class TagBase(BaseModel):
    name: str
    category: str | None = None


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ShareScope(str, Enum):
    """人才库共享范围"""
    PRIVATE = "private"  # 仅所有者可见
    TEAM = "team"  # 团队可见
    ORG = "org"  # 全组织可见
    CUSTOM = "custom"  # 自定义共享


class SharePermission(str, Enum):
    """共享权限级别"""
    VIEW = "view"  # 只读
    EDIT = "edit"  # 可编辑候选人
    ADMIN = "admin"  # 可管理库设置


class PoolShareCreate(BaseModel):
    """添加共享"""
    user_id: str
    permission: SharePermission = SharePermission.VIEW


class PoolShareResponse(BaseModel):
    """共享信息"""
    user_id: str
    permission: SharePermission


class TalentPoolBase(BaseModel):
    name: str
    description: str | None = None


class TalentPoolCreate(TalentPoolBase):
    owner_id: str
    share_scope: ShareScope = ShareScope.PRIVATE
    team_id: str | None = None  # 当 scope=team 时使用


class TalentPoolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    share_scope: ShareScope | None = None
    team_id: str | None = None


class TalentPoolResponse(TalentPoolBase):
    id: int
    owner_id: str
    share_scope: ShareScope
    team_id: str | None = None
    created_at: datetime
    updated_at: datetime
    candidate_count: int = 0
    shared_with: list[PoolShareResponse] = []  # 当 scope=custom 时的共享列表

    class Config:
        from_attributes = True


class CandidateBase(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    years_of_experience: float | None = None
    expected_salary: float | None = None
    skills: str | None = None
    summary: str | None = None
    imported_by: str | None = None


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    years_of_experience: float | None = None
    expected_salary: float | None = None
    skills: str | None = None
    summary: str | None = None


class CandidateResponse(CandidateBase):
    id: int
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse] = []
    parse_status: str | None = None  # pending, parsing, completed, failed

    class Config:
        from_attributes = True


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
    page: int
    page_size: int


class ResumeResponse(BaseModel):
    id: int
    file_name: str
    file_type: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== CKB Schemas ====================

class CandidateProfileBase(BaseModel):
    """Layer 2 - Derived Profile"""
    one_liner: str | None = None
    highlights: list[str] | None = None
    potential_concerns: list[str] | None = None
    skills_with_confidence: list[SkillEntry] | None = None


class CandidateProfileCreate(CandidateProfileBase):
    candidate_id: int


class CandidateProfileResponse(CandidateProfileBase):
    id: int
    candidate_id: int
    profile_version: int
    model_version: str | None
    generated_at: datetime | None
    conflicts: list[LayerConflict] | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CandidateKnowledgeBase(BaseModel):
    """Layer 3 - Accumulated Knowledge"""
    status: CandidateStatus = CandidateStatus.NEW
    recruiter_notes: list[dict] | None = None


class CandidateKnowledgeCreate(CandidateKnowledgeBase):
    candidate_id: int


class CandidateKnowledgeResponse(CandidateKnowledgeBase):
    id: int
    candidate_id: int
    status_history: list[dict] | None = None
    contact_history: list[dict] | None = None
    interview_feedback: list[dict] | None = None
    job_matches: list[dict] | None = None
    skill_overrides: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CandidateStatusUpdate(BaseModel):
    """Update candidate status"""
    status: CandidateStatus
    note: str | None = None


class CandidateFeedbackCreate(BaseModel):
    """Create feedback for a candidate"""
    feedback_type: Literal["interview", "note", "contact"]
    content: str
    score: int | None = None  # For interview feedback, 1-5
    metadata: dict | None = None


class SkillOverride(BaseModel):
    """Override a skill's verification status"""
    skill: str
    action: Literal["verify", "deny"]
    note: str | None = None
