# tests/test_article.py
"""文章接口测试：创建、列表、详情、权限、标签、浏览量。"""
from conftest import ARTICLE_PAYLOAD, create_article


# ────────────────────────── 创建 ──────────────────────────


def test_create_article(client_a):
    data = create_article(client_a)
    assert data["status"] == "published"
    assert data["slug"]                              # 由标题自动生成
    assert len(data["tags"]) == 2
    assert data["author"]["username"] == "alice"
    assert data["published_at"] is not None


def test_create_article_requires_auth(client):
    r = client.post("/api/articles", json=ARTICLE_PAYLOAD)
    assert r.status_code == 401


def test_create_article_empty_title_rejected(client_a):
    r = client_a.post("/api/articles", json={**ARTICLE_PAYLOAD, "title": "   "})
    assert r.status_code == 422


def test_slug_unique_when_title_duplicated(client_a):
    a1 = create_article(client_a)
    a2 = create_article(client_a)
    assert a1["slug"] != a2["slug"]
    assert a2["slug"].endswith("-2")


def test_published_at_set_only_when_published(client_a):
    draft = create_article(client_a, status="draft")
    assert draft["published_at"] is None


# ────────────────────────── 列表与筛选 ──────────────────────────


def test_list_pagination(client_a):
    for i in range(3):
        create_article(client_a, title=f"文章 {i}")
    r = client_a.get("/api/articles?page_num=1&page_size=2")
    body = r.json()["data"]
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["pages"] == 2


def test_list_filter_by_status(client_a):
    create_article(client_a, title="已发布")
    create_article(client_a, title="草稿", status="draft")
    r = client_a.get("/api/articles?status=published")
    assert r.json()["data"]["total"] == 1


def test_list_filter_by_tag(client_a):
    create_article(client_a, tag_names=["Docker"])
    create_article(client_a, title="另一篇", tag_names=["Redis"])
    r = client_a.get("/api/articles?tag=docker")
    body = r.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["tags"][0]["slug"] == "docker"


def test_list_invalid_status_rejected(client_a):
    r = client_a.get("/api/articles?status=unknown")
    assert r.status_code == 422


def test_list_item_has_no_content(client_a):
    """列表项不应该包含正文，减少传输量"""
    create_article(client_a)
    item = client_a.get("/api/articles").json()["data"]["items"][0]
    assert "content" not in item


# ────────────────────────── 详情与草稿可见性 ──────────────────────────


def test_detail_contains_content(client_a):
    article = create_article(client_a)
    r = client_a.get(f"/api/articles/{article['slug']}")
    assert r.status_code == 200
    assert r.json()["data"]["content"] == ARTICLE_PAYLOAD["content"]


def test_draft_hidden_from_anonymous(client, client_a):
    article = create_article(client_a, status="draft")
    assert client.get(f"/api/articles/{article['slug']}").status_code == 404


def test_draft_hidden_from_other_user(client_a, client_b):
    article = create_article(client_a, status="draft")
    assert client_b.get(f"/api/articles/{article['slug']}").status_code == 404


def test_draft_visible_to_author(client_a):
    article = create_article(client_a, status="draft")
    assert client_a.get(f"/api/articles/{article['slug']}").status_code == 200


def test_missing_article_returns_404(client):
    assert client.get("/api/articles/does-not-exist").status_code == 404


# ────────────────────────── 浏览量（Redis 增量） ──────────────────────────


def test_view_count_merges_redis_delta(client, client_a):
    """详情页只写 Redis，列表页显示时把增量合并上去"""
    article = create_article(client_a)
    assert client.get(f"/api/articles/{article['slug']}").status_code == 200

    r = client.get("/api/articles")
    assert r.json()["data"]["items"][0]["view_count"] == 1


def test_view_count_accumulates(client, client_a):
    article = create_article(client_a)
    for _ in range(3):
        client.get(f"/api/articles/{article['slug']}")

    r = client.get("/api/articles")
    assert r.json()["data"]["items"][0]["view_count"] == 3


# ────────────────────────── 更新与删除 ──────────────────────────


def test_update_own_article(client_a):
    article = create_article(client_a)
    r = client_a.patch(f"/api/articles/{article['slug']}", json={"title": "新标题"})
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新标题"


def test_published_at_set_when_status_changes(client_a):
    article = create_article(client_a, status="draft")
    r = client_a.patch(f"/api/articles/{article['slug']}", json={"status": "published"})
    assert r.json()["data"]["published_at"] is not None


def test_update_other_users_article_forbidden(client_a, client_b):
    article = create_article(client_a)
    r = client_b.patch(f"/api/articles/{article['slug']}", json={"title": "篡改"})
    assert r.status_code == 403


def test_delete_other_users_article_forbidden(client_a, client_b):
    article = create_article(client_a)
    r = client_b.delete(f"/api/articles/{article['slug']}")
    assert r.status_code == 403


def test_delete_own_article(client_a):
    article = create_article(client_a)
    assert client_a.delete(f"/api/articles/{article['slug']}").status_code == 200
    assert client_a.get(f"/api/articles/{article['slug']}").status_code == 404


def test_delete_article_requires_auth(client, client_a):
    article = create_article(client_a)
    assert client.delete(f"/api/articles/{article['slug']}").status_code == 401


# ────────────────────────── 标签绑定 ──────────────────────────


def test_set_tags_replaces_all(client_a):
    article = create_article(client_a, tag_names=["Docker"])
    r = client_a.put(
        f"/api/articles/{article['slug']}/tags",
        json={"tag_names": ["Redis", "缓存"]},
    )
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["data"]["tags"]}
    assert names == {"Redis", "缓存"}


def test_clear_tags_with_empty_list(client_a):
    article = create_article(client_a, tag_names=["Docker"])
    r = client_a.put(f"/api/articles/{article['slug']}/tags", json={"tag_names": []})
    assert r.status_code == 200
    assert r.json()["data"]["tags"] == []


def test_set_tags_on_others_article_forbidden(client_a, client_b):
    article = create_article(client_a)
    r = client_b.put(
        f"/api/articles/{article['slug']}/tags", json={"tag_names": ["乱来"]}
    )
    assert r.status_code == 403


def test_same_tag_reused_not_duplicated(client_a):
    create_article(client_a, title="第一篇", tag_names=["Docker"])
    create_article(client_a, title="第二篇", tag_names=["Docker"])

    r = client_a.get("/api/tags")
    assert r.json()["data"]["total"] == 1
