import type { ReviewImportItem } from "./api";

export const MAX_REVIEW_IMPORT_FILE_BYTES = 32 * 1024 * 1024;
export const MAX_REVIEW_IMPORT_FILES = 800;

const SUPPORTED_REVIEW_IMPORT_FILE = /\.(json|jsonl|csv|xlsx)$/i;

export interface PreparedReviewImportFiles {
  files: File[];
  skippedCount: number;
}

export function reviewImportFileLabel(file: File): string {
  return file.webkitRelativePath || file.name;
}

export function prepareReviewImportFiles(
  input: File[],
  options: { fromDirectory?: boolean } = {},
): PreparedReviewImportFiles {
  const files: File[] = [];
  let skippedCount = 0;

  for (const file of input) {
    const temporary = file.name.startsWith("~$");
    const supported = SUPPORTED_REVIEW_IMPORT_FILE.test(file.name);
    if (options.fromDirectory && (temporary || !supported)) {
      skippedCount += 1;
      continue;
    }
    if (temporary) throw new Error(`${file.name} 是 Excel 临时文件`);
    if (!supported) throw new Error(`${file.name} 不是支持的数据文件`);
    files.push(file);
  }

  if (!files.length) {
    throw new Error(
      options.fromDirectory
        ? "所选文件夹中没有可导入的数据文件"
        : "请选择评论数据文件",
    );
  }
  if (files.length > MAX_REVIEW_IMPORT_FILES) {
    throw new Error(`一次最多批量导入 ${MAX_REVIEW_IMPORT_FILES} 个文件`);
  }
  const oversized = files.find(
    (file) => file.size > MAX_REVIEW_IMPORT_FILE_BYTES,
  );
  if (oversized) throw new Error(`${oversized.name} 超过 32 MB`);

  if (options.fromDirectory) {
    files.sort((left, right) =>
      reviewImportFileLabel(left).localeCompare(
        reviewImportFileLabel(right),
        "zh-CN",
        { numeric: true },
      ),
    );
  }
  return { files, skippedCount };
}

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
