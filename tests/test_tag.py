# tests/test_tag.py
"""标签接口测试。"""
from conftest import create_article


def test_create_tag(client_a):
    r = client_a.post("/api/tags", json={"name": "Docker"})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["name"] == "Docker"
    assert data["slug"] == "docker"          # slug 不传时由名称生成


def test_create_tag_with_explicit_slug(client_a):
    r = client_a.post("/api/tags", json={"name": "多阶段构建", "slug": "Multi-Stage"})
    assert r.status_code == 201
    assert r.json()["data"]["slug"] == "multi-stage"   # 自动转小写


def test_create_tag_requires_auth(client):
    assert client.post("/api/tags", json={"name": "Docker"}).status_code == 401


def test_duplicate_tag_name_conflict(client_a):
    assert client_a.post("/api/tags", json={"name": "Docker"}).status_code == 201
    r = client_a.post("/api/tags", json={"name": "Docker"})
    assert r.status_code == 409


def test_list_tags(client_a):
    client_a.post("/api/tags", json={"name": "Docker"})
    client_a.post("/api/tags", json={"name": "Redis"})
    r = client_a.get("/api/tags")
    assert r.json()["data"]["total"] == 2


def test_list_tags_is_public(client, client_a):
    client_a.post("/api/tags", json={"name": "Docker"})
    assert client.get("/api/tags").status_code == 200


def test_update_tag(client_a):
    tag = client_a.post("/api/tags", json={"name": "Docker"}).json()["data"]
    r = client_a.patch(f"/api/tags/{tag['id']}", json={"name": "容器化"})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "容器化"


def test_update_missing_tag(client_a):
    r = client_a.patch("/api/tags/999999", json={"name": "不存在"})
    assert r.status_code == 404


def test_delete_tag(client_a):
    tag = client_a.post("/api/tags", json={"name": "Docker"}).json()["data"]
    assert client_a.delete(f"/api/tags/{tag['id']}").status_code == 200
    assert client_a.get("/api/tags").json()["data"]["total"] == 0


def test_delete_tag_clears_article_relation(client_a):
    """删除标签后，文章的 tags 列表应为空（外键 ON DELETE CASCADE）"""
    article = create_article(client_a, tag_names=["Docker"])
    tag_id = article["tags"][0]["id"]

    assert client_a.delete(f"/api/tags/{tag_id}").status_code == 200

    r = client_a.get(f"/api/articles/{article['slug']}")
    assert r.status_code == 200
    assert r.json()["data"]["tags"] == []
