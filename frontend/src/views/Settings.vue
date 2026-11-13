<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import { errorText, state, loadProject } from "../store";
import type { Settings } from "../types";
const settings = ref<Settings | null>(null),
  keyStatus = ref(""),
  key = ref(""),
  confirmed = ref(false),
  testConsent = ref(false),
  busy = ref(false),
  error = ref(""),
  notice = ref(""),
  path = ref(""),
  showPath = ref(false);
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const view = await api.settings();
    settings.value = view.settings;
    keyStatus.value = view.key_status;
    error.value = view.warning || "";
  } catch (e) {
    error.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (!settings.value || !confirmed.value || busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  const secret = key.value;
  key.value = "";
  try {
    const view = await api.saveSettings(settings.value, secret);
    settings.value = view.settings;
    keyStatus.value = view.key_status;
    notice.value = "设置已保存，密钥仅由操作系统安全凭据管理。";
    confirmed.value = false;
    if (state.selected) void loadProject(state.selected, true);
  } catch (e) {
    error.value = errorText(e);
  } finally {
    key.value = "";
    busy.value = false;
  }
}
async function test() {
  if (!testConsent.value || busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  testConsent.value = false;
  try {
    notice.value = (await api.testSettings()).message;
  } catch (e) {
    error.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function location() {
  if (busy.value) return;
  showPath.value = !showPath.value;
  if (showPath.value) {
    try {
      path.value = (await api.dataLocation()).path;
    } catch (e) {
      error.value = errorText(e);
    }
  } else path.value = "";
}
onMounted(load);
</script>
<template>
  <section class="page scroll-area settings-page">
    <div class="page-heading">
      <div>
        <h1>AI 设置</h1>
        <p class="muted">
          复用本机 Qwen 配置。密钥不会返回到浏览器，也不保存在浏览器存储中。
        </p>
      </div>
      <button :disabled="busy" @click="load">重新读取</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="busy" class="notice" role="status">
      <span class="spinner"></span>正在处理设置请求…
    </p>
    <form v-if="settings" class="card settings-form" @submit.prevent="save">
      <h2>模型与目标地址</h2>
      <p class="small">
        服务商：{{ settings.provider }} · 密钥状态：{{ keyStatus }}
      </p>
      <label
        >API Base URL（HTTPS）<input
          v-model="settings.base_url"
          type="url"
          required
          :disabled="busy"
      /></label>
      <p class="muted small">
        地域、业务空间与 Key 必须匹配。请复制百炼控制台实际地址。新加坡 Flash
        Embedding 不受支持时请明确选择当地可用模型，不会自动替换。
      </p>
      <label
        >新的 API Key<input
          v-model="key"
          type="password"
          autocomplete="new-password"
          placeholder="留空保留当前目标地址的密钥"
          :disabled="busy"
      /></label>
      <div class="form-grid">
        <label
          >LLM 模型 ID<input
            v-model="settings.llm_model"
            required
            :disabled="busy" /></label
        ><label
          >Embedding 模型 ID<input
            v-model="settings.embedding_model"
            required
            :disabled="busy" /></label
        ><label
          >Embedding 维度<input
            v-model.number="settings.dimensions"
            type="number"
            min="1"
            max="4096"
            :disabled="busy"
        /></label>
      </div>
      <details>
        <summary>检索与分块设置</summary>
        <div class="form-grid">
          <label
            >Chunk Size<input
              v-model.number="settings.chunk_size"
              type="number"
              min="200"
              max="4000"
              :disabled="busy" /></label
          ><label
            >Chunk Overlap<input
              v-model.number="settings.chunk_overlap"
              type="number"
              min="0"
              max="3999"
              :disabled="busy" /></label
          ><label
            >Top-K<input
              v-model.number="settings.top_k"
              type="number"
              min="1"
              max="10"
              :disabled="busy" /></label
          ><label
            >历史消息数<input
              v-model.number="settings.history_messages"
              type="number"
              min="0"
              max="20"
              :disabled="busy" /></label
          ><label
            >历史字符上限<input
              v-model.number="settings.history_chars"
              type="number"
              min="0"
              max="20000"
              :disabled="busy" /></label
          ><label
            >最大余弦距离<input
              v-model.number="settings.max_distance"
              type="number"
              min="0"
              max="2"
              step="0.01"
              :disabled="busy"
          /></label>
        </div>
      </details>
      <label class="check"
        ><input
          v-model="confirmed"
          type="checkbox"
          :disabled="busy"
        />我已核对实际地址、地域和模型。更改 Embedding
        或分块配置后需要手动重建索引。</label
      ><button class="primary" :disabled="!confirmed || busy">保存设置</button>
    </form>
    <div class="card">
      <h2>连接测试</h2>
      <p class="muted small">
        仅使用合成文本，各调用一次 Embedding 和
        LLM，可能产生费用。先保存表单再测试。
      </p>
      <label class="check"
        ><input
          v-model="testConsent"
          type="checkbox"
          :disabled="busy"
        />确认测试已保存配置并可能产生 API 费用。</label
      ><button :disabled="!testConsent || busy" @click="test">
        测试已保存配置的 API 连接
      </button>
    </div>
    <details class="card">
      <summary>高级选项</summary>
      <p class="muted small">完整路径可能包含用户名。仅查看，不迁移数据。</p>
      <button @click="location">
        {{ showPath ? "隐藏完整数据路径" : "主动查看完整数据路径" }}
      </button>
      <pre v-if="showPath">{{ path }}</pre>
    </details>
  </section>
</template>
