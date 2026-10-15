<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import type { AssetWorkspace } from "../assetWorkspace";
import { buildReadableReview } from "../reviewContent";

const props = defineProps<{ workspace: AssetWorkspace }>();
const drawer = ref<HTMLDialogElement>();
const closeButton = ref<HTMLButtonElement>();
const restoreFocus = ref<HTMLElement | null>(null);
const tags = ref("");
const note = ref("");
const analysisEnabled = ref(true);
const deletionReason = ref("");
const confirmationId = ref("");
const readableReview = computed(() =>
  props.workspace.detail.value
    ? buildReadableReview(props.workspace.detail.value.original_review)
    : { summary: null, sections: [] },
);

watch(
  () => props.workspace.detail.value,
  async (value) => {
    if (value) {
      restoreFocus.value = document.activeElement as HTMLElement | null;
      tags.value = value.tags.join("，");
      note.value = value.note;
      analysisEnabled.value = value.analysis_enabled;
      deletionReason.value = "";
      confirmationId.value = "";
      drawer.value?.showModal();
      await nextTick();
      closeButton.value?.focus();
    } else if (drawer.value?.open) {
      drawer.value.close();
    }
  },
);

function close() {
  props.workspace.closeAsset();
  drawer.value?.close();
  requestAnimationFrame(() => restoreFocus.value?.focus());
}

function save() {
  void props.workspace.saveMetadata({
    tags: tags.value
      .split(/[，,]/)
      .map((value) => value.trim())
      .filter(Boolean),
    note: note.value,
    analysis_enabled: analysisEnabled.value,
  });
}

async function remove() {
  await props.workspace.deleteCurrent(
    deletionReason.value,
    confirmationId.value,
  );
  if (!props.workspace.detail.value) close();
}
</script>

<template>
  <dialog
    ref="drawer"
    class="asset-drawer"
    aria-labelledby="asset-drawer-title"
    @cancel.prevent="close"
    @close="restoreFocus?.focus()"
  >
    <article v-if="workspace.detail.value" class="asset-drawer__content">
      <header class="asset-drawer__header">
        <div>
          <p class="collection-eyebrow">评论资产</p>
          <h2 id="asset-drawer-title">
            {{ workspace.detail.value.review_id }}
          </h2>
          <p>
            {{ workspace.detail.value.series_name }} ·
            {{ workspace.detail.value.asset_id }}
          </p>
        </div>
        <button
          ref="closeButton"
          class="icon-btn"
          aria-label="关闭评论详情"
          @click="close"
        >
          <X :size="20" />
        </button>
      </header>

      <div class="asset-drawer__body">
        <div v-if="workspace.error.value" class="notice error" role="alert">
          <span>{{ workspace.error.value }}</span>
          <button class="text-button" @click="workspace.refreshCurrentDetail">
            刷新详情
          </button>
        </div>
        <section
          class="original-review"
          aria-labelledby="original-review-title"
        >
          <h3 id="original-review-title">原始评论内容</h3>
          <p class="section-help">
            以下内容按来源中的原始顺序完整展示，不截断、不改写。
          </p>

          <article v-if="readableReview.summary" class="original-review__lead">
            <span>评论概述</span>
            <p>{{ readableReview.summary }}</p>
          </article>

          <div
            v-if="readableReview.sections.length"
            class="original-review__sections"
          >
            <article
              v-for="(section, index) in readableReview.sections"
              :key="`${index}:${section.label}`"
              class="original-review__entry"
            >
              <span>{{ section.label }}</span>
              <p v-if="section.content?.trim()">{{ section.content }}</p>
              <p v-else class="original-review__unreadable">
                该分段没有可阅读的正文，请展开原始结构化字段核对。
              </p>
            </article>
          </div>

          <p
            v-if="!readableReview.summary && !readableReview.sections.length"
            class="original-review__empty"
          >
            该记录没有标准正文字段，请在下方查看完整结构化数据。
          </p>

          <details class="original-review__raw">
            <summary>全部原始结构化字段</summary>
            <pre>{{
              JSON.stringify(workspace.detail.value.original_review, null, 2)
            }}</pre>
          </details>
        </section>

        <section aria-labelledby="metadata-title">
          <h3 id="metadata-title">管理信息</h3>
          <label
            >标签<input
              v-model="tags"
              maxlength="620"
              placeholder="以逗号分隔，最多 20 个"
          /></label>
          <label
            >备注<textarea v-model="note" maxlength="1000" rows="4" />
          </label>
          <label class="check-line"
            ><input
              v-model="analysisEnabled"
              type="checkbox"
            />允许进入后续分析</label
          >
          <button
            class="btn secondary"
            :disabled="workspace.actionBusy.value"
            @click="save"
          >
            保存管理信息
          </button>
        </section>

        <section aria-labelledby="references-title">
          <h3 id="references-title">研究引用</h3>
          <p>
            当前已有
            <strong class="mono">{{
              workspace.detail.value.reference_count
            }}</strong>
            个不可变研究快照引用该评论。
          </p>
        </section>

        <section class="asset-danger" aria-labelledby="delete-title">
          <h3 id="delete-title">删除数据</h3>
          <p>永久删除会移除原始评论，只保留不含正文的最小审计记录。</p>
          <label
            >删除原因<textarea v-model="deletionReason" rows="3" required />
          </label>
          <label
            >输入评论 ID 以确认<input
              v-model="confirmationId"
              :placeholder="workspace.detail.value.review_id"
          /></label>
          <button
            class="btn danger"
            :disabled="
              workspace.actionBusy.value ||
              !deletionReason.trim() ||
              confirmationId !== workspace.detail.value.review_id
            "
            @click="remove"
          >
            永久删除该评论
          </button>
        </section>
      </div>
    </article>
  </dialog>
</template>
