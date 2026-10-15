# Skill 使用清单

Skill 是编码代理在特定任务中加载的工作说明，不是应用运行依赖。项目只保存确有项目价值的 Skill；通用流程能力继续使用 Codex 已提供版本，避免重复和触发冲突。外部副本的来源与审计记录见 [项目内 Skill 来源](../.agents/skills/SOURCES.md)。

## 1. 常用组合顺序

1. 先明确需求和边界：较大功能使用全局 `superpowers:brainstorming`。
2. 多步骤变更形成可验证计划：使用 `superpowers:writing-plans`，实现时使用 `superpowers:executing-plans`。
3. 功能或缺陷采用 `superpowers:test-driven-development`；遇到异常先用 `superpowers:systematic-debugging`。
4. 根据代码范围加载一个或多个技术 Skill：FastAPI、项目 Vue、前端设计或安全。
5. 交付前使用 `superpowers:verification-before-completion`；重大变更再执行代码审查流程。

Skill 只能提供方法，不能覆盖用户要求、`AGENTS.md`、项目锁定版本或数据真实性约束。

## 2. Codex 全局已有，不复制到项目

| Skill | 何时使用 | 不用于 |
| --- | --- | --- |
| `superpowers:brainstorming` | 新功能、组件、行为或较大设计变更前 | 已批准计划的机械执行 |
| `superpowers:writing-plans` | 有明确规格的多步骤开发 | 单行文档修正 |
| `superpowers:test-driven-development` | 功能和缺陷实现 | 纯文档、格式化 |
| `superpowers:systematic-debugging` | 测试失败、运行异常、原因未知 | 没有异常证据的随意重构 |
| `superpowers:verification-before-completion` | 所有完成/通过声明之前 | 替代实际测试 |
| `superpowers:requesting-code-review` / `receiving-code-review` | 重大变更交付、处理审查意见 | 无证据地同意或反驳意见 |
| `frontend-design` | 新页面或明显视觉重塑 | 后端、纯逻辑修复 |
| `web-design-guidelines` | 明确要求 UI/UX/可访问性审查 | 普通代码审查 |
| `playwright` | 真实浏览器流程、截图和交互回归 | 可由单元测试充分覆盖的纯函数 |

这些 Skill 由当前 Codex 环境提供，不写入 `.agents/skills/`，以免项目副本过时。

## 3. 项目下载的外部 Skill

| Skill | 触发条件 | 禁用/注意 |
| --- | --- | --- |
| `$fastapi` | 修改 FastAPI 路由、Pydantic 模型、依赖注入、响应或前端静态服务 | 先核对 FastAPI `0.128.8`；上游新特性不是自动升级许可 |
| `$security-best-practices` | 用户明确要求安全最佳实践、安全审查/报告或安全默认实现 | 不为一般代码审查自动生成安全报告；修复前确认行为兼容性 |
| `$security-threat-model` | 用户明确要求仓库威胁建模、攻击路径或 AppSec 模型 | 不用于一般架构摘要；最终模型前需确认暴露面、用户和部署假设 |
| `$emil-design-eng` | 明显视觉重塑、交互细节或动效审查 | 高频研究操作优先稳定与速度；不因展示效果增加无目的动效，不覆盖项目无障碍、字体与架构约束 |

以上外部 Skill 位于 `.agents/skills/`，下载后已检查文件列表、入口说明、脚本和敏感命令迹象。它们不在应用启动时执行。

## 4. 项目自建 Skill

### `$nev-mcdm-vue`

用于修改 Vue 单文件组件、跨页状态、`workspace.ts`、`api.ts` 共享类型、导航或 ECharts 配置。它把代码路由到以下所有者：

- `App.vue`：应用壳和装配；
- `views/`：单页业务展示；
- `workspace.ts`：跨页状态和请求编排；
- `api.ts`：HTTP 与共享类型；
- `Chart.vue`：通用图表生命周期。

后端纯 Python 变更和纯文档拼写修正不触发。Skill 自带场景文件，更新前端架构时必须同步其参考约定。

## 5. 典型选择

| 任务 | 建议 Skill |
| --- | --- |
| 新增后端资源与页面 | brainstorming → writing-plans → TDD → `$fastapi` + `$nev-mcdm-vue` → verification |
| 修复 CSV 校验缺陷 | systematic-debugging → TDD → `$fastapi` → verification |
| 新增分析图表 | brainstorming → `$nev-mcdm-vue`；涉及视觉取舍再加 `frontend-design`；最后 Playwright 与 verification |
| 全站 UI 重塑 | brainstorming → `frontend-design` + `$emil-design-eng` + `$nev-mcdm-vue` → Playwright → verification |
| 明确的全栈安全审查 | `$security-best-practices`，分别读取 FastAPI 与 Vue 参考；按发现运行对应测试 |
| 计划公网部署 | brainstorming → `$security-threat-model` → 架构 ADR；在鉴权和部署控制完成前不得开放 |
| README 拼写修正 | 不加载技术 Skill；检查链接和文字即可 |

## 6. 维护规则

- 外部 Skill 更新必须重新审计并通过 `quick_validate.py`，同步 `SOURCES.md`。
- 新增或更新项目 Skill 后，重新打开项目任务或重启 Codex，使 Skill 目录重新被发现；不要假设当前会话会热加载新元数据。
- 不直接改写下载的第三方 Skill；项目差异写入 `AGENTS.md`、项目自建 Skill 或规范文档。
- 自建 Skill 保持任务特定、入口简短、参考按需读取，并用正向与不触发场景防止范围膨胀。
- 发现 Skill 与项目实现冲突时，以已验证的代码版本和项目规范为准，同时记录冲突，不能静默套用。
