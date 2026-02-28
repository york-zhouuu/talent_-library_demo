import pytest


@pytest.mark.asyncio
async def test_create_candidate(client):
    response = await client.post("/api/v1/candidates", json={
        "name": "张三",
        "phone": "13800138000",
        "city": "北京",
        "current_title": "高级工程师"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "张三"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_candidates(client):
    # Create a candidate first
    await client.post("/api/v1/candidates", json={"name": "李四"})

    response = await client.get("/api/v1/candidates")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_candidate(client):
    # Create
    create_resp = await client.post("/api/v1/candidates", json={"name": "王五"})
    candidate_id = create_resp.json()["id"]

    # Get
    response = await client.get(f"/api/v1/candidates/{candidate_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "王五"


@pytest.mark.asyncio
async def test_update_candidate(client):
    # Create
    create_resp = await client.post("/api/v1/candidates", json={"name": "赵六"})
    candidate_id = create_resp.json()["id"]

    # Update
    response = await client.put(f"/api/v1/candidates/{candidate_id}", json={
        "city": "上海"
    })
    assert response.status_code == 200
    assert response.json()["city"] == "上海"


@pytest.mark.asyncio
async def test_delete_candidate(client):
    # Create
    create_resp = await client.post("/api/v1/candidates", json={"name": "孙七"})
    candidate_id = create_resp.json()["id"]

    # Delete
    response = await client.delete(f"/api/v1/candidates/{candidate_id}")
    assert response.status_code == 200

    # Verify deleted
    get_resp = await client.get(f"/api/v1/candidates/{candidate_id}")
    assert get_resp.status_code == 404
