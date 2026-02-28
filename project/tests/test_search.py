import pytest


@pytest.mark.asyncio
async def test_quick_search(client):
    # Create test data
    await client.post("/api/v1/candidates", json={
        "name": "Python工程师",
        "city": "上海",
        "skills": '["Python", "FastAPI"]',
        "years_of_experience": 3
    })

    response = await client.post("/api/v1/search/quick", json={
        "query": "Python工程师 上海",
        "limit": 10
    })
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "candidates" in data


@pytest.mark.asyncio
async def test_agent_filter(client):
    # Create test data
    await client.post("/api/v1/candidates", json={
        "name": "北京候选人",
        "city": "北京",
        "years_of_experience": 5
    })

    response = await client.post("/api/v1/agent/filter", json={
        "conditions": [
            {"field": "city", "operator": "$eq", "value": "北京"}
        ],
        "limit": 10
    })
    assert response.status_code == 200
    data = response.json()
    assert "candidates" in data


@pytest.mark.asyncio
async def test_batch_get(client):
    # Create test data
    resp1 = await client.post("/api/v1/candidates", json={"name": "候选人1"})
    resp2 = await client.post("/api/v1/candidates", json={"name": "候选人2"})
    id1 = resp1.json()["id"]
    id2 = resp2.json()["id"]

    response = await client.post("/api/v1/agent/batch/get", json={
        "ids": [id1, id2]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 2
