<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import type { AssetWorkspace } from "../assetWorkspace";
import { MAX_REVIEW_IMPORT_FILE_BYTES } from "../importFile";

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

async function chooseFiles(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files ?? []);
  if (!files.length) return;
  parseError.value = "";
  try {
    const oversized = files.find(
      (file) => file.size > MAX_REVIEW_IMPORT_FILE_BYTES,
    );
    if (oversized) throw new Error(`${oversized.name} 超过 32 MB`);
    const unsupported = files.find(
      (file) => !/\.(json|jsonl|csv|xlsx)$/i.test(file.name),
    );
    if (unsupported) throw new Error(`${unsupported.name} 不是支持的数据文件`);
    await props.workspace.validateImportFiles(files);
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
        <h2 id="import-dialog-title">导入评论 JSON / JSONL / CSV / XLSX</h2>
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
          >选择一个或多个评论数据文件
          <input
            ref="fileInput"
            type="file"
            accept=".json,.jsonl,.csv,.xlsx,application/json,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            multiple
            aria-label="选择评论数据文件"
            @change="chooseFiles"
          />
        </label>
        <p class="section-help">
          每个文件最大 32 MB、最多 20,000 条。所有文件先校验，不会直接写入。
        </p>
      </section>

      <section
        v-else-if="workspace.importStep.value === 'preview'"
        aria-label="校验预览"
      >
        <dl class="import-counts">
          <div>
            <dt>文件</dt>
            <dd>{{ workspace.importTotals.value.files }}</dd>
          </div>
          <div>
            <dt>可导入</dt>
            <dd>{{ workspace.importTotals.value.importable }}</dd>
          </div>
          <div>
            <dt>重复</dt>
            <dd>{{ workspace.importTotals.value.duplicates }}</dd>
          </div>
          <div>
            <dt>错误</dt>
            <dd>{{ workspace.importTotals.value.errors }}</dd>
          </div>
        </dl>
        <div class="import-file-results">
          <h3>文件校验结果</h3>
          <article
            v-for="preview in workspace.importFilePreviews.value"
            :key="preview.file.name"
            class="import-file-result"
          >
            <header>
              <strong>{{ preview.file.name }}</strong>
              <span>
                可导入 {{ preview.validation.importable.length }} · 重复
                {{ preview.validation.duplicates.length }} · 错误
                {{ preview.validation.errors.length }}
              </span>
            </header>
            <div
              v-if="preview.validation.errors.length"
              class="import-feedback"
            >
              <h4>错误行</h4>
              <p
                v-for="item in preview.validation.errors"
                :key="`${item.line}-${item.type}`"
              >
                {{ item.line ? `第 ${item.line} 行：` : "" }}{{ item.message }}
              </p>
            </div>
            <div
              v-if="preview.validation.duplicates.length"
              class="import-feedback"
            >
              <h4>重复原因</h4>
              <p
                v-for="item in preview.validation.duplicates.slice(0, 5)"
                :key="`${item.line}-${item.reason}`"
              >
                第 {{ item.line }} 行：{{ item.reason }}
              </p>
              <p v-if="preview.validation.duplicates.length > 5">
                另有 {{ preview.validation.duplicates.length - 5 }} 条重复记录
              </p>
            </div>
          </article>
        </div>
        <div class="dialog-actions">
          <button class="btn secondary" @click="workspace.beginImport">
            重新选择
          </button>
          <button
            class="btn primary"
            :disabled="
              workspace.actionBusy.value ||
              !workspace.importTotals.value.importable ||
              Boolean(workspace.importTotals.value.errors)
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
