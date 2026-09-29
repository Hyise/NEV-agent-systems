export type ModuleId = "mcdm" | "adaptive";
export type ModuleStatus = "available" | "planned";

export interface ResearchModule {
  id: ModuleId;
  name: string;
  status: ModuleStatus;
  statusLabel: string;
  routeName: ModuleId;
  path: `/${ModuleId}`;
  actionLabel: string;
  accent: `#${string}`;
}

export const researchModules = [
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
] as const satisfies readonly ResearchModule[];
