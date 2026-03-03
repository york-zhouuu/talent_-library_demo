"""
Candidate deduplication service.
Identifies and merges duplicate candidates based on phone, email, and name.
"""
import json
from collections import defaultdict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Candidate, Resume, Tag, TalentPool, candidate_pools, candidate_tags


class DuplicateGroup:
    """Represents a group of duplicate candidates."""

    def __init__(self, candidates: list[Candidate], match_reason: str):
        self.candidates = candidates
        self.match_reason = match_reason
        self.primary_id = self._select_primary()

    def _select_primary(self) -> int:
        """Select the primary candidate (most complete data, oldest)."""
        # Score each candidate by completeness
        def completeness_score(c: Candidate) -> tuple:
            score = 0
            if c.phone:
                score += 10
            if c.email:
                score += 10
            if c.name and c.name != "未知姓名":
                score += 5
            if c.city:
                score += 3
            if c.current_company:
                score += 3
            if c.current_title:
                score += 3
            if c.years_of_experience:
                score += 2
            if c.skills:
                score += 2
            if c.summary:
                score += 2
            # Prefer older records as primary (more established)
            return (score, -c.id)

        sorted_candidates = sorted(self.candidates, key=completeness_score, reverse=True)
        return sorted_candidates[0].id

    def to_dict(self) -> dict:
        return {
            "primary_id": self.primary_id,
            "match_reason": self.match_reason,
            "candidates": [
                {
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "email": c.email,
                    "current_company": c.current_company,
                    "current_title": c.current_title,
                    "is_primary": c.id == self.primary_id
                }
                for c in self.candidates
            ]
        }


class DeduplicationService:
    """Service for finding and merging duplicate candidates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_duplicates(self) -> list[DuplicateGroup]:
        """
        Find all duplicate candidate groups.

        Returns groups of candidates that match by:
        1. Phone number (highest confidence)
        2. Email address (high confidence)
        3. Name + Company (lower confidence, same person at same company)
        """
        duplicate_groups: list[DuplicateGroup] = []
        processed_ids: set[int] = set()

        # 1. Find duplicates by phone
        phone_groups = await self._find_by_phone()
        for group in phone_groups:
            if not any(c.id in processed_ids for c in group):
                duplicate_groups.append(DuplicateGroup(group, "phone"))
                processed_ids.update(c.id for c in group)

        # 2. Find duplicates by email
        email_groups = await self._find_by_email()
        for group in email_groups:
            if not any(c.id in processed_ids for c in group):
                duplicate_groups.append(DuplicateGroup(group, "email"))
                processed_ids.update(c.id for c in group)

        # 3. Find duplicates by name + company (excluding already processed)
        name_company_groups = await self._find_by_name_company(processed_ids)
        for group in name_company_groups:
            duplicate_groups.append(DuplicateGroup(group, "name_company"))
            processed_ids.update(c.id for c in group)

        return duplicate_groups

    async def _find_by_phone(self) -> list[list[Candidate]]:
        """Find candidates with duplicate phone numbers."""
        # Get phones that appear more than once
        stmt = (
            select(Candidate.phone, func.count(Candidate.id).label('count'))
            .where(Candidate.phone.isnot(None), Candidate.phone != "")
            .group_by(Candidate.phone)
            .having(func.count(Candidate.id) > 1)
        )
        result = await self.db.execute(stmt)
        duplicate_phones = [row.phone for row in result.all()]

        groups = []
        for phone in duplicate_phones:
            stmt = select(Candidate).where(Candidate.phone == phone)
            result = await self.db.execute(stmt)
            candidates = list(result.scalars().all())
            if len(candidates) > 1:
                groups.append(candidates)

        return groups

    async def _find_by_email(self) -> list[list[Candidate]]:
        """Find candidates with duplicate email addresses."""
        stmt = (
            select(Candidate.email, func.count(Candidate.id).label('count'))
            .where(Candidate.email.isnot(None), Candidate.email != "")
            .group_by(Candidate.email)
            .having(func.count(Candidate.id) > 1)
        )
        result = await self.db.execute(stmt)
        duplicate_emails = [row.email for row in result.all()]

        groups = []
        for email in duplicate_emails:
            stmt = select(Candidate).where(Candidate.email == email)
            result = await self.db.execute(stmt)
            candidates = list(result.scalars().all())
            if len(candidates) > 1:
                groups.append(candidates)

        return groups

    async def _find_by_name_company(self, exclude_ids: set[int]) -> list[list[Candidate]]:
        """
        Find candidates with same name and company.
        Excludes candidates already identified by phone/email.
        """
        stmt = (
            select(Candidate.name, Candidate.current_company, func.count(Candidate.id).label('count'))
            .where(
                Candidate.name.isnot(None),
                Candidate.name != "",
                Candidate.name != "未知姓名",
                Candidate.current_company.isnot(None),
                Candidate.current_company != ""
            )
            .group_by(Candidate.name, Candidate.current_company)
            .having(func.count(Candidate.id) > 1)
        )
        result = await self.db.execute(stmt)
        duplicate_name_companies = [(row.name, row.current_company) for row in result.all()]

        groups = []
        for name, company in duplicate_name_companies:
            stmt = select(Candidate).where(
                Candidate.name == name,
                Candidate.current_company == company
            )
            result = await self.db.execute(stmt)
            candidates = [c for c in result.scalars().all() if c.id not in exclude_ids]
            if len(candidates) > 1:
                groups.append(candidates)

        return groups

    async def merge_candidates(
        self,
        primary_id: int,
        duplicate_ids: list[int]
    ) -> dict:
        """
        Merge duplicate candidates into the primary candidate.

        Actions:
        1. Move all resumes to primary candidate
        2. Merge tags (union)
        3. Merge pool memberships
        4. Merge data fields (fill empty fields from duplicates)
        5. Delete duplicate candidates

        Returns:
            Dict with merge results
        """
        # Load primary candidate with all relationships
        stmt = (
            select(Candidate)
            .options(
                selectinload(Candidate.resumes),
                selectinload(Candidate.tags),
                selectinload(Candidate.pools)
            )
            .where(Candidate.id == primary_id)
        )
        result = await self.db.execute(stmt)
        primary = result.scalar_one_or_none()

        if not primary:
            raise ValueError(f"Primary candidate {primary_id} not found")

        merged_count = 0
        resumes_moved = 0
        tags_added = 0
        pools_added = 0

        for dup_id in duplicate_ids:
            if dup_id == primary_id:
                continue

            stmt = (
                select(Candidate)
                .options(
                    selectinload(Candidate.resumes),
                    selectinload(Candidate.tags),
                    selectinload(Candidate.pools)
                )
                .where(Candidate.id == dup_id)
            )
            result = await self.db.execute(stmt)
            duplicate = result.scalar_one_or_none()

            if not duplicate:
                continue

            # 1. Move resumes to primary
            for resume in duplicate.resumes:
                resume.candidate_id = primary_id
                resumes_moved += 1

            # 2. Merge tags
            for tag in duplicate.tags:
                if tag not in primary.tags:
                    primary.tags.append(tag)
                    tags_added += 1

            # 3. Merge pool memberships
            for pool in duplicate.pools:
                if pool not in primary.pools:
                    primary.pools.append(pool)
                    pools_added += 1

            # 4. Merge data fields (fill empty fields)
            self._merge_fields(primary, duplicate)

            # 5. Delete duplicate
            await self.db.delete(duplicate)
            merged_count += 1

        await self.db.commit()
        await self.db.refresh(primary)

        return {
            "primary_id": primary_id,
            "merged_count": merged_count,
            "resumes_moved": resumes_moved,
            "tags_added": tags_added,
            "pools_added": pools_added
        }

    def _merge_fields(self, primary: Candidate, duplicate: Candidate):
        """Merge empty fields from duplicate into primary."""
        mergeable_fields = [
            'phone', 'email', 'city', 'current_company', 'current_title',
            'years_of_experience', 'expected_salary', 'summary'
        ]

        for field in mergeable_fields:
            primary_value = getattr(primary, field, None)
            dup_value = getattr(duplicate, field, None)

            # Only fill if primary is empty and duplicate has value
            if (primary_value is None or primary_value == "") and dup_value:
                setattr(primary, field, dup_value)

        # Special handling for name
        if primary.name == "未知姓名" and duplicate.name and duplicate.name != "未知姓名":
            primary.name = duplicate.name

        # Merge skills (combine and dedupe)
        primary_skills = self._parse_skills(primary.skills)
        dup_skills = self._parse_skills(duplicate.skills)
        if dup_skills:
            merged_skills = list(set(primary_skills + dup_skills))
            primary.skills = json.dumps(merged_skills, ensure_ascii=False)

    def _parse_skills(self, skills_str: str | None) -> list[str]:
        """Parse skills string (could be JSON array or comma-separated)."""
        if not skills_str:
            return []
        try:
            skills = json.loads(skills_str)
            return skills if isinstance(skills, list) else []
        except json.JSONDecodeError:
            return [s.strip() for s in skills_str.split(',') if s.strip()]

    async def auto_merge_all(self) -> dict:
        """
        Automatically merge all duplicate groups.

        Returns:
            Dict with total merge statistics
        """
        groups = await self.find_duplicates()

        total_groups = len(groups)
        total_merged = 0
        total_resumes = 0
        total_tags = 0
        total_pools = 0

        for group in groups:
            duplicate_ids = [c.id for c in group.candidates if c.id != group.primary_id]
            if duplicate_ids:
                result = await self.merge_candidates(group.primary_id, duplicate_ids)
                total_merged += result["merged_count"]
                total_resumes += result["resumes_moved"]
                total_tags += result["tags_added"]
                total_pools += result["pools_added"]

        return {
            "groups_processed": total_groups,
            "candidates_merged": total_merged,
            "resumes_moved": total_resumes,
            "tags_added": total_tags,
            "pools_added": total_pools
        }

    async def get_duplicate_stats(self) -> dict:
        """Get statistics about potential duplicates."""
        # Count by phone
        phone_stmt = (
            select(func.count(func.distinct(Candidate.phone)))
            .where(Candidate.phone.isnot(None), Candidate.phone != "")
        )
        phone_result = await self.db.execute(phone_stmt)
        unique_phones = phone_result.scalar() or 0

        # Count by email
        email_stmt = (
            select(func.count(func.distinct(Candidate.email)))
            .where(Candidate.email.isnot(None), Candidate.email != "")
        )
        email_result = await self.db.execute(email_stmt)
        unique_emails = email_result.scalar() or 0

        # Total candidates
        total_stmt = select(func.count(Candidate.id))
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar() or 0

        # Find duplicate groups
        groups = await self.find_duplicates()

        return {
            "total_candidates": total,
            "unique_phones": unique_phones,
            "unique_emails": unique_emails,
            "duplicate_groups": len(groups),
            "candidates_in_duplicate_groups": sum(len(g.candidates) for g in groups),
            "potential_savings": sum(len(g.candidates) - 1 for g in groups)
        }
