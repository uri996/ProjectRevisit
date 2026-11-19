<script setup lang="ts">
import { ref, watch } from "vue";
import {
  current,
  indexDocuments,
  loadProject,
  state,
  uploadDocuments,
} from "../store";
const files = ref<File[]>([]),
  selected = ref<string[]>([]),
  consent = ref(false),
  feedback = ref("");
watch(
  () => state.selected,
  () => {
    files.value = [];
    selected.value = [];
    consent.value = false;
    feedback.value = "";
  },
);
const labels: Record<string, string> = {
  unindexed: "未索引",
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
  needs_reindex: "需重新索引",
};
async function upload() {
  if (!current.value) return;
  const id = state.selected;
  feedback.value = "";
  const result = await uploadDocuments(id, files.value);
  if (state.selected === id && result !== undefined) {
    feedback.value = result;
    files.value = [];
  }
}
async function index() {
  if (!current.value || !consent.value) return;
  const id = state.selected;
  feedback.value = "";
  const failures = await indexDocuments(id, selected.value);
  if (state.selected === id && failures !== undefined) {
    consent.value = false;
    feedback.value = failures
      ? `${failures} 个文件索引失败，可检查配置后手动重试。`
      : "索引处理完成。";
  }
}
</script>
<template>
  <section class="page scroll-area">
    <div class="page-heading">
      <div>
        <h1>知识库管理</h1>
        <p class="muted">
          导入仅保存到本机。手动确认后，才发送文本至外部 Embedding API。
        </p>
      </div>
      <button
        v-if="current"
        :disabled="!!current.task"
        @click="loadProject(state.selected, true)"
      >
        刷新状态
      </button>
    </div>
    <div v-if="!current" class="empty">请先在左侧创建项目。</div>
    <template v-else>
      <p v-if="current.error" class="error" role="alert">{{ current.error }}</p>
      <p v-if="feedback" class="notice" role="status">{{ feedback }}</p>
      <p v-if="current.task" class="notice" role="status">
        <span class="spinner"></span>{{ current.task }}
      </p>
      <div class="card">
        <h2>导入文档</h2>
        <input
          class="file-input"
          aria-label="选择项目资料"
          type="file"
          accept=".md,.txt"
          multiple
          :disabled="!!current.task"
          @change="
            files = Array.from(($event.target as HTMLInputElement).files || [])
          "
        />
        <p class="muted small">
          UTF-8 Markdown / TXT，每份最多 10 MB。同名内容变化标记为需要重新索引。
        </p>
        <button
          class="primary"
          :disabled="!files.length || !!current.task"
          @click="upload"
        >
          保存上传文件{{ files.length ? `（${files.length}）` : "" }}
        </button>
      </div>
      <div class="card">
        <h2>项目文档</h2>
        <div v-if="!current.documents.length" class="empty">
          尚无资料，请先导入文件。
        </div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>选择</th>
                <th>文件名</th>
                <th>状态</th>
                <th>片段</th>
                <th>说明 / 索引配置</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in current.documents" :key="d.id">
                <td>
                  <input
                    v-model="selected"
                    :value="d.id"
                    type="checkbox"
                    :aria-label="`选择 ${d.name}`"
                    :disabled="!!current.task"
                  />
                </td>
                <td>{{ d.name }}</td>
                <td>
                  <span class="badge" :class="d.status">{{
                    labels[d.status] || d.status
                  }}</span>
                </td>
                <td>{{ d.chunk_count }}</td>
                <td>
                  <span class="error-text">{{ d.error }}</span>
                  <details v-if="d.index_config">
                    <summary>查看原索引配置</summary>
                    <pre>{{ d.index_config }}</pre>
                  </details>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <label class="check"
          ><input
            v-model="consent"
            type="checkbox"
            :disabled="!!current.task"
          />我确认向 AI 设置中已保存的 API
          地址发送所选资料，可能产生费用。</label
        ><button
          class="primary"
          :disabled="!consent || !selected.length || !!current.task"
          @click="index"
        >
          建立索引 / 重新索引</button
        ><RouterLink class="text-link" to="/settings"
          >检查目标地址、模型和维度</RouterLink
        >
      </div></template
    >
  </section>
</template>
