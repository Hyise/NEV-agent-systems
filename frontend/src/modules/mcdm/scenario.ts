export type ScenarioCurveKind = "weights" | "rationality";

export function reconcileCurveCriteria(
  current: string[],
  available: string[],
  defaultCount = 3,
): string[] {
  const availableSet = new Set(available);
  const retained = current.filter((name) => availableSet.has(name));
  return retained.length ? retained : available.slice(0, defaultCount);
}

export function scenarioSourceNote(
  isPreset: boolean,
  kind: ScenarioCurveKind,
): string {
  if (isPreset) {
    const meaning =
      kind === "weights"
        ? "准则权重由各准则效用范围归一化得到。"
        : "理性混合权重是归档模型中的混合系数，不是对真实消费者理性的直接测量。";
    return `${meaning} 此处使用原研究后处理报表，不能据此单独判断政策因果效应。`;
  }
  const meaning =
    kind === "weights"
      ? "准则权重是所选BEAST实验拟合得到的全局重要度。"
      : "理性混合权重是模型中期望效用项与心理抽样项之间的混合系数，不是对真实消费者理性的直接测量。";
  return `${meaning} 2026年无时间压力时曲线可能保持水平；不能据此单独判断政策因果效应。`;
}
