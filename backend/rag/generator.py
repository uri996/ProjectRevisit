import re

from backend.models import AppError
from backend.rag.answer_policy import SYSTEM_PROMPT

LABELS = {
    "fact": "项目资料支持的事实",
    "analysis": "基于项目资料的分析与建议（不代表已实施）",
    "general": "AI 通用知识补充（不代表项目已采用）",
    "uncertainty": "尚待核实的项目事实",
}


def _invalid(code="STRUCTURE", section=None):
    reasons = {
        "STRUCTURE": "回答结构不符合约定",
        "SECTION": "段落类型或正文无效",
        "SOURCES": "来源字段格式无效",
        "SOURCE_REQUIRED": "项目事实或基于资料的分析缺少来源",
        "SOURCE_ROLE": "通用知识或待核实事实不应声称有项目证据",
        "SOURCE_UNKNOWN": "引用不属于本次检索资料",
        "QUOTE": "所附引用原文与检索片段不符",
        "LENGTH": "回答超出长度限制",
        "LEGACY": "旧格式回答缺少有效证据或字段无效",
    }
    # Fixed codes and an ordinal only: never expose model text, IDs or private data.
    position = f"，第 {section} 段" if section is not None else ""
    return AppError(f"模型回答校验失败（QA_{code}{position}）：{reasons[code]}；未保存为成功回答。")


def _normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def _legacy(output, evidence):
    # Support older custom providers without rewriting existing saved answers.
    supported, answer, used = (output.get(k) for k in ("supported", "answer", "used_chunk_ids"))
    allowed = {c["chunk_id"] for c in evidence}
    if (
        not isinstance(supported, bool)
        or not isinstance(answer, str)
        or not 1 <= len(answer.strip()) <= 16000
        or not isinstance(used, list)
        or any(not isinstance(x, str) or x not in allowed for x in used)
        or (supported and not used)
    ):
        raise _invalid("LEGACY")
    return (
        answer.strip(),
        [dict(c, cited=c["chunk_id"] in used) for c in evidence],
        "completed" if supported else "insufficient",
    )


def generate(provider, question, history, evidence, evidence_state=None):
    # Short request-local IDs avoid requiring the model to copy long opaque IDs.
    # Only these aliases and exact IDs in this retrieval can resolve to citations.
    aliases = {f"E{i + 1}": c["chunk_id"] for i, c in enumerate(evidence)}
    output = provider.complete(
        SYSTEM_PROMPT,
        dict(
            question=question,
            history=history,
            evidence=[dict(c, chunk_id=f"E{i + 1}") for i, c in enumerate(evidence)],
            evidence_state=evidence_state or ("matched" if evidence else "no_matches"),
        ),
    )
    if not isinstance(output, dict):
        raise _invalid()
    if "sections" not in output:
        if isinstance(output.get("used_chunk_ids"), list):
            output = dict(
                output,
                used_chunk_ids=[
                    aliases.get(x, x) if isinstance(x, str) else x for x in output["used_chunk_ids"]
                ],
            )
        return _legacy(output, evidence)
    sections = output["sections"]
    if isinstance(sections, dict):
        sections = [sections]
    if not isinstance(sections, list) or not 1 <= len(sections) <= 8:
        raise _invalid()
    by_id = {c["chunk_id"]: c for c in evidence}
    references = {c["chunk_id"]: i + 1 for i, c in enumerate(evidence)}
    facts, analysis = set(), set()
    quotes = {chunk_id: [] for chunk_id in by_id}
    answer, kinds = [], []
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            raise _invalid("SECTION", index)
        kind, text, sources = (section.get(k) for k in ("kind", "text", "sources"))
        if isinstance(kind, str):
            kind = kind.strip().lower()
        if (
            not isinstance(kind, str)
            or kind not in LABELS
            or not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 4000
        ):
            raise _invalid("SECTION", index)
        if sources is None:
            sources = []
        elif isinstance(sources, (dict, str)):
            sources = [sources]
        if not isinstance(sources, list) or len(sources) > 10:
            raise _invalid("SOURCES", index)
        if kind in ("fact", "analysis") and not sources:
            raise _invalid("SOURCE_REQUIRED", index)
        if kind in ("general", "uncertainty") and sources:
            raise _invalid("SOURCE_ROLE", index)
        section_ids = []
        for source in sources:
            if isinstance(source, str):
                source = {"chunk_id": source}
            if not isinstance(source, dict):
                raise _invalid("SOURCES", index)
            chunk_id, quote = source.get("chunk_id"), source.get("quote")
            if isinstance(chunk_id, str):
                chunk_id = chunk_id.strip().strip("`").strip()
                chunk_id = aliases.get(chunk_id, chunk_id)
            if not isinstance(chunk_id, str) or chunk_id not in by_id:
                raise _invalid("SOURCE_UNKNOWN", index)
            # Quotes are optional; the UI already displays the actual source chunk.
            # If the model supplies a quote, NEVER drop or repair fabricated text.
            if "quote" in source and (
                not isinstance(quote, str)
                or not 1 <= len(quote.strip()) <= 400
                or _normalized(quote) not in _normalized(by_id[chunk_id]["text"])
            ):
                raise _invalid("QUOTE", index)
            if chunk_id not in section_ids:
                section_ids.append(chunk_id)
            if quote is not None and quote.strip() not in quotes[chunk_id]:
                quotes[chunk_id].append(quote.strip())
        if kind == "fact":
            facts.update(section_ids)
        elif kind == "analysis":
            analysis.update(section_ids)
        reference_text = "、".join(f"资料 {references[x]}" for x in section_ids)
        label = LABELS[kind] + (
            f" · {'分析依据' if kind == 'analysis' else '依据'}：{reference_text}"
            if reference_text
            else ""
        )
        answer.append(f"**{label}**\n\n{text.strip()}")
        kinds.append(kind)
    answer = "\n\n".join(answer)
    if len(answer) > 18000:
        raise _invalid("LENGTH")
    citations = [
        dict(
            c,
            reference=references[c["chunk_id"]],
            cited=c["chunk_id"] in facts,
            analysis_basis=c["chunk_id"] in analysis,
            supporting_quotes=quotes[c["chunk_id"]],
        )
        for c in evidence
    ]
    status = "insufficient" if all(k == "uncertainty" for k in kinds) else "completed"
    return answer, citations, status
