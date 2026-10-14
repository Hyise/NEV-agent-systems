export interface ReadableReviewSection {
  label: string;
  content: string | null;
}

export interface ReadableReview {
  summary: string | null;
  sections: ReadableReviewSection[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function buildReadableReview(
  original: Record<string, unknown>,
): ReadableReview {
  const summary =
    typeof original.feeling_summary === "string" &&
    original.feeling_summary.trim()
      ? original.feeling_summary
      : null;
  const contents = Array.isArray(original.contents) ? original.contents : [];
  const sections = contents.map((item, index) => {
    const label =
      isRecord(item) &&
      typeof item.structuredname === "string" &&
      item.structuredname.trim()
        ? item.structuredname.trim()
        : `原文 ${index + 1}`;
    const content =
      isRecord(item) && typeof item.content === "string" ? item.content : null;
    return { label, content };
  });

  return { summary, sections };
}
