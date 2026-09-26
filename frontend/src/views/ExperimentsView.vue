<script setup lang="ts">
import { FlaskConical } from "lucide-vue-next";
import { pct, useWorkspace } from "../workspace";

const { experiments } = useWorkspace();
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
  <section class="experiments-workspace">
    <div class="notice info source-status">
      实验档案保留原研究数值。后续修复版将重新进行时间切分、基线比较与消融验证，并建立独立版本。
    </div>
    <template v-if="experiments.baseline.length">
      <div class="panel">
        <div class="panel-heading">
          <div>
            <h2>基线模型比较</h2>
            <p>记录值 · 非独立测试结论</p>
          </div>
          <span class="badge neutral">来源：研究压缩包</span>
        </div>
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
      </div>
      <div class="panel spaced">
        <div class="panel-heading">
          <div>
            <h2>消融实验</h2>
            <p>
              去除时间压力的归档R²略高于完整模型，不预设各模块必然带来提升。
            </p>
          </div>
        </div>
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
      </div>
    </template>
    <div v-else class="panel empty">
      <FlaskConical :size="34" />
      <h3>此项目暂无实验记录</h3>
      <p>算法接入后，每次实验将绑定自己的准则、数据和训练版本。</p>
    </div>
  </section>
</template>
