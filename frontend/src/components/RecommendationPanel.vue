<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { current, generateQuestions, state } from "../store";
const emit = defineEmits<{ ask: [question: string]; close: [] }>();
const category = ref("项目复盘"),
  all = ref(false),
  consent = ref(false),
  form = ref(false);
watch(
  () => state.selected,
  () => {
    consent.value = false;
  },
);
const questions = computed(() => {
  const list = state.presets[category.value] || [];
  return all.value ? list : list.slice(0, 3);
});
async function generate() {
  if (consent.value) {
    const id = state.selected;
    consent.value = false;
    await generateQuestions(id);
  }
}
</script>
<template>
  <aside class="recommendation-panel" aria-label="智能提问推荐">
    <header class="panel-heading">
      <div><strong>推荐问题</strong><small>找到值得深入复盘的方向</small></div>
      <button class="icon" @click="emit('close')" aria-label="收起推荐面板">
        ×
      </button>
    </header>
    <div class="recommendation-scroll">
      <div class="tabs" role="group" aria-label="提问方向">
        <button
          v-for="c in ['项目复盘', '面试准备']"
          :key="c"
          :class="{ chosen: category === c }"
          @click="
            category = c;
            all = false;
          "
        >
          {{ c }}
        </button>
      </div>
      <p class="muted small">
        浏览免费。点击问题会直接对当前项目提问，可能产生 API 费用。
      </p>
      <button
        v-for="q in questions"
        :key="q"
        class="question-button"
        :disabled="!current || !!current.task"
        @click="emit('ask', q)"
      >
        {{ q }}<span>↗</span></button
      ><button class="subtle" @click="all = !all">
        {{ all ? "收起基础问题" : "展开全部基础问题" }}
      </button>
      <div class="section-heading">
        <h2>个性化推荐</h2>
        <button class="subtle" @click="form = !form">
          {{ form ? "收起表单" : "根据简历生成" }}
        </button>
      </div>
      <form
        v-if="form && current"
        class="recommendation-form"
        @submit.prevent="generate"
      >
        <label
          >项目简历描述<textarea
            v-model="current.description"
            rows="5"
            maxlength="8000"
            placeholder="粘贴项目描述或简短介绍"
            required
          ></textarea></label
        ><label
          >目标岗位<input
            v-model="current.role"
            maxlength="100"
            placeholder="如后端开发、AI 产品经理"
            required
        /></label>
        <p class="muted small">
          只发送以上两项输入，复用已配置的 Qwen。不读取知识库，也不生成答案。
        </p>
        <label class="check"
          ><input v-model="consent" type="checkbox" />确认发送至已配置 LLM
          API，可能产生费用。</label
        ><button
          class="primary"
          :disabled="
            !consent ||
            !current.description.trim() ||
            !current.role.trim() ||
            !!current.task
          "
        >
          {{
            current.task.startsWith("正在生成")
              ? "生成中…"
              : "生成 / 重新生成问题"
          }}
        </button>
      </form>
      <p v-if="current?.recommendationError" class="error" role="alert">
        {{ current.recommendationError }}
      </p>
      <template v-if="current?.recommendations"
        ><p class="muted small">
          已保存 · {{ current.recommendations.target_role
          }}<br />上次成功生成的结果，浏览不会再次调用 API。
        </p>
        <div
          v-for="(q, i) in current.recommendations.questions"
          :key="q.question"
          class="personal-question"
        >
          <button
            class="question-button"
            :disabled="!!current.task"
            @click="emit('ask', q.question)"
          >
            <span class="question-number">{{ i + 1 }}</span>{{
              q.question
            }}</button
          ><span class="badge">{{ q.direction }}</span>
          <p class="muted small">{{ q.reason }}</p>
        </div></template
      >
      <p v-else class="muted small">尚无个性化问题。基础推荐始终可用。</p>
    </div>
  </aside>
</template>
