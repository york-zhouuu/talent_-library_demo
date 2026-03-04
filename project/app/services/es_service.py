"""
Elasticsearch service for candidate search.
"""
import json
from typing import Any
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from app.core import get_settings

settings = get_settings()


# Candidate index mapping with support for Chinese text analysis
CANDIDATE_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "chinese_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "cjk_width", "cjk_bigram"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "id": {"type": "integer"},
            "name": {
                "type": "text",
                "analyzer": "chinese_analyzer",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "phone": {"type": "keyword"},
            "email": {"type": "keyword"},
            "city": {"type": "keyword"},
            "current_company": {
                "type": "text",
                "analyzer": "chinese_analyzer",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "current_title": {
                "type": "text",
                "analyzer": "chinese_analyzer",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "years_of_experience": {"type": "float"},
            "expected_salary": {"type": "float"},
            "skills": {
                "type": "text",
                "analyzer": "chinese_analyzer",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "summary": {
                "type": "text",
                "analyzer": "chinese_analyzer"
            },
            "raw_text": {
                "type": "text",
                "analyzer": "chinese_analyzer"
            },
            "parse_status": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"}
        }
    }
}


class ElasticsearchService:
    """Elasticsearch service for candidate search operations."""

    def __init__(self):
        self.client: AsyncElasticsearch | None = None
        self.index_name = settings.es_index_name

    async def connect(self) -> AsyncElasticsearch:
        """Initialize and return the Elasticsearch client."""
        if self.client is None:
            self.client = AsyncElasticsearch(hosts=[settings.elasticsearch_url])
        return self.client

    async def close(self):
        """Close the Elasticsearch client."""
        if self.client:
            await self.client.close()
            self.client = None

    async def ensure_index(self) -> bool:
        """Ensure the candidates index exists with proper mapping."""
        client = await self.connect()
        if not await client.indices.exists(index=self.index_name):
            await client.indices.create(
                index=self.index_name,
                body=CANDIDATE_MAPPING
            )
            return True
        return False

    async def delete_index(self) -> bool:
        """Delete the candidates index."""
        client = await self.connect()
        if await client.indices.exists(index=self.index_name):
            await client.indices.delete(index=self.index_name)
            return True
        return False

    async def index_candidate(self, candidate: dict) -> dict:
        """Index a single candidate document."""
        client = await self.connect()
        doc_id = candidate.get("id")

        # Prepare document
        doc = self._prepare_document(candidate)

        result = await client.index(
            index=self.index_name,
            id=str(doc_id),
            document=doc,
            refresh=True
        )
        return result

    async def bulk_index_candidates(self, candidates: list[dict]) -> dict:
        """Bulk index multiple candidates."""
        client = await self.connect()
        await self.ensure_index()

        actions = []
        for candidate in candidates:
            doc = self._prepare_document(candidate)
            actions.append({
                "_index": self.index_name,
                "_id": str(candidate.get("id")),
                "_source": doc
            })

        success, failed = await async_bulk(
            client,
            actions,
            raise_on_error=False,
            refresh=True
        )
        return {"success": success, "failed": len(failed) if failed else 0}

    async def delete_candidate(self, candidate_id: int) -> bool:
        """Delete a candidate from the index."""
        client = await self.connect()
        try:
            await client.delete(
                index=self.index_name,
                id=str(candidate_id),
                refresh=True
            )
            return True
        except Exception:
            return False

    async def search(
        self,
        query: str,
        filters: dict | None = None,
        limit: int = 50,
        highlight: bool = True
    ) -> dict:
        """
        Search candidates using multi-match query with optional filters.

        Args:
            query: Search query text
            filters: Optional filters (city, min_experience, max_experience, etc.)
            limit: Maximum number of results
            highlight: Whether to include highlights

        Returns:
            Dict with hits, total, and highlights
        """
        client = await self.connect()

        # Build the query
        body = self._build_search_query(query, filters, limit, highlight)

        result = await client.search(index=self.index_name, body=body)

        return self._format_search_results(result, highlight)

    async def search_by_terms(
        self,
        search_terms: list[str],
        city: str | None = None,
        min_experience: float | None = None,
        max_experience: float | None = None,
        max_salary: float | None = None,
        limit: int = 50
    ) -> list[dict]:
        """
        Search candidates by multiple terms with filters.
        This is the main method used by intelligent search.
        """
        client = await self.connect()

        # Build bool query
        must_clauses = []
        filter_clauses = []

        # Text search across multiple fields
        if search_terms:
            should_clauses = []
            for term in search_terms:
                should_clauses.append({
                    "multi_match": {
                        "query": term,
                        "fields": ["name^3", "skills^2", "current_title^2", "current_company", "summary", "raw_text"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                })
            must_clauses.append({"bool": {"should": should_clauses, "minimum_should_match": 1}})

        # Filters
        if city:
            filter_clauses.append({"term": {"city": city}})
        if min_experience is not None:
            filter_clauses.append({"range": {"years_of_experience": {"gte": min_experience}}})
        if max_experience is not None:
            filter_clauses.append({"range": {"years_of_experience": {"lte": max_experience}}})
        if max_salary is not None:
            filter_clauses.append({"range": {"expected_salary": {"lte": max_salary}}})

        query_body = {
            "query": {
                "bool": {
                    "must": must_clauses if must_clauses else [{"match_all": {}}],
                    "filter": filter_clauses
                }
            },
            "size": limit,
            "highlight": {
                "fields": {
                    "skills": {},
                    "summary": {},
                    "current_title": {}
                }
            }
        }

        result = await client.search(index=self.index_name, body=query_body)

        # Format results
        candidates = []
        for hit in result["hits"]["hits"]:
            candidate = hit["_source"]
            candidate["_score"] = hit["_score"]
            if "highlight" in hit:
                candidate["_highlights"] = hit["highlight"]
            candidates.append(candidate)

        return candidates

    async def search_with_aggregations(
        self,
        query: str,
        filters: dict | None = None,
        limit: int = 50
    ) -> dict:
        """
        Search candidates with aggregations for faceted navigation.

        Returns:
            Dict with hits, total, aggregations (cities, experience ranges, etc.)
        """
        client = await self.connect()

        # Build the query
        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "skills^2", "current_title^2", "current_company", "summary"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "match": {
                                "raw_text": {
                                    "query": query,
                                    "boost": 0.5
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1,
                    "filter": []
                }
            },
            "size": limit,
            "highlight": {
                "fields": {
                    "skills": {"number_of_fragments": 3},
                    "summary": {"number_of_fragments": 2},
                    "current_title": {},
                    "current_company": {}
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"]
            },
            "aggs": {
                "cities": {
                    "terms": {
                        "field": "city",
                        "size": 10
                    }
                },
                "experience_ranges": {
                    "range": {
                        "field": "years_of_experience",
                        "ranges": [
                            {"key": "1-3年", "from": 1, "to": 3},
                            {"key": "3-5年", "from": 3, "to": 5},
                            {"key": "5-10年", "from": 5, "to": 10},
                            {"key": "10年+", "from": 10}
                        ]
                    }
                },
                "salary_ranges": {
                    "range": {
                        "field": "expected_salary",
                        "ranges": [
                            {"key": "20万以下", "to": 20},
                            {"key": "20-40万", "from": 20, "to": 40},
                            {"key": "40-60万", "from": 40, "to": 60},
                            {"key": "60-100万", "from": 60, "to": 100},
                            {"key": "100万+", "from": 100}
                        ]
                    }
                }
            }
        }

        # Add filters
        if filters:
            filter_clauses = body["query"]["bool"]["filter"]

            if filters.get("city"):
                filter_clauses.append({"term": {"city": filters["city"]}})

            if filters.get("min_experience") is not None:
                filter_clauses.append({"range": {"years_of_experience": {"gte": filters["min_experience"]}}})

            if filters.get("max_experience") is not None:
                filter_clauses.append({"range": {"years_of_experience": {"lte": filters["max_experience"]}}})

            if filters.get("min_salary") is not None:
                filter_clauses.append({"range": {"expected_salary": {"gte": filters["min_salary"]}}})

            if filters.get("max_salary") is not None:
                filter_clauses.append({"range": {"expected_salary": {"lte": filters["max_salary"]}}})

        result = await client.search(index=self.index_name, body=body)

        # Format results
        hits = []
        for hit in result["hits"]["hits"]:
            doc = hit["_source"]
            doc["_score"] = hit["_score"]
            if "highlight" in hit:
                doc["_highlights"] = hit["highlight"]
            hits.append(doc)

        # Format aggregations
        aggs = {}
        if "aggregations" in result:
            raw_aggs = result["aggregations"]

            if "cities" in raw_aggs:
                aggs["cities"] = [
                    {"value": b["key"], "count": b["doc_count"]}
                    for b in raw_aggs["cities"]["buckets"]
                    if b["key"]  # Skip empty values
                ]

            if "experience_ranges" in raw_aggs:
                aggs["experience"] = [
                    {"value": b["key"], "count": b["doc_count"]}
                    for b in raw_aggs["experience_ranges"]["buckets"]
                    if b["doc_count"] > 0
                ]

            if "salary_ranges" in raw_aggs:
                aggs["salary"] = [
                    {"value": b["key"], "count": b["doc_count"]}
                    for b in raw_aggs["salary_ranges"]["buckets"]
                    if b["doc_count"] > 0
                ]

        return {
            "hits": hits,
            "total": result["hits"]["total"]["value"],
            "max_score": result["hits"]["max_score"],
            "aggregations": aggs
        }

    def _prepare_document(self, candidate: dict) -> dict:
        """Prepare a candidate dict for indexing."""
        doc = {
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "phone": candidate.get("phone"),
            "email": candidate.get("email"),
            "city": candidate.get("city"),
            "current_company": candidate.get("current_company"),
            "current_title": candidate.get("current_title"),
            "years_of_experience": candidate.get("years_of_experience"),
            "expected_salary": candidate.get("expected_salary"),
            "parse_status": candidate.get("parse_status"),
        }

        # Handle skills - could be JSON string or list
        skills = candidate.get("skills")
        if skills:
            if isinstance(skills, str):
                try:
                    skills_list = json.loads(skills)
                    doc["skills"] = " ".join(skills_list) if isinstance(skills_list, list) else skills
                except json.JSONDecodeError:
                    doc["skills"] = skills
            elif isinstance(skills, list):
                doc["skills"] = " ".join(skills)
            else:
                doc["skills"] = str(skills)

        # Summary
        doc["summary"] = candidate.get("summary")

        # Raw text from resume (if available)
        doc["raw_text"] = candidate.get("raw_text", "")

        # Timestamps
        created_at = candidate.get("created_at")
        updated_at = candidate.get("updated_at")
        if created_at:
            doc["created_at"] = created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at
        if updated_at:
            doc["updated_at"] = updated_at.isoformat() if hasattr(updated_at, 'isoformat') else updated_at

        return doc

    def _build_search_query(
        self,
        query: str,
        filters: dict | None,
        limit: int,
        highlight: bool
    ) -> dict:
        """Build Elasticsearch query body."""
        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "skills^2", "current_title^2", "current_company", "summary"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "match": {
                                "raw_text": {
                                    "query": query,
                                    "boost": 0.5
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1,
                    "filter": []
                }
            },
            "size": limit
        }

        # Add filters
        if filters:
            filter_clauses = body["query"]["bool"]["filter"]

            if filters.get("city"):
                filter_clauses.append({"term": {"city": filters["city"]}})

            if filters.get("min_experience") is not None:
                filter_clauses.append({"range": {"years_of_experience": {"gte": filters["min_experience"]}}})

            if filters.get("max_experience") is not None:
                filter_clauses.append({"range": {"years_of_experience": {"lte": filters["max_experience"]}}})

            if filters.get("max_salary") is not None:
                filter_clauses.append({"range": {"expected_salary": {"lte": filters["max_salary"]}}})

            if filters.get("min_salary") is not None:
                filter_clauses.append({"range": {"expected_salary": {"gte": filters["min_salary"]}}})

        # Add highlighting
        if highlight:
            body["highlight"] = {
                "fields": {
                    "skills": {"number_of_fragments": 3},
                    "summary": {"number_of_fragments": 2},
                    "current_title": {}
                },
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"]
            }

        return body

    def _format_search_results(self, result: dict, include_highlights: bool) -> dict:
        """Format Elasticsearch search results."""
        hits = []
        for hit in result["hits"]["hits"]:
            doc = hit["_source"]
            doc["_score"] = hit["_score"]
            if include_highlights and "highlight" in hit:
                doc["_highlights"] = hit["highlight"]
            hits.append(doc)

        return {
            "hits": hits,
            "total": result["hits"]["total"]["value"],
            "max_score": result["hits"]["max_score"]
        }


# Singleton instance
_es_service: ElasticsearchService | None = None


def get_es_service() -> ElasticsearchService:
    """Get or create the ElasticsearchService singleton."""
    global _es_service
    if _es_service is None:
        _es_service = ElasticsearchService()
    return _es_service


async def close_es_service():
    """Close the ElasticsearchService singleton."""
    global _es_service
    if _es_service:
        await _es_service.close()
        _es_service = None
