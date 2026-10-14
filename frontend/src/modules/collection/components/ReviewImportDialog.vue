<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import type { AssetWorkspace } from "../assetWorkspace";
import {
  decodeReviewImport,
  MAX_REVIEW_IMPORT_BYTES,
  parseReviewImportText,
} from "../importFile";

const props = defineProps<{ workspace: AssetWorkspace }>();
const dialog = ref<HTMLDialogElement>();
const fileInput = ref<HTMLInputElement>();
const restoreFocus = ref<HTMLElement | null>(null);
const parseError = ref("");

watch(
  () => props.workspace.importOpen.value,
  async (open) => {
    if (open) {
      restoreFocus.value = document.activeElement as HTMLElement | null;
      parseError.value = "";
      dialog.value?.showModal();
      await nextTick();
      fileInput.value?.focus();
    } else if (dialog.value?.open) {
      dialog.value.close();
    }
  },
);

function close() {
  props.workspace.closeImport();
  dialog.value?.close();
  requestAnimationFrame(() => restoreFocus.value?.focus());
}

async function chooseFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  parseError.value = "";
  try {
    if (file.size > MAX_REVIEW_IMPORT_BYTES)
      throw new Error("导入文件不能超过 8 MB");
    const bytes = new Uint8Array(await file.arrayBuffer());
    const text = decodeReviewImport(bytes);
    await props.workspace.validateImport(
      parseReviewImportText(text),
      file.size,
    );
  } catch (error) {
    parseError.value = error instanceof Error ? error.message : "文件解析失败";
  }
}
</script>

<template>
  <dialog
    ref="dialog"
    class="project-dialog import-dialog"
    aria-labelledby="import-dialog-title"
    @cancel.prevent="close"
    @close="restoreFocus?.focus()"
  >
    <header class="import-dialog__header">
      <div>
        <p class="collection-eyebrow">人工导入</p>
        <h2 id="import-dialog-title">导入评论 JSON / JSONL</h2>
      </div>
      <button class="icon-btn" aria-label="关闭导入对话框" @click="close">
        <X :size="20" />
      </button>
    </header>
    <ol class="import-steps" aria-label="导入步骤">
      <li :class="{ current: workspace.importStep.value === 'select' }">
        01 选择文件
      </li>
      <li :class="{ current: workspace.importStep.value === 'preview' }">
        02 校验预览
      </li>
      <li :class="{ current: workspace.importStep.value === 'complete' }">
        03 确认写入
      </li>
    </ol>

    <div class="import-dialog__body">
      <div
        v-if="parseError || workspace.error.value"
        class="notice error"
        role="alert"
      >
        {{ parseError || workspace.error.value }}
      </div>
      <section v-if="workspace.importStep.value === 'select'">
        <label class="file-field"
          >选择 UTF-8 JSON 或 JSONL 文件
          <input
            ref="fileInput"
            type="file"
            accept=".json,.jsonl,application/json"
            aria-label="选择评论数据文件"
            @change="chooseFile"
          />
        </label>
        <p class="section-help">
          最大 8 MB，最多 10,000 条；本机解析后先校验，不会直接写入。
        </p>
      </section>

      <section
        v-else-if="workspace.importStep.value === 'preview'"
        aria-label="校验预览"
      >
        <dl class="import-counts">
          <div>
            <dt>可导入</dt>
            <dd>{{ workspace.importPreview.value?.importable.length ?? 0 }}</dd>
          </div>
          <div>
            <dt>重复</dt>
            <dd>{{ workspace.importPreview.value?.duplicates.length ?? 0 }}</dd>
          </div>
          <div>
            <dt>错误</dt>
            <dd>{{ workspace.importPreview.value?.errors.length ?? 0 }}</dd>
          </div>
        </dl>
        <div
          v-if="workspace.importPreview.value?.errors.length"
          class="import-feedback"
        >
          <h3>错误行</h3>
          <p
            v-for="item in workspace.importPreview.value.errors"
            :key="`${item.line}-${item.type}`"
          >
            第 {{ item.line }} 行：{{ item.message }}
          </p>
        </div>
        <div
          v-if="workspace.importPreview.value?.duplicates.length"
          class="import-feedback"
        >
          <h3>重复原因</h3>
          <p
            v-for="item in workspace.importPreview.value.duplicates"
            :key="`${item.line}-${item.reason}`"
          >
            第 {{ item.line }} 行：{{ item.reason }}
          </p>
        </div>
        <div class="dialog-actions">
          <button class="btn secondary" @click="workspace.beginImport">
            重新选择
          </button>
          <button
            class="btn primary"
            :disabled="
              workspace.actionBusy.value ||
              !workspace.importPreview.value?.importable.length ||
              Boolean(workspace.importPreview.value?.errors.length)
            "
            @click="workspace.confirmImport"
          >
            确认写入
          </button>
        </div>
      </section>

      <section v-else class="import-complete" aria-live="polite">
        <h3>导入完成</h3>
        <p>
          已写入
          {{ workspace.importResult.value?.imported_count ?? 0 }} 条，跳过重复
          {{ workspace.importResult.value?.duplicate_count ?? 0 }} 条。
        </p>
        <button class="btn primary" @click="close">返回资产列表</button>
      </section>
    </div>
  </dialog>
</template>
