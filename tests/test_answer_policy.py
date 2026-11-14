import copy
from dataclasses import replace

import pytest

from backend.models import AppError
from backend.rag.answer_policy import SYSTEM_PROMPT
from backend.rag.generator import generate
from backend.services.application import create_application

EVIDENCE = [
    dict(
        source="catalog.md",
        chunk_id="synthetic-catalog:revision:0",
        document_id="synthetic-doc",
        heading="虚构目录 v0.1",
        text="虚构目录 v0.1 使用 CSV 保存图书，目录编号必须唯一。没有记录个人职责或故障经历。",
        distance=0.1,
    ),
    dict(
        source="notes.md",
        chunk_id="synthetic-notes:revision:0",
        document_id="synthetic-other",
        heading="其他记录",
        text="虚构的分类演示记录。",
        distance=0.2,
    ),
]


def section(kind, text, evidence=None, quote=None):
    return {
        "kind": kind,
        "text": text,
        "sources": []
        if evidence is None
        else [{"chunk_id": evidence["chunk_id"], "quote": quote or evidence["text"][:100]}],
    }


class OutputProvider:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def complete(self, prompt, payload):
        self.requests.append((prompt, payload))
        return copy.deepcopy(self.output)


def test_mixed_fact_analysis_general_have_separate_real_source_roles():
    provider = OutputProvider(
        {
            "sections": [
                section("fact", "该版本使用 CSV 保存图书，编号必须唯一。", EVIDENCE[0]),
                section(
                    "analysis",
                    "基于唯一性约束，可以考虑增加重复编号测试；这不是已实现的成果。",
                    EVIDENCE[0],
                ),
                section("general", "通用测试方法还包括边界值与异常路径测试，不表示该项目已采用。"),
            ]
        }
    )
    answer, citations, status = generate(provider, "既介绍项目，再提出改进建议", [], EVIDENCE)
    assert status == "completed"
    assert "项目资料支持的事实" in answer and "分析与建议" in answer and "AI 通用知识补充" in answer
    assert "资料 1" in answer and "资料 2" not in answer
    assert citations[0]["cited"] and citations[0]["analysis_basis"]
    assert citations[0]["supporting_quotes"] == [EVIDENCE[0]["text"]]
    assert not citations[1]["cited"] and not citations[1]["analysis_basis"]
    assert citations[1]["supporting_quotes"] == []


def test_hypothetical_analysis_needs_basis_but_not_recorded_future_plan():
    provider = OutputProvider(
        {
            "sections": [
                section(
                    "analysis",
                    "如果重新开发，可以考虑增加编号校验测试，并评估并发写入需求；没有证据表明这些已经实施或属于既定计划。",
                    EVIDENCE[0],
                )
            ]
        }
    )
    answer, citations, status = generate(provider, "如果重新开发一次，你会改进什么？", [], EVIDENCE)
    assert status == "completed" and "可以考虑" in answer
    assert "资料不足" not in answer
    assert not citations[0]["cited"] and citations[0]["analysis_basis"]


def test_unknown_historical_difficulties_stay_unknown_but_allow_preparation_help():
    provider = OutputProvider(
        {
            "sections": [
                section(
                    "uncertainty", "本次资料未提供真实故障和处置记录，不能确认实际遇到哪些困难。"
                ),
                section(
                    "general",
                    "可以核查文件写入失败、编号冲突等潜在挑战，准备对应证据；这些是待核查方向，不是已发生的经历。",
                ),
            ]
        }
    )
    answer, citations, status = generate(provider, "项目遇到哪些困难，最终如何处理？", [], EVIDENCE)
    assert status == "completed" and "不是已发生的经历" in answer
    assert "尚待核实" in answer and "AI 通用知识" in answer
    assert not any(c["cited"] or c["analysis_basis"] for c in citations)


def test_empty_evidence_allows_general_knowledge_without_fabricated_project_sources():
    provider = OutputProvider(
        {
            "sections": [
                section(
                    "general",
                    "评价 RAG 可分别检查召回、答案正确性、引用忠实性和无依据断言；这是通用方法。",
                ),
                section(
                    "uncertainty",
                    "当前没有可用项目证据，不能确认本项目已有的评测结果。之前年份的结果也不能视为当前结果。",
                ),
            ]
        }
    )
    answer, citations, status = generate(
        provider, "如何评价 RAG 质量？", [], [], evidence_state="no_matches"
    )
    assert status == "completed" and citations == []
    assert "AI 通用知识" in answer and "资料不足" not in answer
    assert provider.requests[0][1]["evidence_state"] == "no_matches"


@pytest.mark.parametrize(
    "case",
    [
        "unknown-id",
        "invented-quote",
        "fact-no-source",
        "analysis-no-source",
        "general-with-source",
        "uncertainty-with-source",
        "wrong-kind",
        "empty",
    ],
)
def test_invalid_grounding_is_rejected(case):
    row = section("fact", "虚构目录使用 CSV。", EVIDENCE[0])
    evidence = EVIDENCE
    if case == "unknown-id":
        row["sources"][0]["chunk_id"] = "other-project:private:0"
    elif case == "invented-quote":
        row["sources"][0]["quote"] = "项目经历生产故障，延迟下降百分之三十。"
    elif case == "fact-no-source":
        row["sources"] = []
    elif case == "analysis-no-source":
        row = section("analysis", "可以改进目录。")
    elif case == "general-with-source":
        row["kind"] = "general"
    elif case == "uncertainty-with-source":
        row["kind"] = "uncertainty"
    elif case == "wrong-kind":
        row["kind"] = "invented"
    elif case == "empty":
        evidence = []
    with pytest.raises(AppError, match="QA_"):
        generate(OutputProvider({"sections": [row]}), "测试问题", [], evidence)


def test_no_duplicate_refusal_and_legacy_format_is_still_accepted():
    provider = OutputProvider(
        {"supported": False, "answer": "资料不足，无法确认。未记录实际职责。", "used_chunk_ids": []}
    )
    answer, _, status = generate(provider, "实际职责是什么", [], EVIDENCE)
    assert status == "insufficient" and answer.count("资料不足，无法确认") == 1
    modern = OutputProvider({"sections": [section("uncertainty", "本次资料未记录实际职责。")]})
    answer, _, status = generate(modern, "实际职责是什么", [], EVIDENCE)
    assert status == "insufficient" and "资料不足" not in answer


def test_prompt_covers_question_types_version_boundaries_and_untrusted_history():
    for phrase in (
        "历史事实",
        "技术分析",
        "假设改进",
        "技术知识",
        "混合问题",
        "版本",
        "旧版架构",
        "本地代码",
        "历史 AI 回答",
        "不得虚构外部",
        "个人职责",
    ):
        assert phrase in SYSTEM_PROMPT


def test_no_index_calls_only_llm_and_keeps_chat_project_scoped(configured, tmp_path):
    app, providers, keys, factory = configured
    first, second = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    answer = app.qa.ask(first, "如果重新开发一次，你会改进什么？")
    assert answer["status"] == "completed" and answer["citations"] == []
    assert "AI 通用知识" in answer["answer"]
    assert len(providers) == 1 and providers[0].embedded == []
    assert providers[0].payloads[0]["evidence_state"] == "no_compatible_index"
    assert app.qa.history(second) == [] and app.documents.list(first) == []
    restored = create_application(tmp_path, keys, factory)
    assert restored.qa.history(first) == app.qa.history(first)
    assert restored.qa.history(second) == []


def test_older_version_evidence_cannot_establish_latest_implementation():
    evidence = [dict(EVIDENCE[0], text="虚构资料 v0.1：界面使用 Streamlit，仅用于版本边界测试。")]
    provider = OutputProvider(
        {
            "sections": [
                section("fact", "这份 v0.1 资料描述的界面使用 Streamlit。", evidence[0]),
                section("uncertainty", "仅凭旧版资料不能确认当前是否已改为 Vue 或 FastAPI。"),
            ]
        }
    )
    answer, _, _ = generate(provider, "现在最新实现是否 Vue？", [], evidence)
    assert "v0.1" in answer and "不能确认当前" in answer
    assert "旧版架构不能直接认定为当前实现" in provider.requests[0][0]


def test_open_interview_questions_use_current_project_evidence_without_mutating_index(
    configured, tmp_path
):
    app, providers, keys, factory = configured
    first, second = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    for project, filename, text in (
        (
            first,
            "catalog.md",
            "# 虚构图书目录 v0.1\nCatalog 使用 CSV 保存图书，目录编号必须唯一。资料没有记录真实困难或未来计划。",
        ),
        (second, "tasks.md", "# 虚构任务清单\nTask 使用 localStorage 保存演示任务。"),
    ):
        doc = app.documents.upload(project, filename, text.encode())
        app.documents.index(project, doc["document_id"], confirmed=True)
    # The deterministic fake embedding has no open-question semantics. Only this
    # temporary fixture broadens distance so these exact interview questions retrieve.
    app.settings.save(replace(app.settings.load(), max_distance=2.0))
    document = app.documents.list(first)[0]
    original_bytes = app.documents.files.read(document["path"])
    original_ids = app.documents.vectors._open(document["collection"]).get()["ids"]
    schema = app.qa.db.query("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")

    def scripted(settings, key):
        provider = factory(settings, key)

        def complete(prompt, payload):
            provider.payloads.append(payload)
            assert payload["evidence"] and all(
                e["source"] == "catalog.md" for e in payload["evidence"]
            )
            basis = payload["evidence"][0]
            if "困难" in payload["question"]:
                return {
                    "sections": [
                        section(
                            "uncertainty", "本次资料没有提供实际故障及处理记录，无法确认真实困难。"
                        ),
                        section(
                            "general",
                            "可以核查是否遇到过重复编号或文件写入问题，并准备实际记录；这些只是核查方向，不是已发生的事实。",
                        ),
                    ]
                }
            return {
                "sections": [
                    section(
                        "fact",
                        "这份 v0.1 资料描述 CSV 存储与编号唯一性约束。",
                        basis,
                        "目录编号必须唯一。",
                    ),
                    section(
                        "analysis",
                        "基于编号唯一性约束，可以考虑增加重复编号、空编号的回归测试；如有并发写需求，再比较存储方案，不能断言项目已经做过这些优化。",
                        basis,
                        "目录编号必须唯一。",
                    ),
                ]
            }

        provider.complete = complete
        return provider

    app.settings.provider_factory = scripted
    future = app.qa.ask(first, "如果重新开发一次，你会改进什么？")
    assert future["status"] == "completed" and "可以考虑增加" in future["answer"]
    assert future["citations"][0]["analysis_basis"]
    assert future["citations"][0]["supporting_quotes"] == ["目录编号必须唯一。"]
    history = app.qa.history(first)
    history_before = copy.deepcopy(history)
    difficulty = app.qa.ask(first, "项目遇到哪些困难，最终如何处理？")
    assert difficulty["status"] == "completed" and "不是已发生的事实" in difficulty["answer"]
    assert not any(c["cited"] or c["analysis_basis"] for c in difficulty["citations"])
    assert app.qa.history(first)[:2] == history_before
    assert app.qa.history(second) == []
    assert app.documents.files.read(document["path"]) == original_bytes
    assert app.documents.vectors._open(document["collection"]).get()["ids"] == original_ids
    assert (
        app.qa.db.query("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")
        == schema
    )
    restored = create_application(tmp_path, keys, factory)
    assert restored.qa.history(first) == app.qa.history(first)
    assert restored.recommendations.load(second) is None
