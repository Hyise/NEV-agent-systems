<script setup lang="ts">
import { ref } from "vue";
import type { AssetWorkspace } from "../assetWorkspace";
import ReviewAssetDrawer from "../components/ReviewAssetDrawer.vue";
import ReviewImportDialog from "../components/ReviewImportDialog.vue";

const props = defineProps<{ workspace: AssetWorkspace }>();
const batchTag = ref("");

function checked(assetId: string) {
  return props.workspace.selectedAssetIds.value.includes(assetId);
}

function toggle(assetId: string) {
  props.workspace.selectedAssetIds.value = checked(assetId)
    ? props.workspace.selectedAssetIds.value.filter((id) => id !== assetId)
    : [...props.workspace.selectedAssetIds.value, assetId];
}

function batchEnable(enabled: boolean) {
  void props.workspace.batchUpdate({
    analysis_enabled: enabled,
    add_tags: [],
    remove_tags: [],
  });
}

function addBatchTag() {
  const value = batchTag.value.trim();
  if (!value) return;
  void props.workspace.batchUpdate({
    add_tags: [value],
    remove_tags: [],
  });
  batchTag.value = "";
}

function dateTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <section class="assets-workspace" aria-label="管理评论数据">
    <div class="asset-summary-line asset-command-area">
      <span
        >资产总数
        <strong class="mono">{{
          workspace.summary.value?.total ?? 0
        }}</strong></span
      >
      <span
        >参与分析
        <strong class="mono">{{
          workspace.summary.value?.analysis_enabled ?? 0
        }}</strong></span
      >
      <span
        >暂不分析
        <strong class="mono">{{
          workspace.summary.value?.analysis_disabled ?? 0
        }}</strong></span
      >
      <button class="btn primary" type="button" @click="workspace.beginImport">
        导入评论
      </button>
    </div>

    <form
      class="asset-filters"
      aria-label="评论资产筛选"
      @submit.prevent="workspace.applyFilters"
    >
      <label
        >关键词<input
          v-model="workspace.filters.keyword"
          type="search"
          placeholder="评论 ID、车系或正文"
      /></label>
      <label
        >车系 ID<input
          v-model="workspace.filters.series_id"
          inputmode="numeric"
      /></label>
      <label
        >来源<select v-model="workspace.filters.source_kind">
          <option value="">全部来源</option>
          <option value="autohome">汽车之家采集</option>
          <option value="manual_import">人工导入</option>
        </select></label
      >
      <label>标签<input v-model="workspace.filters.tag" /></label>
      <label
        >分析状态<select v-model="workspace.filters.analysis_enabled">
          <option value="">全部状态</option>
          <option value="true">参与分析</option>
          <option value="false">暂不分析</option>
        </select></label
      >
      <div class="asset-filter-actions">
        <button
          class="btn secondary"
          type="submit"
          :disabled="workspace.busy.value"
        >
          {{ workspace.busy.value ? "筛选中…" : "应用筛选" }}
        </button>
        <button
          class="text-button"
          type="button"
          :disabled="workspace.busy.value || !workspace.canResetFilters.value"
          @click="workspace.resetFilters"
        >
          清空筛选
        </button>
      </div>
    </form>

    <div class="asset-filter-status" role="status" aria-live="polite">
      <span>
        {{ workspace.activeFilters.value.length ? "筛选结果" : "全部评论" }}
        <strong class="mono">{{ workspace.assets.value.total }}</strong> 条
      </span>
      <ul v-if="workspace.activeFilters.value.length" aria-label="已生效条件">
        <li v-for="item in workspace.activeFilters.value" :key="item.key">
          {{ item.label }}
        </li>
      </ul>
      <span v-else>填写条件后按 Enter 或点击“应用筛选”</span>
    </div>

    <div v-if="workspace.error.value" class="notice error" role="alert">
      {{ workspace.error.value }}
    </div>

    <div class="asset-batch-bar" aria-label="批量管理">
      <span
        >已选
        <strong class="mono">{{
          workspace.selectedAssetIds.value.length
        }}</strong>
        条</span
      >
      <button
        class="text-button"
        :disabled="!workspace.selectedAssetIds.value.length"
        @click="batchEnable(true)"
      >
        设为参与分析
      </button>
      <button
        class="text-button"
        :disabled="!workspace.selectedAssetIds.value.length"
        @click="batchEnable(false)"
      >
        设为暂不分析
      </button>
      <label>批量添加标签<input v-model="batchTag" maxlength="30" /></label>
      <button
        class="text-button"
        :disabled="!workspace.selectedAssetIds.value.length || !batchTag.trim()"
        @click="addBatchTag"
      >
        添加标签
      </button>
    </div>

    <div class="asset-table-region" :aria-busy="workspace.busy.value">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th><span class="visually-hidden">选择</span></th>
              <th>评论 ID</th>
              <th>车系</th>
              <th>来源</th>
              <th>评论摘要</th>
              <th>标签</th>
              <th>分析状态</th>
              <th>采集 / 导入时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in workspace.assets.value.rows"
              :key="item.asset_id"
            >
              <td>
                <input
                  type="checkbox"
                  :checked="checked(item.asset_id)"
                  :aria-label="`选择评论 ${item.review_id}`"
                  @change="toggle(item.asset_id)"
                />
              </td>
              <td>
                <span class="mono">{{ item.review_id }}</span>
              </td>
              <td>
                {{ item.series_name
                }}<small class="mono">{{ item.series_id }}</small>
              </td>
              <td>
                {{
                  item.source_kind === "manual_import" ? "人工导入" : "汽车之家"
                }}
              </td>
              <td class="asset-excerpt">{{ item.excerpt }}</td>
              <td>
                <span v-if="item.tags.length">{{ item.tags.join("、") }}</span
                ><span v-else>—</span>
              </td>
              <td>{{ item.analysis_enabled ? "参与分析" : "暂不分析" }}</td>
              <td>{{ dateTime(item.first_collected_at) }}</td>
              <td>
                <button
                  class="asset-id-button"
                  type="button"
                  :aria-label="`查看评论 ${item.review_id} 的完整原文`"
                  @click="workspace.openAsset(item.asset_id)"
                >
                  查看原文
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p
        v-if="!workspace.busy.value && !workspace.assets.value.rows.length"
        class="collection-empty-inline"
      >
        当前筛选下没有评论资产。
      </p>
      <footer class="asset-pagination">
        <span
          >第 {{ workspace.page.value }} 页 · 共
          {{ workspace.assets.value.total }} 条</span
        >
        <div>
          <button
            class="text-button"
            :disabled="workspace.page.value <= 1"
            @click="workspace.previousPage"
          >
            上一页</button
          ><button
            class="text-button"
            :disabled="
              workspace.page.value * workspace.pageSize.value >=
              workspace.assets.value.total
            "
            @click="workspace.nextPage"
          >
            下一页
          </button>
        </div>
      </footer>
    </div>

    <details class="deletion-history">
      <summary>删除记录（{{ workspace.deletions.value.total }}）</summary>
      <p class="section-help">
        解除阻止只允许未来重新采集，不会恢复已删除的原始评论。
      </p>
      <div class="table-scroll" :aria-busy="workspace.deletionBusy.value">
        <table>
          <thead>
            <tr>
              <th>评论 ID</th>
              <th>车系</th>
              <th>删除原因</th>
              <th>删除时间</th>
              <th>重采状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in workspace.deletions.value.rows"
              :key="item.audit_id ?? `${item.asset_id}-${item.deleted_at}`"
            >
              <td class="mono">{{ item.review_id }}</td>
              <td>
                {{ item.series_name_snapshot ?? "—" }}
                <small class="mono">{{ item.series_id ?? "—" }}</small>
              </td>
              <td>{{ item.reason }}</td>
              <td>{{ dateTime(item.deleted_at) }}</td>
              <td>
                {{ item.recollection_allowed_at ? "已允许" : "阻止中" }}
              </td>
              <td>
                <button
                  v-if="!item.recollection_allowed_at"
                  class="text-button"
                  :disabled="workspace.actionBusy.value"
                  @click="workspace.allowRecollection(item.asset_id)"
                >
                  允许未来重新采集
                </button>
                <span v-else>无需操作</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p
        v-if="
          !workspace.deletionBusy.value &&
          !workspace.deletions.value.rows.length
        "
        class="collection-empty-inline"
      >
        暂无删除记录。
      </p>
      <footer class="asset-pagination">
        <span>第 {{ workspace.deletionPage.value }} 页</span>
        <div>
          <button
            class="text-button"
            :disabled="workspace.deletionPage.value <= 1"
            @click="workspace.loadDeletions(workspace.deletionPage.value - 1)"
          >
            上一页</button
          ><button
            class="text-button"
            :disabled="
              workspace.deletionPage.value * workspace.pageSize.value >=
              workspace.deletions.value.total
            "
            @click="workspace.loadDeletions(workspace.deletionPage.value + 1)"
          >
            下一页
          </button>
        </div>
      </footer>
    </details>

    <ReviewImportDialog :workspace="workspace" />
    <ReviewAssetDrawer :workspace="workspace" />
  </section>
</template>
