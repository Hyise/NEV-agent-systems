<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import {
  Archive,
  Check,
  Clock3,
  FlaskConical,
  Play,
  XCircle,
} from "lucide-vue-next";
import { METRIC_GUIDANCE, modelGuidance } from "../model-experiments/guidance";
import { useModelExperimentWorkspace } from "../model-experiments/workspace";
import { count, pct, useWorkspace } from "../workspace";

const { experiments, overview } = useWorkspace();
const workspace = useModelExperimentWorkspace();
onMounted(() => void workspace.activate());
onBeforeUnmount(workspace.deactivate);

const statusLabel = (status: string) =>
  ({
    queued: "等待执行",
    running: "正在运行",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  })[status] || status;
const monthRange = (months?: string[]) =>
  !months?.length
    ? "—"
    : months.length === 1
      ? months[0]
      : `${months[0]}—${months.at(-1)}`;
const metricName = (name: string) =>
  ({
    LR: "Ridge",
    RF: "Random Forest",
    "BEAST (Ours)": "BEAST-MCDM",
    "Our Model (Full)": "完整模型",
    "Our Model (Without Pressure)": "去除时间压力",
    "Our Model (Without Num. Scales)": "去除语义数值化",
    "Our Model (Without Sampling)": "去除心理抽样",
  })[name] || name;
</script>

<template>
  <section
    class="research-surface experiments-workspace"
    aria-label="模型实验工作区"
  >
    <div class="experiment-guide">
      <section class="experiment-setup analysis-document">
        <header class="analysis-heading">
          <div>
            <span class="section-kicker">01 · 固定实验输入</span>
            <h2>建立一次可复核实验</h2>
            <p>
              每次运行都会冻结当前准则版本与评价矩阵快照，历史数据不会被模型修改。
            </p>
          </div>
          <span
            :class="[
              'badge',
              overview?.schema.status === 'frozen' ? 'success' : 'neutral',
            ]"
          >
            准则 V{{ overview?.schema.version }} ·
            {{ overview?.schema.status === "frozen" ? "已冻结" : "草稿" }}
          </span>
        </header>
        <div class="experiment-source-strip">
          <div>
            <span>数据来源</span
            ><strong>{{
              overview?.dataset?.name || "尚未导入评价矩阵"
            }}</strong>
          </div>
          <div>
            <span>记录数</span
            ><strong>{{ count(overview?.stats.records || 0) }}</strong>
          </div>
          <div>
            <span>覆盖月份</span
            ><strong>{{ overview?.stats.months || 0 }}</strong>
          </div>
          <div>
            <span>快照摘要</span
            ><strong class="mono">{{
              overview?.dataset?.sha256?.slice(0, 10) || "—"
            }}</strong>
          </div>
        </div>

        <div class="experiment-form">
          <fieldset class="model-selector">
            <legend><span class="section-kicker">02 · 选择模型</span></legend>
            <label
              v-for="model in workspace.capabilities.value"
              :key="model.key"
              :class="[
                'model-option',
                {
                  selected: workspace.selectedModelKeys.value.includes(
                    model.key,
                  ),
                  disabled: !model.available,
                },
              ]"
            >
              <input
                type="checkbox"
                :checked="workspace.selectedModelKeys.value.includes(model.key)"
                :disabled="!model.available || workspace.busy.value"
                @change="workspace.toggleModel(model.key)"
              />
              <span
                ><strong>{{ model.label }}</strong
                ><small>{{
                  model.available
                    ? `实现 ${model.implementation_version}`
                    : model.reason
                }}</small>
                <small class="model-option__summary">{{
                  modelGuidance(model.key).summary
                }}</small></span
              >
              <Check
                v-if="workspace.selectedModelKeys.value.includes(model.key)"
                :size="16"
                aria-hidden="true"
              />
            </label>
            <details class="model-guide">
              <summary>了解各模型的原理、适用价值与局限</summary>
              <div class="model-guide__grid">
                <article
                  v-for="model in workspace.capabilities.value"
                  :key="`guide-${model.key}`"
                >
                  <h3>{{ model.label }}</h3>
                  <dl>
                    <div>
                      <dt>原理</dt>
                      <dd>{{ modelGuidance(model.key).principle }}</dd>
                    </div>
                    <div>
                      <dt>适用价值</dt>
                      <dd>{{ modelGuidance(model.key).value }}</dd>
                    </div>
                    <div>
                      <dt>注意事项</dt>
                      <dd>{{ modelGuidance(model.key).caution }}</dd>
                    </div>
                  </dl>
                </article>
              </div>
            </details>
          </fieldset>

          <div class="experiment-parameters">
            <span class="section-kicker">03 · 设置评估口径</span>
            <div class="parameter-grid">
              <label
                >验证集（月）<input
                  v-model.number="workspace.validationMonths.value"
                  type="number"
                  min="1"
                  max="12"
              /></label>
              <label
                >测试集（月）<input
                  v-model.number="workspace.testMonths.value"
                  type="number"
                  min="1"
                  max="12"
              /></label>
              <label
                >随机种子<input
                  v-model.number="workspace.seed.value"
                  type="number"
                  min="0"
              /></label>
              <label
                >BEAST 模拟次数<input
                  v-model.number="workspace.simulations.value"
                  type="number"
                  min="16"
                  max="2000"
                  step="16"
              /></label>
            </div>
            <p>时间切分固定为“训练 → 验证 → 测试”，测试月份不会参与拟合。</p>
            <button
              class="btn primary experiment-run-button"
              :disabled="
                workspace.busy.value ||
                overview?.schema.status !== 'frozen' ||
                !overview?.stats.records
              "
              @click="workspace.createRun"
            >
              <Play :size="16" />运行所选模型
            </button>
          </div>
        </div>
        <div v-if="workspace.error.value" class="notice error" role="alert">
          {{ workspace.error.value }}
        </div>
      </section>

      <section class="experiment-runs analysis-document">
        <header class="analysis-heading">
          <div>
            <span class="section-kicker">04 · 查看运行结果</span>
            <h2>实验记录</h2>
            <p>切换记录可复核其数据快照、切分范围和模型指标。</p>
          </div>
          <label
            v-if="workspace.runs.value.length"
            class="experiment-history-select"
            >历史记录
            <select v-model="workspace.selectedRunId.value">
              <option
                v-for="run in workspace.runs.value"
                :key="run.id"
                :value="run.id"
              >
                {{ statusLabel(run.status) }} · {{ run.id.slice(0, 8) }}
              </option>
            </select>
          </label>
        </header>

        <div v-if="workspace.selectedRun.value" class="run-detail">
          <div class="run-status-row">
            <span
              :class="[
                'run-status',
                `is-${workspace.selectedRun.value.status}`,
              ]"
            >
              <Clock3
                v-if="
                  ['queued', 'running'].includes(
                    workspace.selectedRun.value.status,
                  )
                "
                :size="15"
              />
              <Check
                v-else-if="workspace.selectedRun.value.status === 'completed'"
                :size="15"
              />
              <XCircle v-else :size="15" />
              {{ statusLabel(workspace.selectedRun.value.status) }}
            </span>
            <span v-if="workspace.selectedRun.value.current_model"
              >当前模型：{{ workspace.selectedRun.value.current_model }}</span
            >
            <span class="mono"
              >{{
                Math.round(workspace.selectedRun.value.progress * 100)
              }}%</span
            >
            <button
              v-if="
                ['queued', 'running'].includes(
                  workspace.selectedRun.value.status,
                )
              "
              class="text-button"
              @click="workspace.cancelRun"
            >
              取消实验
            </button>
          </div>
          <div class="run-progress" aria-hidden="true">
            <span
              :style="{
                width: `${workspace.selectedRun.value.progress * 100}%`,
              }"
            />
          </div>
          <p v-if="workspace.selectedRun.value.error_message" class="run-error">
            {{ workspace.selectedRun.value.error_message }}
          </p>

          <div v-if="workspace.selectedRun.value.result" class="run-evidence">
            <div class="split-ledger">
              <div>
                <span>训练集</span
                ><strong>{{
                  monthRange(workspace.selectedRun.value.result.split.train)
                }}</strong>
              </div>
              <div>
                <span>验证集</span
                ><strong>{{
                  monthRange(
                    workspace.selectedRun.value.result.split.validation,
                  )
                }}</strong>
              </div>
              <div>
                <span>测试集</span
                ><strong>{{
                  monthRange(workspace.selectedRun.value.result.split.test)
                }}</strong>
              </div>
              <div>
                <span>快照</span
                ><strong class="mono">{{
                  workspace.selectedRun.value.dataset?.snapshot_sha256.slice(
                    0,
                    10,
                  )
                }}</strong>
              </div>
            </div>
            <p class="run-metric-caption">
              下表仅统计测试月份；验证集指标与模型参数一同保存在运行记录中，不参与测试成绩计算。
            </p>
            <section class="metric-guide" aria-label="评价指标说明">
              <header>
                <h3>如何阅读评价指标</h3>
                <p>
                  四项指标均基于本次运行的测试月份。比较模型时应保持数据切分、车型范围和样本量一致，不能用单一指标代替完整判断。
                </p>
              </header>
              <div class="metric-guide__grid">
                <article v-for="metric in METRIC_GUIDANCE" :key="metric.key">
                  <div>
                    <strong>{{ metric.label }}</strong>
                    <span>{{ metric.direction }}</span>
                  </div>
                  <p>{{ metric.meaning }}</p>
                  <small>{{ metric.caution }}</small>
                </article>
              </div>
            </section>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>实际运行模型</th>
                    <th>版本</th>
                    <th class="numeric">R² ↑</th>
                    <th class="numeric">WAPE ↓</th>
                    <th class="numeric">RMSE ↓</th>
                    <th class="numeric">MAE ↓</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="model in workspace.selectedRun.value.result.models"
                    :key="model.key"
                    :class="{ highlighted: model.key === 'beast_mcdm' }"
                  >
                    <td>
                      <strong>{{ model.label }}</strong>
                    </td>
                    <td class="mono">{{ model.implementation_version }}</td>
                    <td class="numeric mono">
                      {{ model.metrics.R2.toFixed(4) }}
                    </td>
                    <td class="numeric mono">{{ pct(model.metrics.WAPE) }}</td>
                    <td class="numeric mono">
                      {{ model.metrics.RMSE.toFixed(6) }}
                    </td>
                    <td class="numeric mono">
                      {{ model.metrics.MAE.toFixed(6) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div v-else class="empty compact">
          <FlaskConical :size="30" />
          <h3>还没有可执行实验</h3>
          <p>选择模型并运行后，结果会保存在这里。</p>
        </div>
      </section>
    </div>

    <details
      v-if="experiments.baseline.length"
      class="archive-ledger analysis-document"
    >
      <summary>
        <Archive :size="16" />查看原研究归档指标（只读，非本系统重新运行结果）
      </summary>
      <div class="experiment-ledger">
        <header class="analysis-heading">
          <div>
            <h2>原研究实验档案</h2>
            <p>以下数值来自研究压缩包，保留用于溯源，不与上方新实验混写。</p>
          </div>
          <span class="badge neutral">来源：研究压缩包</span>
        </header>
        <section class="experiment-section">
          <header class="experiment-section__heading">
            <h3>基线模型比较</h3>
            <p>记录值 · 非独立测试结论</p>
          </header>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>模型</th>
                  <th class="numeric">R² ↑</th>
                  <th class="numeric">WAPE ↓</th>
                  <th class="numeric">RMSE ↓</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in experiments.baseline"
                  :key="row.model"
                  :class="{ highlighted: row.model.includes('BEAST') }"
                >
                  <td>
                    <strong>{{ metricName(row.model) }}</strong>
                  </td>
                  <td class="numeric mono">{{ row.R2.toFixed(4) }}</td>
                  <td class="numeric mono">{{ pct(row.WAPE) }}</td>
                  <td class="numeric mono">{{ row.RMSE.toFixed(6) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section class="experiment-section">
          <header class="experiment-section__heading">
            <h3>消融实验</h3>
            <p>
              去除时间压力的归档R²略高于完整模型，不预设各模块必然带来提升。
            </p>
          </header>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>实验变体</th>
                  <th class="numeric">R² ↑</th>
                  <th class="numeric">WAPE ↓</th>
                  <th class="numeric">RMSE ↓</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in experiments.ablation" :key="row.model">
                  <td>{{ metricName(row.model) }}</td>
                  <td class="numeric mono">{{ row.R2.toFixed(4) }}</td>
                  <td class="numeric mono">{{ pct(row.WAPE) }}</td>
                  <td class="numeric mono">{{ row.RMSE.toFixed(6) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </details>
  </section>
</template>
