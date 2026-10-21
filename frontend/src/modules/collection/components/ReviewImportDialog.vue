<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import { isSkippedImportPreview, type AssetWorkspace } from "../assetWorkspace";
import {
  MAX_REVIEW_IMPORT_FILES,
  prepareReviewImportFiles,
  reviewImportFileLabel,
} from "../importFile";

const props = defineProps<{ workspace: AssetWorkspace }>();
const dialog = ref<HTMLDialogElement>();
const fileInput = ref<HTMLInputElement>();
const restoreFocus = ref<HTMLElement | null>(null);
const parseError = ref("");
const selectionNotice = ref("");

watch(
  () => props.workspace.importOpen.value,
  async (open) => {
    if (open) {
      restoreFocus.value = document.activeElement as HTMLElement | null;
      parseError.value = "";
      selectionNotice.value = "";
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

async function chooseFiles(event: Event, fromDirectory = false) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length) return;
  parseError.value = "";
  selectionNotice.value = "";
  try {
    const prepared = prepareReviewImportFiles(files, { fromDirectory });
    if (prepared.skippedCount) {
      selectionNotice.value = `已忽略 ${prepared.skippedCount} 个临时或不支持的文件`;
    }
    await props.workspace.validateImportFiles(prepared.files);
  } catch (error) {
    parseError.value = error instanceof Error ? error.message : "文件解析失败";
  } finally {
    input.value = "";
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
        <h3 class="import-source-heading">选择导入方式</h3>
        <div class="import-source-grid">
          <label class="import-source-option">
            <strong>选择文件</strong>
            <span>手动选择一个或多个表格或 JSON 文件</span>
            <input
              ref="fileInput"
              type="file"
              accept=".json,.jsonl,.csv,.xlsx,application/json,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              multiple
              aria-label="选择评论数据文件"
              :disabled="workspace.actionBusy.value"
              @change="chooseFiles"
            />
          </label>
          <label class="import-source-option import-source-option--folder">
            <strong>选择文件夹批量导入</strong>
            <span>自动识别文件夹内支持的评论数据文件</span>
            <input
              type="file"
              multiple
              webkitdirectory
              aria-label="选择评论数据文件夹"
              :disabled="workspace.actionBusy.value"
              @change="chooseFiles($event, true)"
            />
          </label>
        </div>
        <p v-if="selectionNotice" class="import-selection-notice" role="status">
          {{ selectionNotice }}
        </p>
        <p class="section-help">
          每次最多 {{ MAX_REVIEW_IMPORT_FILES }} 个文件；每个文件最大 32
          MB、最多 20,000 条。所有文件先校验，不会直接写入。
        </p>
        <div
          v-if="workspace.importProgress.value.phase === 'validating'"
          class="import-progress"
          role="status"
          aria-live="polite"
        >
          <header>
            <strong>正在校验文件</strong>
            <span>
              {{ workspace.importProgress.value.completed }} /
              {{ workspace.importProgress.value.total }}
            </span>
          </header>
          <progress
            :max="workspace.importProgress.value.total"
            :value="workspace.importProgress.value.completed"
          />
          <p>{{ workspace.importProgress.value.currentFile }}</p>
        </div>
      </section>

      <section
        v-else-if="workspace.importStep.value === 'preview'"
        aria-label="校验预览"
      >
        <div
          v-if="workspace.importProgress.value.phase === 'writing'"
          class="import-progress"
          role="status"
          aria-live="polite"
        >
          <header>
            <strong>正在写入评论</strong>
            <span>
              {{ workspace.importProgress.value.completed }} /
              {{ workspace.importProgress.value.total }}
            </span>
          </header>
          <progress
            :max="workspace.importProgress.value.total"
            :value="workspace.importProgress.value.completed"
          />
          <p>{{ workspace.importProgress.value.currentFile }}</p>
        </div>
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
            <dt>已跳过</dt>
            <dd>{{ workspace.importTotals.value.skipped }}</dd>
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
            :key="reviewImportFileLabel(preview.file)"
            class="import-file-result"
          >
            <header>
              <strong>{{ reviewImportFileLabel(preview.file) }}</strong>
              <span v-if="isSkippedImportPreview(preview)">
                已跳过 · 没有评论
              </span>
              <span v-else>
                可导入 {{ preview.validation.importable.length }} · 重复
                {{ preview.validation.duplicates.length }} · 错误
                {{ preview.validation.errors.length }}
              </span>
            </header>
            <div
              v-if="preview.validation.errors.length"
              class="import-feedback"
              :class="{
                'import-feedback--skipped': isSkippedImportPreview(preview),
              }"
            >
              <h4>
                {{ isSkippedImportPreview(preview) ? "跳过原因" : "错误行" }}
              </h4>
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
            {{ workspace.actionBusy.value ? "正在写入…" : "确认写入" }}
          </button>
        </div>
      </section>

      <section v-else class="import-complete" aria-live="polite">
        <h3>导入完成</h3>
        <p>
          已写入
          {{ workspace.importResult.value?.imported_count ?? 0 }} 条，跳过重复
          {{ workspace.importResult.value?.duplicate_count ?? 0 }}
          条，跳过无评论文件
          {{ workspace.skippedImportFiles.value.length }} 个。
        </p>
        <details
          v-if="
            workspace.importFileResults.value.length ||
            workspace.skippedImportFiles.value.length
          "
        >
          <summary>
            查看
            {{
              workspace.importFileResults.value.length +
              workspace.skippedImportFiles.value.length
            }}
            个文件的处理结果
          </summary>
          <ul class="import-complete__files">
            <li
              v-for="result in workspace.importFileResults.value"
              :key="result.file_name"
            >
              <span>{{ result.file_name }}</span>
              <span>
                写入 {{ result.imported_count }} · 重复
                {{ result.duplicate_count }}
              </span>
            </li>
            <li
              v-for="fileName in workspace.skippedImportFiles.value"
              :key="`skipped-${fileName}`"
            >
              <span>{{ fileName }}</span>
              <span>已跳过 · 没有评论</span>
            </li>
          </ul>
        </details>
        <button class="btn primary" @click="close">返回资产列表</button>
      </section>
    </div>
  </dialog>
</template>
