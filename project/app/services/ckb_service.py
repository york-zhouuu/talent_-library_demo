"""
CKB (Candidate Knowledge Base) Service

Implements the 4-layer architecture for candidate data:
- Layer 1: Raw resume data (Candidate model)
- Layer 2: Derived profile (CandidateProfile) - AI-generated insights
- Layer 3: Accumulated knowledge (CandidateKnowledge) - Human feedback, highest priority
- Layer 4: Session context (CandidateSessionContext) - Ephemeral, per-search context

Priority: Layer 3 > Layer 1 > Layer 2 (human verification overrides everything)
"""

import json
from datetime import datetime, timedelta
from typing import Literal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Candidate, CandidateProfile, CandidateKnowledge, CandidateSessionContext
from app.schemas.candidate import (
    SkillEntry, SkillSource, LayerConflict, CandidateStatus,
    CandidateProfileResponse, CandidateKnowledgeResponse
)
from app.services.ai_service import AIService


class CKBService:
    """Candidate Knowledge Base Service"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AIService()

    # ==================== Layer 2: Profile Generation ====================

    async def generate_profile(self, candidate_id: int, force: bool = False) -> CandidateProfile:
        """
        Generate or regenerate the AI-derived profile for a candidate.

        Args:
            candidate_id: The candidate to generate profile for
            force: If True, regenerate even if profile exists

        Returns:
            The generated CandidateProfile
        """
        # Get candidate with existing profile
        stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.resumes)
        ).where(Candidate.id == candidate_id)
        result = await self.db.execute(stmt)
        candidate = result.scalar_one_or_none()

        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        # Check if profile exists and force is False
        if candidate.profile and not force:
            return candidate.profile

        # Generate profile using AI
        profile_data = await self._generate_profile_data(candidate)

        if candidate.profile:
            # Update existing profile
            profile = candidate.profile
            profile.parsed_data = json.dumps(profile_data.get("parsed_data", {}), ensure_ascii=False)
            profile.inferred_traits = json.dumps(profile_data.get("inferred_traits", []), ensure_ascii=False)
            profile.highlights = json.dumps(profile_data.get("highlights", []), ensure_ascii=False)
            profile.potential_concerns = json.dumps(profile_data.get("potential_concerns", []), ensure_ascii=False)
            profile.one_liner = profile_data.get("one_liner", "")
            profile.search_keywords = json.dumps(profile_data.get("search_keywords", []), ensure_ascii=False)
            profile.skills_with_confidence = json.dumps(profile_data.get("skills_with_confidence", []), ensure_ascii=False)
            profile.profile_version = (profile.profile_version or 0) + 1
            profile.model_version = "claude-sonnet-4-5"
            profile.generated_at = datetime.utcnow()
        else:
            # Create new profile
            profile = CandidateProfile(
                candidate_id=candidate_id,
                parsed_data=json.dumps(profile_data.get("parsed_data", {}), ensure_ascii=False),
                inferred_traits=json.dumps(profile_data.get("inferred_traits", []), ensure_ascii=False),
                highlights=json.dumps(profile_data.get("highlights", []), ensure_ascii=False),
                potential_concerns=json.dumps(profile_data.get("potential_concerns", []), ensure_ascii=False),
                one_liner=profile_data.get("one_liner", ""),
                search_keywords=json.dumps(profile_data.get("search_keywords", []), ensure_ascii=False),
                skills_with_confidence=json.dumps(profile_data.get("skills_with_confidence", []), ensure_ascii=False),
                profile_version=1,
                model_version="claude-sonnet-4-5",
                generated_at=datetime.utcnow()
            )
            self.db.add(profile)

        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def _generate_profile_data(self, candidate: Candidate) -> dict:
        """Use AI to generate profile data from candidate information"""
        # Gather all available text
        resume_text = ""
        if candidate.resumes:
            resume_text = candidate.resumes[0].raw_text or ""

        candidate_info = {
            "name": candidate.name,
            "current_title": candidate.current_title,
            "current_company": candidate.current_company,
            "city": candidate.city,
            "years_of_experience": candidate.years_of_experience,
            "skills": candidate.skills,
            "summary": candidate.summary,
            "resume_text": resume_text[:5000]  # Limit resume text
        }

        prompt = f"""分析以下候选人信息，生成结构化的候选人画像。

候选人信息：
{json.dumps(candidate_info, ensure_ascii=False, indent=2)}

请返回 JSON 格式：
{{
    "one_liner": "一句话总结这个候选人的核心价值（20-30字）",
    "highlights": ["亮点1", "亮点2", "亮点3"],
    "potential_concerns": ["可能的顾虑或风险点"],
    "inferred_traits": ["推断的特质，如：技术导向、有领导力等"],
    "search_keywords": ["适合搜索的关键词，包含职位变体、技能变体等"],
    "skills_with_confidence": [
        {{"skill": "技能名", "confidence": "high/medium/low", "source": "resume"}}
    ]
}}

只返回 JSON，不要其他内容。"""

        try:
            response = await self.ai.client.messages.create(
                model=self.ai.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            content = self.ai._extract_text(response)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except Exception as e:
            print(f"Profile generation failed: {e}")

        # Return default profile
        return {
            "one_liner": candidate.summary[:100] if candidate.summary else "",
            "highlights": [],
            "potential_concerns": [],
            "inferred_traits": [],
            "search_keywords": [],
            "skills_with_confidence": []
        }

    async def get_profile(self, candidate_id: int) -> CandidateProfile | None:
        """Get candidate's profile (Layer 2)"""
        stmt = select(CandidateProfile).where(CandidateProfile.candidate_id == candidate_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ==================== Layer 3: Knowledge Management ====================

    async def get_or_create_knowledge(self, candidate_id: int) -> CandidateKnowledge:
        """Get or create knowledge record for a candidate"""
        stmt = select(CandidateKnowledge).where(CandidateKnowledge.candidate_id == candidate_id)
        result = await self.db.execute(stmt)
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            knowledge = CandidateKnowledge(
                candidate_id=candidate_id,
                status="new",
                status_history=json.dumps([{
                    "status": "new",
                    "timestamp": datetime.utcnow().isoformat(),
                    "note": "Initial status"
                }], ensure_ascii=False)
            )
            self.db.add(knowledge)
            await self.db.commit()
            await self.db.refresh(knowledge)

        return knowledge

    async def update_status(self, candidate_id: int, new_status: CandidateStatus, note: str | None = None) -> CandidateKnowledge:
        """Update candidate status with history tracking"""
        knowledge = await self.get_or_create_knowledge(candidate_id)

        # Update status history
        history = json.loads(knowledge.status_history or "[]")
        history.append({
            "status": new_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "note": note,
            "previous_status": knowledge.status
        })

        knowledge.status = new_status.value
        knowledge.status_history = json.dumps(history, ensure_ascii=False)

        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def record_feedback(
        self,
        candidate_id: int,
        feedback_type: Literal["interview", "note", "contact"],
        content: str,
        score: int | None = None,
        metadata: dict | None = None
    ) -> CandidateKnowledge:
        """Record feedback for a candidate"""
        knowledge = await self.get_or_create_knowledge(candidate_id)

        feedback_entry = {
            "type": feedback_type,
            "content": content,
            "score": score,
            "metadata": metadata,
            "timestamp": datetime.utcnow().isoformat()
        }

        if feedback_type == "interview":
            feedback_list = json.loads(knowledge.interview_feedback or "[]")
            feedback_list.append(feedback_entry)
            knowledge.interview_feedback = json.dumps(feedback_list, ensure_ascii=False)
        elif feedback_type == "contact":
            contact_list = json.loads(knowledge.contact_history or "[]")
            contact_list.append(feedback_entry)
            knowledge.contact_history = json.dumps(contact_list, ensure_ascii=False)
        else:  # note
            notes_list = json.loads(knowledge.recruiter_notes or "[]")
            notes_list.append(feedback_entry)
            knowledge.recruiter_notes = json.dumps(notes_list, ensure_ascii=False)

        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def override_skill(
        self,
        candidate_id: int,
        skill: str,
        action: Literal["verify", "deny"],
        note: str | None = None
    ) -> CandidateKnowledge:
        """
        Override a skill's verification status (Layer 3 highest priority).

        Args:
            candidate_id: Candidate ID
            skill: Skill name to override
            action: "verify" or "deny"
            note: Optional note explaining the override
        """
        knowledge = await self.get_or_create_knowledge(candidate_id)

        overrides = json.loads(knowledge.skill_overrides or "{}")
        overrides[skill.lower()] = {
            "action": action,
            "note": note,
            "timestamp": datetime.utcnow().isoformat()
        }
        knowledge.skill_overrides = json.dumps(overrides, ensure_ascii=False)

        # Also record a conflict if there's a profile
        profile = await self.get_profile(candidate_id)
        if profile:
            conflicts = json.loads(profile.conflicts or "[]")
            conflicts.append({
                "field": f"skill:{skill}",
                "layer2_value": "present" if action == "deny" else "absent",
                "layer3_value": action,
                "resolution": "layer3_wins",
                "resolved_at": datetime.utcnow().isoformat()
            })
            profile.conflicts = json.dumps(conflicts, ensure_ascii=False)
            await self.db.commit()

        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def should_match_skill(self, candidate_id: int, skill: str) -> tuple[bool, float]:
        """
        Determine if a candidate should match for a given skill.

        Priority: Layer 3 (human override) > Layer 1 (resume) > Layer 2 (AI inferred)

        Returns:
            (should_match, confidence) where confidence is 0-1
        """
        skill_lower = skill.lower()

        # Check Layer 3 first (human overrides - highest priority)
        knowledge = await self.get_or_create_knowledge(candidate_id)
        overrides = json.loads(knowledge.skill_overrides or "{}")

        if skill_lower in overrides:
            action = overrides[skill_lower].get("action")
            if action == "deny":
                return (False, 1.0)  # Human denied, definitely no match
            elif action == "verify":
                return (True, 1.0)  # Human verified, definitely matches

        # Check Layer 1 (raw resume data)
        stmt = select(Candidate).where(Candidate.id == candidate_id)
        result = await self.db.execute(stmt)
        candidate = result.scalar_one_or_none()

        if candidate and candidate.skills:
            if skill_lower in candidate.skills.lower():
                return (True, 0.9)  # Found in resume, high confidence

        # Check Layer 2 (AI inferred)
        profile = await self.get_profile(candidate_id)
        if profile and profile.skills_with_confidence:
            skills = json.loads(profile.skills_with_confidence)
            for s in skills:
                if s.get("skill", "").lower() == skill_lower:
                    confidence_map = {"high": 0.8, "medium": 0.6, "low": 0.4}
                    confidence = confidence_map.get(s.get("confidence", "low"), 0.4)
                    return (True, confidence)

        return (False, 0.0)  # Skill not found

    # ==================== Layer 4: Session Context ====================

    async def create_session_context(
        self,
        session_id: str,
        candidate_id: int,
        job_context_id: str | None = None,
        search_relevance: dict | None = None,
        job_fit_analysis: dict | None = None,
        expires_hours: int = 24
    ) -> CandidateSessionContext:
        """Create a session-specific context for a candidate"""
        context = CandidateSessionContext(
            session_id=session_id,
            candidate_id=candidate_id,
            job_context_id=job_context_id,
            search_relevance=json.dumps(search_relevance, ensure_ascii=False) if search_relevance else None,
            job_fit_analysis=json.dumps(job_fit_analysis, ensure_ascii=False) if job_fit_analysis else None,
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours)
        )
        self.db.add(context)
        await self.db.commit()
        await self.db.refresh(context)
        return context

    async def get_session_context(
        self,
        session_id: str,
        candidate_id: int
    ) -> CandidateSessionContext | None:
        """Get session context for a candidate if it exists and hasn't expired"""
        stmt = select(CandidateSessionContext).where(
            CandidateSessionContext.session_id == session_id,
            CandidateSessionContext.candidate_id == candidate_id,
            (CandidateSessionContext.expires_at > datetime.utcnow()) |
            (CandidateSessionContext.expires_at.is_(None))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_session_note(
        self,
        session_id: str,
        candidate_id: int,
        note: str
    ) -> CandidateSessionContext | None:
        """Add a note to an existing session context"""
        context = await self.get_session_context(session_id, candidate_id)
        if not context:
            return None

        notes = json.loads(context.session_notes or "[]")
        notes.append({
            "note": note,
            "timestamp": datetime.utcnow().isoformat()
        })
        context.session_notes = json.dumps(notes, ensure_ascii=False)

        await self.db.commit()
        await self.db.refresh(context)
        return context

    # ==================== Combined Layer Access ====================

    async def get_candidate_full_context(self, candidate_id: int, session_id: str | None = None) -> dict:
        """
        Get full candidate context combining all layers.

        Returns combined view with proper priority handling.
        """
        # Load all layers
        stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.knowledge),
            selectinload(Candidate.tags)
        ).where(Candidate.id == candidate_id)
        result = await self.db.execute(stmt)
        candidate = result.scalar_one_or_none()

        if not candidate:
            return {}

        # Build combined context
        context = {
            "candidate_id": candidate.id,
            "name": candidate.name,
            "layer1": {
                "current_title": candidate.current_title,
                "current_company": candidate.current_company,
                "city": candidate.city,
                "years_of_experience": candidate.years_of_experience,
                "expected_salary": candidate.expected_salary,
                "skills": candidate.skills,
                "summary": candidate.summary
            },
            "layer2": None,
            "layer3": None,
            "layer4": None
        }

        # Add Layer 2 (profile)
        if candidate.profile:
            context["layer2"] = {
                "one_liner": candidate.profile.one_liner,
                "highlights": json.loads(candidate.profile.highlights or "[]"),
                "potential_concerns": json.loads(candidate.profile.potential_concerns or "[]"),
                "skills_with_confidence": json.loads(candidate.profile.skills_with_confidence or "[]"),
                "profile_version": candidate.profile.profile_version,
                "generated_at": candidate.profile.generated_at.isoformat() if candidate.profile.generated_at else None
            }

        # Add Layer 3 (knowledge)
        if candidate.knowledge:
            context["layer3"] = {
                "status": candidate.knowledge.status,
                "skill_overrides": json.loads(candidate.knowledge.skill_overrides or "{}"),
                "recruiter_notes": json.loads(candidate.knowledge.recruiter_notes or "[]"),
                "interview_feedback": json.loads(candidate.knowledge.interview_feedback or "[]")
            }

        # Add Layer 4 (session context) if session_id provided
        if session_id:
            session_context = await self.get_session_context(session_id, candidate_id)
            if session_context:
                context["layer4"] = {
                    "search_relevance": json.loads(session_context.search_relevance or "{}"),
                    "job_fit_analysis": json.loads(session_context.job_fit_analysis or "{}"),
                    "session_notes": json.loads(session_context.session_notes or "[]")
                }

        return context
