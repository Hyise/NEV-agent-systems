import { describe, expect, it } from "vitest";
import { researchModules } from "./modules";

describe("researchModules", () => {
  it("offers the available MCDM system and the planned adaptive system", () => {
    expect(researchModules).toEqual([
      {
        id: "mcdm",
        name: "多准则决策系统",
        status: "available",
        statusLabel: "已开放",
        routeName: "mcdm",
        path: "/mcdm",
        actionLabel: "进入多准则系统",
        accent: "#235F68",
      },
      {
        id: "adaptive",
        name: "自适应评估系统",
        status: "planned",
        statusLabel: "规划中",
        routeName: "adaptive",
        path: "/adaptive",
        actionLabel: "查看系统规划",
        accent: "#625C82",
      },
    ]);
  });

  it("uses unique identifiers, paths, and route names", () => {
    expect(new Set(researchModules.map(({ id }) => id)).size).toBe(2);
    expect(new Set(researchModules.map(({ path }) => path)).size).toBe(2);
    expect(
      new Set(researchModules.map(({ routeName }) => routeName)).size,
    ).toBe(2);
  });
});
