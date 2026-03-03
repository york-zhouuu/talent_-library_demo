"""批量解析所有未解析的简历"""
import asyncio
import json
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def batch_parse_all():
    from app.db import AsyncSessionLocal
    from app.models import Candidate, Resume
    from app.services.ai_service import AIService
    
    ai = AIService()
    
    async with AsyncSessionLocal() as db:
        # 获取所有候选人和他们的简历
        stmt = select(Candidate).options(selectinload(Candidate.resumes))
        result = await db.execute(stmt)
        candidates = result.scalars().all()
        
        print(f"找到 {len(candidates)} 个候选人")
        
        for candidate in candidates:
            if not candidate.resumes:
                print(f"  跳过 {candidate.name}: 没有简历")
                continue
            
            # 获取最新简历
            latest_resume = max(candidate.resumes, key=lambda r: r.created_at)
            
            # 检查是否已有结构化数据
            if latest_resume.parsed_data:
                try:
                    parsed = json.loads(latest_resume.parsed_data)
                    if "work_experience" in parsed or "basic_info" in parsed:
                        print(f"  跳过 {candidate.name}: 已有结构化 profile")
                        continue
                except:
                    pass
            
            # 检查是否有原文
            if not latest_resume.raw_text or len(latest_resume.raw_text.strip()) < 50:
                print(f"  跳过 {candidate.name}: 简历原文太短或不存在")
                continue
            
            print(f"  解析 {candidate.name}...")
            
            try:
                # 解析结构化 profile
                structured = await ai.parse_resume_structured(latest_resume.raw_text)
                
                if structured:
                    latest_resume.parsed_data = json.dumps(structured, ensure_ascii=False)
                    candidate.parse_status = "completed"
                    await db.commit()
                    print(f"    ✓ 完成")
                else:
                    print(f"    ✗ 解析返回空")
            except Exception as e:
                print(f"    ✗ 错误: {e}")
                continue
        
        print("\n批量解析完成!")

if __name__ == "__main__":
    asyncio.run(batch_parse_all())
