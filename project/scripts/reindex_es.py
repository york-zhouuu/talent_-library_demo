#!/usr/bin/env python3
"""
Bulk reindex all candidates into Elasticsearch.

Usage:
    python scripts/reindex_es.py [--reset]

Options:
    --reset     Delete the index and recreate it before reindexing
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db import AsyncSessionLocal
from app.models import Candidate, Resume
from app.services.es_service import get_es_service


async def get_all_candidates_with_resumes():
    """Fetch all candidates with their resumes from the database."""
    async with AsyncSessionLocal() as db:
        stmt = select(Candidate).options(selectinload(Candidate.resumes))
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def reindex_all(reset: bool = False):
    """Reindex all candidates into Elasticsearch."""
    es = get_es_service()

    print("Connecting to Elasticsearch...")
    try:
        client = await es.connect()
        if not await client.ping():
            print("ERROR: Cannot connect to Elasticsearch. Is it running?")
            print("       Try: docker-compose up -d elasticsearch")
            return
    except Exception as e:
        print(f"ERROR: Failed to connect to Elasticsearch: {e}")
        print("       Make sure Elasticsearch is running: docker-compose up -d elasticsearch")
        return

    # Reset index if requested
    if reset:
        print("Deleting existing index...")
        await es.delete_index()

    # Ensure index exists
    print("Ensuring index exists with proper mapping...")
    created = await es.ensure_index()
    if created:
        print(f"Created new index: {es.index_name}")
    else:
        print(f"Index {es.index_name} already exists")

    # Fetch all candidates
    print("\nFetching candidates from database...")
    candidates = await get_all_candidates_with_resumes()
    print(f"Found {len(candidates)} candidates")

    if not candidates:
        print("No candidates to index.")
        return

    # Prepare documents for bulk indexing
    print("\nPreparing documents for indexing...")
    docs = []
    for candidate in candidates:
        doc = {
            "id": candidate.id,
            "name": candidate.name,
            "phone": candidate.phone,
            "email": candidate.email,
            "city": candidate.city,
            "current_company": candidate.current_company,
            "current_title": candidate.current_title,
            "years_of_experience": candidate.years_of_experience,
            "expected_salary": candidate.expected_salary,
            "skills": candidate.skills,
            "summary": candidate.summary,
            "parse_status": candidate.parse_status,
            "created_at": candidate.created_at,
            "updated_at": candidate.updated_at,
        }

        # Add raw text from latest resume if available
        if candidate.resumes:
            latest_resume = max(candidate.resumes, key=lambda r: r.created_at)
            if latest_resume.raw_text:
                doc["raw_text"] = latest_resume.raw_text

        docs.append(doc)

    # Bulk index
    print(f"\nBulk indexing {len(docs)} documents...")
    result = await es.bulk_index_candidates(docs)
    print(f"Indexed: {result['success']} success, {result['failed']} failed")

    # Verify
    print("\nVerifying index...")
    client = await es.connect()
    count = await client.count(index=es.index_name)
    print(f"Total documents in index: {count['count']}")

    # Close connection
    await es.close()
    print("\nReindexing complete!")


async def main():
    reset = "--reset" in sys.argv

    if reset:
        print("=" * 50)
        print("WARNING: This will DELETE the existing index!")
        print("=" * 50)
        response = input("Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

    await reindex_all(reset=reset)


if __name__ == "__main__":
    asyncio.run(main())
