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


def test_sync_directory_skips_unchanged_updates_changed_and_removes_deleted(tmp_path):
    source = tmp_path / "guide.md"
    source.write_text("第一版操作指南", encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")

    assert kb.sync_directory(tmp_path) == 1
    first_id = kb.search("操作指南", user_id="alice")[0].id
    assert kb.sync_directory(tmp_path) == 0
    assert kb.search("操作指南", user_id="alice")[0].id == first_id

    source.write_text("第二版操作指南，增加审批步骤", encoding="utf-8")
    assert kb.sync_directory(tmp_path) == 1
    changed = kb.search("审批步骤", user_id="alice")
    assert len(changed) == 1
    assert "第二版" in changed[0].text

    source.unlink()
    assert kb.sync_directory(tmp_path) == 1
    assert kb.search("审批步骤", user_id="alice") == []


def test_fts_ranks_stronger_match_before_newer_weak_match(tmp_path):
    strong = tmp_path / "strong.md"
    weak = tmp_path / "weak.md"
    strong.write_text("退款 退款 退款 政策和退款流程", encoding="utf-8")
    weak.write_text("退款通知", encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")
    kb.ingest_file(strong)
    kb.ingest_file(weak)

    results = kb.search("退款", user_id="alice")

    assert [item.source for item in results[:2]] == ["strong.md", "weak.md"]


def test_fts_query_with_punctuation_is_safely_tokenized(tmp_path):
    source = tmp_path / "faq.md"
    source.write_text("退款政策", encoding="utf-8")
    kb = KnowledgeBase(tmp_path / "knowledge.sqlite")
    kb.ingest_file(source)

    results = kb.search("退款 OR (", user_id="alice")

    assert len(results) == 1
