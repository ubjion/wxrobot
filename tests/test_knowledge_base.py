from app.services.knowledge_base import KnowledgeBase


def test_ingests_markdown_and_retrieves_relevant_chunk(tmp_path):
    source = tmp_path / "faq.md"
    source.write_text("# 退款\n\n普通商品支持七天内退款。", encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")

    assert kb.ingest_directory(tmp_path, scope="public") == 1
    results = kb.search("退款", user_id="alice")

    assert len(results) == 1
    assert results[0].title == "faq"
    assert "七天内退款" in results[0].text
    assert results[0].source == "faq.md"


def test_search_respects_public_private_and_group_scopes(tmp_path):
    files = {
        "public.md": "公开规则：工作日服务。",
        "private.md": "Alice 私密资料：项目代号。",
        "group.md": "研发群资料：发布流程。",
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")
    kb.ingest_file(tmp_path / "public.md", scope="public")
    kb.ingest_file(tmp_path / "private.md", scope="private", owner_id="alice")
    kb.ingest_file(tmp_path / "group.md", scope="group", group_id="dev")

    assert len(kb.search("资料", user_id="bob")) == 0
    assert len(kb.search("资料", user_id="alice")) == 1
    assert len(kb.search("流程", user_id="alice", group_id="dev")) == 1


def test_rebuild_removes_deleted_documents(tmp_path):
    source = tmp_path / "old.md"
    source.write_text("旧内容", encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")

    kb.rebuild(tmp_path)
    source.unlink()
    kb.rebuild(tmp_path)

    assert kb.search("旧内容", user_id="alice") == []
