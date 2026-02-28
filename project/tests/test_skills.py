import pytest


@pytest.mark.asyncio
async def test_talent_search_skill(client):
    # Create test candidates
    await client.post("/api/v1/candidates", json={
        "name": "Java工程师A",
        "city": "北京",
        "current_title": "Java开发工程师",
        "skills": '["Java", "Spring"]',
        "years_of_experience": 5
    })

    response = await client.post("/api/v1/skill/talent_search", json={
        "query": "Java工程师",
        "limit": 5
    })
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "session_id" in data


@pytest.mark.asyncio
async def test_talent_detail_skill(client):
    # Create
    create_resp = await client.post("/api/v1/candidates", json={
        "name": "测试候选人",
        "phone": "13900139000"
    })
    candidate_id = create_resp.json()["id"]

    response = await client.post("/api/v1/skill/talent_detail", json={
        "candidate_id": candidate_id
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "测试候选人"
