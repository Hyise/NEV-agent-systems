<script setup lang="ts">
import { ArrowRight, LockKeyhole, Plus, Trash2 } from "lucide-vue-next";
import { labels, useWorkspace } from "../workspace";

const {
  overview,
  isPreset,
  editable,
  saving,
  isDirty,
  draft,
  resetDraft,
  saveCriteria,
  forkVersion,
  openCreate,
} = useWorkspace();
</script>

<template>
  <section v-if="overview" class="research-surface criteria-workspace">
    <article class="criteria-document">
      <header class="criteria-document__header">
        <div>
          <h2>评价准则与有序等级</h2>
          <p>从优到劣排列，每个版本都有独立的数据关联。</p>
        </div>
        <div class="criteria-document__meta">
          <span :class="['badge', editable ? 'amber' : 'teal']">
            <LockKeyhole v-if="!editable" :size="12" />{{
              editable
                ? `V${overview.schema.version} · 草稿可编辑`
                : `V${overview.schema.version} · 已冻结`
            }}
          </span>
        </div>
      </header>
      <div v-if="isPreset" class="notice info">
        预置模式沿用真实矩阵的 L0 至
        L(n−1)。原自然语言标签存在等级数不一致，尚未自动映射；数字等级顺序按原PNS代码由优到劣保留。
      </div>
      <div v-else class="notice info">
        每行一个准则。用“ |
        ”分隔等级，最优等级放最左侧。冻结后不能原地修改，可派生新版本。
      </div>
      <div class="criteria-column-head" aria-hidden="true">
        <span>序号</span>
        <span>准则定义</span>
        <span>等级数</span>
        <span>操作</span>
      </div>
      <div class="criteria-list">
        <div
          v-for="(criterion, index) in draft"
          :key="index"
          class="criteria-row"
        >
          <span class="criterion-index mono">{{
            String(index + 1).padStart(2, "0")
          }}</span>
          <div class="criteria-row__fields">
            <label v-if="editable" class="criterion-field">
              <span class="criterion-field__label">准则名称</span>
              <input
                v-model="criterion.name"
                :name="`criterion-${index + 1}-name`"
                autocomplete="off"
                :disabled="saving"
                class="criterion-name-input"
                :aria-label="`准则${index + 1}名称`"
                maxlength="50"
              />
            </label>
            <div v-else class="criterion-field">
              <span class="criterion-field__label">准则名称</span>
              <h3>{{ criterion.name }}</h3>
            </div>
            <label v-if="editable" class="criterion-field">
              <span class="criterion-field__label">有序等级</span>
              <input
                v-model="criterion.labelsText"
                :name="`criterion-${index + 1}-levels`"
                autocomplete="off"
                :disabled="saving"
                class="labels-input"
                :aria-label="`准则${index + 1}等级`"
                placeholder="优秀 | 良好 | 一般 | 较差…"
              />
            </label>
            <div v-else class="criterion-field">
              <span class="criterion-field__label">有序等级</span>
              <div class="level-tags">
                <span
                  v-for="(label, labelIndex) in labels(criterion.labelsText)"
                  :key="labelIndex"
                >
                  {{ label }}<small v-if="labelIndex === 0">优</small>
                  <small
                    v-else-if="
                      labelIndex === labels(criterion.labelsText).length - 1
                    "
                    >劣</small
                  >
                </span>
              </div>
              <p
                v-if="isPreset && overview.source_labels[criterion.name]"
                class="caption source-labels"
              >
                原文标签（待核验）：{{
                  overview.source_labels[criterion.name]?.join(" / ")
                }}
              </p>
            </div>
          </div>
          <span class="level-count mono"
            >{{ labels(criterion.labelsText).length }}级</span
          >
          <button
            v-if="editable"
            class="text-button delete-btn"
            :aria-label="`删除准则${index + 1}`"
            :disabled="draft.length <= 1 || saving"
            @click="draft.splice(index, 1)"
          >
            <Trash2 :size="15" /><span>删除</span>
          </button>
        </div>
      </div>
      <div class="criteria-actions">
        <button
          v-if="editable"
          class="btn secondary"
          :disabled="saving || draft.length >= 20"
          @click="
            draft.push({ name: '', labelsText: '优秀 | 良好 | 一般 | 较差' })
          "
        >
          <Plus :size="16" />添加准则
        </button>
        <span v-if="editable" class="caption">{{
          isDirty ? "有修改，请保存后切换项目" : "草稿已保存"
        }}</span>
        <div class="button-group">
          <template v-if="editable">
            <button
              v-if="isDirty"
              class="text-button"
              :disabled="saving"
              @click="resetDraft"
            >
              撤销未保存修改
            </button>
            <button
              class="btn secondary"
              :disabled="saving"
              @click="saveCriteria(false)"
            >
              保存草稿
            </button>
            <button
              class="btn primary"
              :disabled="saving"
              @click="saveCriteria(true)"
            >
              <LockKeyhole :size="15" />保存并冻结
            </button>
          </template>
          <button
            v-else-if="!isPreset"
            class="btn primary"
            :disabled="saving"
            @click="forkVersion"
          >
            <Plus :size="16" />派生新版本
          </button>
          <button v-else class="btn primary" @click="openCreate('custom')">
            基于这些准则新建研究<ArrowRight :size="16" />
          </button>
        </div>
      </div>
    </article>
  </section>
</template>
