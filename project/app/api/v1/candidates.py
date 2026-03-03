from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header, BackgroundTasks
from fastapi.responses import FileResponse
import re
import asyncio
import os
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db, get_db_context
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


# ==================== Deduplication Endpoints ====================

@router.get("/duplicates")
async def get_duplicates(db: AsyncSession = Depends(get_db)):
    """
    Find all duplicate candidate groups.

    Returns groups of candidates that match by:
    - Phone number (highest confidence)
    - Email address (high confidence)
    - Name + Company (lower confidence)
    """
    from app.services.dedup_service import DeduplicationService

    dedup = DeduplicationService(db)
    groups = await dedup.find_duplicates()
    stats = await dedup.get_duplicate_stats()

    return {
        "stats": stats,
        "groups": [g.to_dict() for g in groups]
    }


@router.post("/merge")
async def merge_candidates_endpoint(
    primary_id: int = Query(..., description="ID of the primary candidate to keep"),
    duplicate_ids: list[int] = Query(..., description="IDs of duplicates to merge into primary"),
    db: AsyncSession = Depends(get_db)
):
    """
    Merge duplicate candidates into a primary candidate.

    This will:
    - Move all resumes to the primary candidate
    - Merge tags (union)
    - Merge pool memberships
    - Fill empty fields from duplicates
    - Delete the duplicate candidates
    """
    from app.services.dedup_service import DeduplicationService

    dedup = DeduplicationService(db)
    try:
        result = await dedup.merge_candidates(primary_id, duplicate_ids)
        return {"message": "Candidates merged successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/auto-dedup")
async def auto_deduplicate(db: AsyncSession = Depends(get_db)):
    """
    Automatically merge all duplicate candidate groups.

    Uses the most complete candidate as primary in each group.
    """
    from app.services.dedup_service import DeduplicationService

    dedup = DeduplicationService(db)
    result = await dedup.auto_merge_all()

    return {
        "message": "Auto-deduplication completed",
        **result
    }


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


async def find_existing_candidate(db: AsyncSession, phone: str = None, email: str = None, name: str = None) -> Candidate | None:
    """通过手机号、邮箱或姓名查找已存在的候选人"""
    if phone:
        stmt = select(Candidate).where(Candidate.phone == phone)
        result = await db.execute(stmt)
        candidate = result.scalar_one_or_none()
        if candidate:
            return candidate

    if email:
        stmt = select(Candidate).where(Candidate.email == email)
        result = await db.execute(stmt)
        candidate = result.scalar_one_or_none()
        if candidate:
            return candidate

    # 姓名匹配作为最后手段（可能不准确，但可以减少明显重复）
    if name and name != "未知姓名":
        stmt = select(Candidate).where(Candidate.name == name)
        result = await db.execute(stmt)
        candidate = result.scalar_one_or_none()
        if candidate:
            return candidate

    return None


def merge_candidate_data(existing: Candidate, new_data: dict, new_skills: list = None) -> bool:
    """
    合并候选人数据 - 只补充空字段，不覆盖已有数据
    返回是否有更新
    """
    updated = False

    # 可合并的字段列表
    mergeable_fields = [
        'phone', 'email', 'city', 'current_company', 'current_title',
        'years_of_experience', 'expected_salary', 'summary'
    ]

    for field in mergeable_fields:
        existing_value = getattr(existing, field, None)
        new_value = new_data.get(field)
        # 只有当现有值为空且新值不为空时才更新
        if (existing_value is None or existing_value == "") and new_value:
            setattr(existing, field, new_value)
            updated = True

    # 合并技能 - 追加新技能
    if new_skills:
        existing_skills = []
        if existing.skills:
            try:
                existing_skills = json.loads(existing.skills)
            except:
                existing_skills = [s.strip() for s in existing.skills.split(',') if s.strip()]

        # 合并并去重
        merged_skills = list(set(existing_skills + new_skills))
        if len(merged_skills) > len(existing_skills):
            existing.skills = json.dumps(merged_skills, ensure_ascii=False)
            updated = True

    return updated


@router.post("/import")
async def import_resume(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    快速导入简历（毫秒级入库）
    1. 快速提取文本 + 正则提取关键字段
    2. 立即入库
    3. 后台异步 AI 精细解析
    """
    parser = ResumeParser()
    content = await file.read()

    try:
        # 使用快速解析模式（不调用 AI）
        result = await parser.quick_parse(file.filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    parsed = result["parsed_data"]
    raw_text = result.get("raw_text", "")

    # 图片版 PDF 暂时允许入库（标记为待 AI 识别）
    if result.get("extraction_method") == "pending_vision":
        # 图片版 PDF，文本较少但仍然入库
        pass
    elif not raw_text or len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"无法从文件中提取文本内容。文件可能是扫描版 PDF 或格式不支持。"
        )

    # 检查必填字段 name
    name = parsed.get("name")
    if not name:
        name = extract_name_from_filename(file.filename)
        if not name:
            name = "未知姓名"
        parsed["name"] = name

    skills = parsed.pop("skills", [])

    # 检查是否已存在该候选人（通过手机号、邮箱或姓名）
    existing_candidate = await find_existing_candidate(
        db,
        phone=parsed.get("phone"),
        email=parsed.get("email"),
        name=parsed.get("name")
    )

    is_merged = False
    if existing_candidate:
        # 合并数据到已存在的候选人
        is_merged = merge_candidate_data(existing_candidate, parsed, skills)
        candidate = existing_candidate
        if is_merged:
            candidate.parse_status = "pending"  # 重新标记为待解析
    else:
        # 创建新候选人
        candidate = Candidate(
            **{k: v for k, v in parsed.items() if hasattr(Candidate, k) and v is not None},
            skills=json.dumps(skills, ensure_ascii=False) if skills else None,
            parse_status="pending"
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
    await db.refresh(resume)  # 获取 resume.id

    # 后台异步 AI 精细解析 + 结构化 Profile
    if background_tasks and raw_text and len(raw_text.strip()) >= 20:
        background_tasks.add_task(
            background_ai_parse,
            candidate.id,
            raw_text,
            resume.id  # 传递 resume_id 用于保存结构化 profile
        )

    return {
        "candidate_id": candidate.id,
        "parsed": result["parsed_data"],
        "pool_id": pool.id,
        "parse_status": "pending",
        "is_merged": is_merged  # 标识是否为合并操作
    }


async def background_ai_parse(candidate_id: int, raw_text: str, resume_id: int = None):
    """后台 AI 精细解析任务 + 结构化 Profile 生成"""
    from app.services.ai_service import AIService
    parser = ResumeParser()
    ai = AIService()

    try:
        # 使用独立的数据库会话
        async with get_db_context() as db:
            # 更新状态为解析中
            stmt = select(Candidate).where(Candidate.id == candidate_id)
            result = await db.execute(stmt)
            candidate = result.scalar_one_or_none()
            if not candidate:
                return

            candidate.parse_status = "parsing"
            await db.commit()

            # 1. 基本信息 AI 解析
            parsed = await parser.ai_parse_text(raw_text)

            if parsed:
                # 更新候选人信息（只更新之前为空的字段）
                if parsed.get("name") and candidate.name == "未知姓名":
                    candidate.name = parsed["name"]
                if parsed.get("phone") and not candidate.phone:
                    candidate.phone = parsed["phone"]
                if parsed.get("email") and not candidate.email:
                    candidate.email = parsed["email"]
                if parsed.get("city") and not candidate.city:
                    candidate.city = parsed["city"]
                if parsed.get("current_company") and not candidate.current_company:
                    candidate.current_company = parsed["current_company"]
                if parsed.get("current_title") and not candidate.current_title:
                    candidate.current_title = parsed["current_title"]
                if parsed.get("years_of_experience") and not candidate.years_of_experience:
                    candidate.years_of_experience = parsed["years_of_experience"]
                if parsed.get("expected_salary") and not candidate.expected_salary:
                    candidate.expected_salary = parsed["expected_salary"]
                if parsed.get("skills"):
                    skills = parsed["skills"]
                    candidate.skills = json.dumps(skills, ensure_ascii=False) if isinstance(skills, list) else skills
                if parsed.get("summary") and not candidate.summary:
                    candidate.summary = parsed["summary"]

            # 2. 结构化 Profile 解析
            print(f"开始结构化 Profile 解析: candidate_id={candidate_id}")
            structured_profile = await ai.parse_resume_structured(raw_text)

            if structured_profile and resume_id:
                # 保存到 Resume 的 parsed_data
                from app.models import Resume
                resume_stmt = select(Resume).where(Resume.id == resume_id)
                resume_result = await db.execute(resume_stmt)
                resume = resume_result.scalar_one_or_none()
                if resume:
                    resume.parsed_data = json.dumps(structured_profile, ensure_ascii=False)
                    print(f"结构化 Profile 已保存: resume_id={resume_id}")

            candidate.parse_status = "completed"
            await db.commit()
            print(f"AI 解析完成: candidate_id={candidate_id}, status={candidate.parse_status}")

    except Exception as e:
        print(f"后台 AI 解析失败: candidate_id={candidate_id}, error={e}")
        import traceback
        traceback.print_exc()
        try:
            async with get_db_context() as db:
                stmt = select(Candidate).where(Candidate.id == candidate_id)
                result = await db.execute(stmt)
                candidate = result.scalar_one_or_none()
                if candidate:
                    candidate.parse_status = "failed"
                    await db.commit()
        except:
            pass


@router.post("/import/batch")
async def import_resumes_batch(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    批量快速导入简历
    使用快速解析模式，后台异步 AI 精细解析
    """
    parser = ResumeParser()
    results = []
    candidates_to_parse = []  # 收集需要后台解析的候选人

    # 获取或创建用户的人才库
    pool = await get_or_create_user_pool(db, current_user)

    for file in files:
        try:
            content = await file.read()
            # 使用快速解析模式
            result = await parser.quick_parse(file.filename, content)
            parsed = result["parsed_data"]
            raw_text = result.get("raw_text", "")

            # 图片版 PDF 暂时允许入库
            if result.get("extraction_method") == "pending_vision":
                pass
            elif not raw_text or len(raw_text.strip()) < 10:
                results.append({
                    "success": False,
                    "filename": file.filename,
                    "error": f"无法从文件中提取文本内容"
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
                skills=json.dumps(skills, ensure_ascii=False) if skills else None,
                parse_status="pending"
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
            await db.refresh(resume)  # 获取 resume.id

            # 收集需要后台解析的候选人
            if raw_text and len(raw_text.strip()) >= 20:
                candidates_to_parse.append((candidate.id, raw_text, resume.id))

            results.append({"success": True, "filename": file.filename, "candidate_id": candidate.id})
        except Exception as e:
            # 回滚当前事务以便继续处理下一个文件
            await db.rollback()
            results.append({"success": False, "filename": file.filename, "error": str(e)})

    # 批量添加后台解析任务
    if background_tasks and candidates_to_parse:
        for candidate_id, raw_text, resume_id in candidates_to_parse:
            background_tasks.add_task(background_ai_parse, candidate_id, raw_text, resume_id)

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


@router.get("/{candidate_id}/structured-profile")
async def get_structured_profile(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """
    获取候选人的结构化 Profile（从简历解析）
    包含：基本信息、工作经历、教育背景、项目经历、技能等
    """
    # 查找候选人
    stmt = select(Candidate).where(Candidate.id == candidate_id).options(selectinload(Candidate.resumes))
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 查找最新的简历解析数据
    if not candidate.resumes:
        raise HTTPException(status_code=404, detail="No resume found for this candidate")

    # 获取最新的简历
    latest_resume = max(candidate.resumes, key=lambda r: r.created_at)

    # 检查是否有结构化数据
    if latest_resume.parsed_data:
        try:
            parsed = json.loads(latest_resume.parsed_data)
            # 检查是否是新的结构化格式（有 work_experience 字段）
            if "work_experience" in parsed or "basic_info" in parsed:
                return {
                    "candidate_id": candidate_id,
                    "resume_id": latest_resume.id,
                    "profile": parsed,
                    "raw_text": latest_resume.raw_text or "",
                    "generated_at": latest_resume.created_at.isoformat() if latest_resume.created_at else None
                }
        except json.JSONDecodeError:
            pass

    # 没有结构化数据，返回 404
    raise HTTPException(
        status_code=404,
        detail="Structured profile not generated yet. Use POST to generate."
    )


@router.post("/{candidate_id}/structured-profile/generate")
async def generate_structured_profile(
    candidate_id: int,
    force: bool = Query(False, description="Force regenerate even if profile exists"),
    db: AsyncSession = Depends(get_db)
):
    """
    生成候选人的结构化 Profile
    从简历原文重新解析，提取完整的工作经历、教育背景等
    """
    from app.services.ai_service import AIService

    # 查找候选人和简历
    stmt = select(Candidate).where(Candidate.id == candidate_id).options(selectinload(Candidate.resumes))
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.resumes:
        raise HTTPException(status_code=404, detail="No resume found for this candidate")

    # 获取最新的简历
    latest_resume = max(candidate.resumes, key=lambda r: r.created_at)

    # 检查是否已有结构化数据（除非 force=True）
    if not force and latest_resume.parsed_data:
        try:
            parsed = json.loads(latest_resume.parsed_data)
            if "work_experience" in parsed or "basic_info" in parsed:
                return {
                    "candidate_id": candidate_id,
                    "resume_id": latest_resume.id,
                    "profile": parsed,
                    "message": "Profile already exists. Use force=true to regenerate."
                }
        except json.JSONDecodeError:
            pass

    # 检查是否有原文
    if not latest_resume.raw_text:
        raise HTTPException(status_code=400, detail="Resume raw text not available")

    # 使用 AI 解析
    ai = AIService()
    structured_data = await ai.parse_resume_structured(latest_resume.raw_text)

    if not structured_data:
        raise HTTPException(status_code=500, detail="Failed to parse resume")

    # 保存到数据库
    latest_resume.parsed_data = json.dumps(structured_data, ensure_ascii=False)
    await db.commit()

    return {
        "candidate_id": candidate_id,
        "resume_id": latest_resume.id,
        "profile": structured_data,
        "message": "Profile generated successfully"
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


@router.get("/{candidate_id}/resume/download")
async def download_resume(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """
    下载候选人的原始简历文件 (PDF/DOCX)
    """
    # 查找候选人和简历
    stmt = select(Candidate).where(Candidate.id == candidate_id).options(selectinload(Candidate.resumes))
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.resumes:
        raise HTTPException(status_code=404, detail="No resume found for this candidate")

    # 获取最新的简历
    latest_resume = max(candidate.resumes, key=lambda r: r.created_at)

    if not latest_resume.file_path or not os.path.exists(latest_resume.file_path):
        raise HTTPException(status_code=404, detail="Resume file not found on disk")

    # 确定 media type
    media_type = "application/pdf"
    if latest_resume.file_type == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif latest_resume.file_type == "doc":
        media_type = "application/msword"

    return FileResponse(
        path=latest_resume.file_path,
        filename=latest_resume.file_name or f"{candidate.name}_简历.{latest_resume.file_type or 'pdf'}",
        media_type=media_type
    )
