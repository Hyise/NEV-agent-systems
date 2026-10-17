import type { ReviewImportItem } from "./api";

export const MAX_REVIEW_IMPORT_FILE_BYTES = 32 * 1024 * 1024;

export function decodeReviewImport(bytes: Uint8Array): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("文件必须使用有效的 UTF-8 编码");
  }
}

export function parseReviewImportText(text: string): ReviewImportItem[] {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("文件内容为空");
  if (trimmed.startsWith("[")) {
    const value = JSON.parse(trimmed) as unknown;
    if (!Array.isArray(value)) throw new Error("JSON 文件顶层必须是数组");
    return value as ReviewImportItem[];
  }
  if (trimmed.startsWith("{")) {
    try {
      return [JSON.parse(trimmed) as ReviewImportItem];
    } catch {
      if (!trimmed.includes("\n")) throw new Error("第 1 行不是有效的 JSON");
    }
  }

  const items: ReviewImportItem[] = [];
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line.trim()) continue;
    try {
      items.push(JSON.parse(line) as ReviewImportItem);
    } catch {
      throw new Error(`第 ${index + 1} 行不是有效的 JSON`);
    }
  }
  return items;
}
