<script setup lang="ts">
import type { Citation } from "../types";
defineProps<{ citations: Citation[] }>();
function sourceLabel(citation: Citation) {
  if (citation.reference == null)
    return citation.cited ? "模型标记支持（旧回答）" : "旧检索上下文";
  if (citation.cited)
    return citation.analysis_basis ? "事实来源 / 分析依据" : "支持对应事实段落";
  return citation.analysis_basis
    ? "仅作为分析依据，不证明建议已实施"
    : "仅检索上下文，未用于结论";
}
</script>
<template>
  <details v-if="citations.length" class="citations">
    <summary>来源证据 · {{ citations.length }} 条</summary>
    <section
      v-for="(citation, citationIndex) in citations"
      :key="citation.chunk_id"
      class="citation"
    >
      <span class="badge"
        >资料 {{ citation.reference ?? citationIndex + 1 }}</span
      >
      <strong>{{ citation.source }}</strong>
      <p class="muted small">
        {{ citation.heading || "无章节标题" }} ·
        {{ sourceLabel(citation) }}
      </p>
      <div v-if="citation.supporting_quotes?.length" class="supporting-quotes">
        <span class="muted small">本次引用原文</span>
        <p v-for="quote in citation.supporting_quotes" :key="quote">
          {{ quote }}
        </p>
      </div>
      <blockquote>{{ citation.text }}</blockquote>
      <details>
        <summary class="small">完整 Chunk ID</summary>
        <code>{{ citation.chunk_id }}</code>
      </details>
    </section>
  </details>
</template>
