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

export const MODEL_GUIDANCE: Record<string, ModelGuidance> = {
  ridge: {
    summary: "线性、稳定的基线，用于判断复杂模型是否真正带来增益。",
    principle:
      "把各准则的有序语义期望作为特征，通过 L2 正则化的线性回归估计车型份额。",
    value:
      "结构简单、结果稳定，适合建立可复核的线性基准，并观察准则信号是否具有基本解释力。",
    caution:
      "假设准则影响近似线性且可加，难以捕捉阈值效应和复杂交互；系数也不能直接解释为因果关系。",
  },
  random_forest: {
    summary: "基于多棵决策树学习非线性关系和准则之间的交互。",
    principle:
      "对语义概率特征训练多棵随机决策树，再汇总各树预测以降低单棵树的波动。",
    value:
      "不要求线性关系，能够识别准则组合、阈值和局部非线性，可作为稳健的树模型基线。",
    caution:
      "样本较少时可能过拟合，对训练范围之外的月份和车型外推能力有限；特征重要性不等于因果影响。",
  },
  xgboost: {
    summary: "逐轮修正预测误差的提升树模型，擅长结构化数据。",
    principle:
      "按梯度提升方式依次增加决策树，让后续树重点修正前序模型尚未解释的残差。",
    value:
      "通常能有效拟合复杂非线性和特征交互，适合作为高性能结构化数据对照模型。",
    caution:
      "结果对样本量和超参数较敏感，小样本下容易过拟合；模型依赖可选组件，且解释成本高于线性模型。",
  },
  lightgbm: {
    summary: "面向效率优化的梯度提升树，适合较多特征的结构化数据。",
    principle:
      "使用直方图分桶和叶子优先生长策略迭代构建提升树，以较低计算成本拟合复杂关系。",
    value:
      "训练效率高，能够处理非线性和高阶交互，适合与 XGBoost 形成不同实现路径的提升树对照。",
    caution:
      "叶子优先生长在小数据上可能产生过深分支，对参数设置较敏感；模型依赖可选组件，不能据此推断因果。",
  },
  beast_mcdm: {
    summary: "把准则权重、评论语义不确定性与有效时间压力纳入同一效用模型。",
    principle:
      "联合语义期望与心理抽样结果，通过准则重要度和样条理性权重构造效用，再归一化为月度车型份额。",
    value:
      "保留多准则决策研究的机制结构，可输出准则权重，并与通用回归模型进行同口径比较。",
    caution:
      "结果受模拟次数、优化过程和准则版本影响；权重是当前模型与样本下的相对效用，不代表评论提及率或因果效应。",
  },
};

const UNKNOWN_MODEL_GUIDANCE: ModelGuidance = {
  summary: "当前模型由运行服务提供，请结合实现版本与测试指标复核。",
  principle: "当前前端版本尚未登记该模型的计算原理。",
  value: "可作为扩展模型参与同一数据快照和时间切分下的比较。",
  caution: "在确认实现、输入特征和参数口径前，不应仅凭单次指标得出结论。",
};

export const METRIC_GUIDANCE: MetricGuidance[] = [
  {
    key: "R2",
    label: "决定系数 R²",
    direction: "越高越好",
    meaning: "衡量模型相对测试集均值基准解释了多少结果波动，1 表示完全拟合。",
    caution:
      "R² 可以为负；负值表示预测劣于测试集均值基准。测试样本很少时该指标也可能明显波动。",
  },
  {
    key: "WAPE",
    label: "加权绝对百分比误差",
    direction: "越低越好",
    meaning:
      "用绝对误差总和除以实际值总和，以百分比表示整体相对误差，便于理解总体偏差规模。",
    caution:
      "实际值总量很小时结果会不稳定，而且销量或份额较大的车型会对该指标产生更大影响。",
  },
  {
    key: "RMSE",
    label: "均方根误差",
    direction: "越低越好",
    meaning:
      "先平方每条预测误差再取均值和平方根，因此会对较大误差给予更高惩罚。",
    caution:
      "数值单位与预测目标一致，但会被少数大误差显著拉高；不同数据尺度之间不能直接比较。",
  },
  {
    key: "MAE",
    label: "平均绝对误差",
    direction: "越低越好",
    meaning:
      "计算每条预测与真实值之间的平均绝对偏差，表示一次预测通常偏离多少。",
    caution:
      "它不区分高估或低估，对大误差的惩罚弱于 RMSE；不同数据尺度之间不能直接比较。",
  },
];

export function modelGuidance(key: string): ModelGuidance {
  return MODEL_GUIDANCE[key] ?? UNKNOWN_MODEL_GUIDANCE;
}
