from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models import Candidate, Tag, Resume, TalentPool
from app.schemas import (
    CandidateCreate, CandidateUpdate, CandidateResponse, CandidateListResponse
)
from app.schemas.candidate import (
    CandidateProfileResponse, CandidateKnowledgeResponse,
    CandidateStatusUpdate, CandidateFeedbackCreate, SkillOverride
)
from app.services import ResumeParser
from app.services.ckb_service import CKBService
from app.core import NotFoundError
import json

router = APIRouter(prefix="/candidates", tags=["candidates"])


def get_current_user(x_user_id: str = Header(default="default_user")) -> str:
    """从请求头获取当前用户ID"""
    return x_user_id


async def get_or_create_user_pool(db: AsyncSession, user_id: str) -> TalentPool:
    """获取用户的人才库，如果不存在则自动创建"""
    stmt = select(TalentPool).where(TalentPool.owner_id == user_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()

    if not pool:
        pool = TalentPool(
            name="我的人才库",
            description="自动创建的个人人才库",
            owner_id=user_id,
            share_scope="private"
        )
        db.add(pool)
        await db.commit()
        await db.refresh(pool)

    return pool


def extract_name_from_filename(filename: str) -> str | None:
    """尝试从文件名中提取姓名"""
    if not filename:
        return None

    filename_without_ext = filename.rsplit(".", 1)[0]

    # 常见的简历文件名格式:
    # "姓名-职位.pdf", "姓名_简历.pdf", "【职位】姓名.pdf"
    # "姓名-工作X年-【脉脉招聘】.pdf"

    # 尝试提取中文名字 (2-4个汉字，通常在开头或特定分隔符后)
    # 先尝试匹配 "【...】姓名" 格式
    match = re.search(r'】([\u4e00-\u9fa5]{2,4})', filename_without_ext)
    if match:
        return match.group(1)

    # 尝试匹配开头的中文名
    match = re.match(r'^([\u4e00-\u9fa5]{2,4})[-_\s]', filename_without_ext)
    if match:
        return match.group(1)

    # 尝试任意位置的中文名
    match = re.search(r'([\u4e00-\u9fa5]{2,4})', filename_without_ext)
    if match:
        return match.group(1)

    return None


@router.post("", response_model=CandidateResponse)
async def create_candidate(data: CandidateCreate, db: AsyncSession = Depends(get_db)):
    candidate = Candidate(**data.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    stmt = select(Candidate).options(selectinload(Candidate.tags)).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    count_stmt = select(func.count(Candidate.id))
    total = await db.scalar(count_stmt)

    return CandidateListResponse(items=candidates, total=total or 0, page=page, page_size=page_size)


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Candidate).options(selectinload(Candidate.tags)).where(Candidate.id == candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)
    return candidate


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Candidate).where(Candidate.id == candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)

    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Candidate).where(Candidate.id == candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    await db.delete(candidate)
    await db.commit()
    return {"message": "Candidate deleted"}


@router.post("/import")
async def import_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    parser = ResumeParser()
    content = await file.read()

    try:
        result = await parser.parse(file.filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    parsed = result["parsed_data"]
    raw_text = result.get("raw_text", "")

    # 检查是否提取到文本
    if not raw_text or len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"无法从文件中提取文本内容。文件可能是扫描版 PDF 或格式不支持。提取到的内容长度: {len(raw_text) if raw_text else 0}"
        )

    # 检查必填字段 name
    name = parsed.get("name")
    if not name:
        # 尝试从文件名提取姓名
        name = extract_name_from_filename(file.filename)
        if not name:
            name = "未知姓名"
        parsed["name"] = name

    skills = parsed.pop("skills", [])

    candidate = Candidate(
        **{k: v for k, v in parsed.items() if hasattr(Candidate, k) and v is not None},
        skills=json.dumps(skills, ensure_ascii=False) if skills else None
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)

    resume = Resume(
        candidate_id=candidate.id,
        file_path=result["file_path"],
        file_name=result["file_name"],
        file_type=result["file_type"],
        raw_text=result["raw_text"],
        parsed_data=json.dumps(result["parsed_data"], ensure_ascii=False)
    )
    db.add(resume)

    # 自动添加到用户的人才库
    pool = await get_or_create_user_pool(db, current_user)
    pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool.id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one()
    if candidate not in pool.candidates:
        pool.candidates.append(candidate)

    await db.commit()

    return {"candidate_id": candidate.id, "parsed": result["parsed_data"], "pool_id": pool.id}


@router.post("/import/batch")
async def import_resumes_batch(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    parser = ResumeParser()
    results = []

    # 获取或创建用户的人才库
    pool = await get_or_create_user_pool(db, current_user)

    for file in files:
        try:
            content = await file.read()
            result = await parser.parse(file.filename, content)
            parsed = result["parsed_data"]
            raw_text = result.get("raw_text", "")

            # 检查是否提取到文本
            if not raw_text or len(raw_text.strip()) < 10:
                results.append({
                    "success": False,
                    "filename": file.filename,
                    "error": f"无法从文件中提取文本内容 (长度: {len(raw_text) if raw_text else 0})"
                })
                continue

            # 检查必填字段 name
            name = parsed.get("name")
            if not name:
                name = extract_name_from_filename(file.filename)
                if not name:
                    name = "未知姓名"
                parsed["name"] = name

            skills = parsed.pop("skills", [])

            candidate = Candidate(
                **{k: v for k, v in parsed.items() if hasattr(Candidate, k) and v is not None},
                skills=json.dumps(skills, ensure_ascii=False) if skills else None
            )
            db.add(candidate)
            await db.commit()
            await db.refresh(candidate)

            resume = Resume(
                candidate_id=candidate.id,
                file_path=result["file_path"],
                file_name=result["file_name"],
                file_type=result["file_type"],
                raw_text=result["raw_text"],
                parsed_data=json.dumps(result["parsed_data"], ensure_ascii=False)
            )
            db.add(resume)

            # 自动添加到用户的人才库
            pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool.id)
            pool_result = await db.execute(pool_stmt)
            pool_with_candidates = pool_result.scalar_one()
            if candidate not in pool_with_candidates.candidates:
                pool_with_candidates.candidates.append(candidate)

            await db.commit()

            results.append({"success": True, "filename": file.filename, "candidate_id": candidate.id})
        except Exception as e:
            # 回滚当前事务以便继续处理下一个文件
            await db.rollback()
            results.append({"success": False, "filename": file.filename, "error": str(e)})

    return {"results": results, "pool_id": pool.id}


@router.post("/{candidate_id}/tags/{tag_id}")
async def add_tag_to_candidate(candidate_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Candidate).options(selectinload(Candidate.tags)).where(Candidate.id == candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    tag_stmt = select(Tag).where(Tag.id == tag_id)
    tag_result = await db.execute(tag_stmt)
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise NotFoundError("Tag", tag_id)

    if tag not in candidate.tags:
        candidate.tags.append(tag)
        await db.commit()

    return {"message": "Tag added"}


@router.delete("/{candidate_id}/tags/{tag_id}")
async def remove_tag_from_candidate(candidate_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Candidate).options(selectinload(Candidate.tags)).where(Candidate.id == candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    tag_stmt = select(Tag).where(Tag.id == tag_id)
    tag_result = await db.execute(tag_stmt)
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise NotFoundError("Tag", tag_id)

    if tag in candidate.tags:
        candidate.tags.remove(tag)
        await db.commit()

    return {"message": "Tag removed"}


# ==================== CKB (Candidate Knowledge Base) Endpoints ====================

@router.post("/{candidate_id}/profile/generate")
async def generate_candidate_profile(
    candidate_id: int,
    force: bool = Query(False, description="Force regenerate even if profile exists"),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate AI-derived profile for a candidate (Layer 2).

    This uses AI to analyze the candidate's resume and generate:
    - One-liner summary
    - Key highlights
    - Potential concerns
    - Skills with confidence levels
    - Search keywords
    """
    ckb = CKBService(db)
    try:
        profile = await ckb.generate_profile(candidate_id, force=force)
        return {
            "message": "Profile generated successfully",
            "profile_id": profile.id,
            "profile_version": profile.profile_version
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{candidate_id}/profile")
async def get_candidate_profile(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """Get candidate's AI-derived profile (Layer 2)"""
    ckb = CKBService(db)
    profile = await ckb.get_profile(candidate_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Generate one first.")

    return {
        "id": profile.id,
        "candidate_id": profile.candidate_id,
        "one_liner": profile.one_liner,
        "highlights": json.loads(profile.highlights or "[]"),
        "potential_concerns": json.loads(profile.potential_concerns or "[]"),
        "skills_with_confidence": json.loads(profile.skills_with_confidence or "[]"),
        "conflicts": json.loads(profile.conflicts or "[]"),
        "profile_version": profile.profile_version,
        "model_version": profile.model_version,
        "generated_at": profile.generated_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }


@router.get("/{candidate_id}/knowledge")
async def get_candidate_knowledge(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """Get candidate's accumulated knowledge (Layer 3)"""
    ckb = CKBService(db)
    knowledge = await ckb.get_or_create_knowledge(candidate_id)

    return {
        "id": knowledge.id,
        "candidate_id": knowledge.candidate_id,
        "status": knowledge.status,
        "status_history": json.loads(knowledge.status_history or "[]"),
        "contact_history": json.loads(knowledge.contact_history or "[]"),
        "interview_feedback": json.loads(knowledge.interview_feedback or "[]"),
        "recruiter_notes": json.loads(knowledge.recruiter_notes or "[]"),
        "job_matches": json.loads(knowledge.job_matches or "[]"),
        "skill_overrides": json.loads(knowledge.skill_overrides or "{}"),
        "created_at": knowledge.created_at,
        "updated_at": knowledge.updated_at
    }


@router.post("/{candidate_id}/knowledge/status")
async def update_candidate_status(
    candidate_id: int,
    status_update: CandidateStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update candidate's status with optional note"""
    ckb = CKBService(db)
    try:
        knowledge = await ckb.update_status(candidate_id, status_update.status, status_update.note)
        return {
            "message": "Status updated",
            "new_status": knowledge.status,
            "history_count": len(json.loads(knowledge.status_history or "[]"))
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{candidate_id}/knowledge/feedback")
async def add_candidate_feedback(
    candidate_id: int,
    feedback: CandidateFeedbackCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add feedback for a candidate (interview notes, contact records, general notes)"""
    ckb = CKBService(db)
    knowledge = await ckb.record_feedback(
        candidate_id,
        feedback.feedback_type,
        feedback.content,
        feedback.score,
        feedback.metadata
    )
    return {"message": f"Feedback ({feedback.feedback_type}) recorded"}


@router.post("/{candidate_id}/knowledge/skill-override")
async def override_candidate_skill(
    candidate_id: int,
    override: SkillOverride,
    db: AsyncSession = Depends(get_db)
):
    """
    Override a skill's verification status (Layer 3 - highest priority).

    Use this when human verification confirms or denies an AI-inferred skill.
    Denied skills will be excluded from future searches.
    """
    ckb = CKBService(db)
    knowledge = await ckb.override_skill(
        candidate_id,
        override.skill,
        override.action,
        override.note
    )
    return {
        "message": f"Skill '{override.skill}' {override.action}d",
        "skill_overrides": json.loads(knowledge.skill_overrides or "{}")
    }


@router.get("/{candidate_id}/context")
async def get_candidate_full_context(
    candidate_id: int,
    session_id: str | None = Query(None, description="Session ID for Layer 4 context"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full candidate context combining all CKB layers.

    Returns a unified view with:
    - Layer 1: Raw resume data
    - Layer 2: AI-derived profile
    - Layer 3: Human feedback and overrides (highest priority)
    - Layer 4: Session-specific context (if session_id provided)
    """
    ckb = CKBService(db)
    context = await ckb.get_candidate_full_context(candidate_id, session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return context


@router.post("/{candidate_id}/knowledge/note")
async def add_recruiter_note(
    candidate_id: int,
    note: str = Query(..., description="Note content"),
    db: AsyncSession = Depends(get_db)
):
    """Quick endpoint to add a recruiter note"""
    ckb = CKBService(db)
    await ckb.record_feedback(candidate_id, "note", note)
    return {"message": "Note added"}
