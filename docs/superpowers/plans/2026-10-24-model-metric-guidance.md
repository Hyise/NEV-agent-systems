# 模型与指标说明 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在模型实验页就地解释五个可执行模型与四个测试指标，同时保持既有实验行为不变。

**Architecture:** 新建一个纯展示说明模块，集中维护模型与指标文案，避免继续扩大 `ExperimentsView.vue`；实验页负责把能力列表映射为模型说明，并在结果表前渲染指标说明。样式沿用当前研究仪器型设计，交互只使用原生 `details/summary`。

**Tech Stack:** Vue 3、TypeScript、Vitest、CSS、原生 HTML details/summary。

**Spec:** `docs/superpowers/specs/2026-10-24-model-metric-guidance-design.md`

## Global Constraints

- 不改变后端模型、指标公式、数据快照或历史实验记录。
- 不新增前端依赖。
- 模型摘要在选择模型时常驻可见，详细内容渐进展开。
- 指标说明只解释测试集语境，不把单一指标描述为充分结论。
- 文案必须覆盖负 R²、WAPE 比例、RMSE 对大误差敏感和 MAE 平均绝对偏差。

## Review Focus

- 后端返回未知模型键时，页面仍显示原能力项且不崩溃；契约测试验证回退文案。
- 可选依赖缺失的模型仍可阅读说明，但勾选状态继续由既有 `available` 控制；契约测试保留禁用绑定。
- 无运行结果时不显示脱离上下文的指标网格；契约测试限定其位于结果条件块内。
- 负 R² 的解释不能误写为“无效”或百分比；文案测试固定“劣于测试集均值基准”。
- 说明不能遮挡或替代既有选择和运行控件；源代码契约测试同时断言 checkbox、运行按钮与结果表仍存在。

---

### Task 1: 集中模型与指标说明并接入实验页

**Files:**
- Create: `frontend/src/modules/mcdm/model-experiments/guidance.ts`
- Create: `frontend/src/modules/mcdm/model-experiments/guidance.spec.ts`
- Modify: `frontend/src/modules/mcdm/views/ExperimentsView.vue`
- Modify: `frontend/src/styles/pages.css`

**Interfaces:**
- Consumes: `ModelCapability.key`、`ModelCapability.label` 和既有运行结果条件块。
- Produces: `MODEL_GUIDANCE: Record<string, ModelGuidance>`、`METRIC_GUIDANCE: MetricGuidance[]`、`modelGuidance(key: string): ModelGuidance`。

- [x] **Step 1: 写失败测试**

在 `guidance.spec.ts` 断言五个模型均有 `summary`、`principle`、`value`、`caution`；四个指标按 `R2/WAPE/RMSE/MAE` 顺序存在并包含方向；断言 R² 文案包含“劣于测试集均值基准”；断言未知模型返回中性说明。对 `ExperimentsView.vue?raw` 断言说明模块、原生 `details`、指标网格及既有 checkbox/运行按钮/结果表共同存在，并确认指标网格位于 `selectedRun.value.result` 条件块中。

- [x] **Step 2: 运行测试并确认 RED**

Run: `npm test -- --run src/modules/mcdm/model-experiments/guidance.spec.ts`

Expected: FAIL，原因是 `guidance.ts` 尚不存在或实验页尚未接入说明。

- [x] **Step 3: 实现最小说明模块**

在 `guidance.ts` 定义：

```ts
export interface ModelGuidance {
  summary: string;
  principle: string;
  value: string;
  caution: string;
}

export interface MetricGuidance {
  key: "R2" | "WAPE" | "RMSE" | "MAE";
  label: string;
  direction: "越高越好" | "越低越好";
  meaning: string;
  caution: string;
}

export const MODEL_GUIDANCE: Record<string, ModelGuidance>;
export const METRIC_GUIDANCE: MetricGuidance[];
export function modelGuidance(key: string): ModelGuidance;
```

文案按设计文档覆盖 Ridge、随机森林、XGBoost、LightGBM、BEAST-MCDM，未知键使用“当前模型由运行服务提供，请结合实现版本与测试指标复核”的中性回退。

- [x] **Step 4: 接入实验页与样式**

模型卡版本行下添加 `modelGuidance(model.key).summary`；模型选择区域末尾添加 `details.model-guide`，完整列出当前能力列表的原理、适用价值和注意事项。运行结果条件块内、结果表前添加 `section.metric-guide`，循环 `METRIC_GUIDANCE` 渲染四项指标。`pages.css` 增加紧凑网格、边界、字体层级以及窄屏单列规则，不更改既有控件选择器行为。

- [x] **Step 5: 运行聚焦测试并确认 GREEN**

Run: `npm test -- --run src/modules/mcdm/model-experiments/guidance.spec.ts`

Expected: PASS。

- [x] **Step 6: 运行完整前端门禁**

Run: `npm test -- --run`

Run: `npm run typecheck`

Run: `npm run format:check`

Run: `npm run check:design`

Run: `npm run build`

Expected: 全部退出码为 0；生产构建可以保留既有大 chunk 警告，但不得出现错误。

- [x] **Step 7: 浏览器验收**

在 `http://127.0.0.1:8029/#/mcdm` 进入“模型实验”，确认五个模型摘要可见、详细说明可用键盘展开、运行结果中四项指标说明可见，且模型勾选和历史结果切换不受影响。

- [x] **Step 8: 提交当前分支**

```bash
git add frontend/src/modules/mcdm/model-experiments/guidance.ts frontend/src/modules/mcdm/model-experiments/guidance.spec.ts frontend/src/modules/mcdm/views/ExperimentsView.vue frontend/src/styles/pages.css docs/superpowers/specs/2026-10-24-model-metric-guidance-design.md docs/superpowers/plans/2026-10-24-model-metric-guidance.md
git commit -m "feat(mcdm): explain experiment models and metrics"
```
