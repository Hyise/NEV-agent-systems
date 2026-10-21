import { describe, expect, it } from "vitest";
import type { Project } from "./api";
import { resolveInitialProject } from "./workspace";

const projects: Project[] = [
  {
    id: "research-archive",
    name: "研究归档",
    mode: "preset",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "custom-1",
    name: "自定义研究",
    mode: "custom",
    created_at: "2026-01-02T00:00:00Z",
  },
];

describe("mcdm project selection", () => {
  it("restores a previously selected project that still exists", () => {
    expect(resolveInitialProject(projects, "custom-1")).toBe("custom-1");
  });

  it("falls back to the preset project when stored selection no longer exists", () => {
    expect(resolveInitialProject(projects, "removed-project")).toBe(
      "research-archive",
    );
  });
});
