# 项目内 Skill 来源清单

本目录只保存本项目需要、且已人工审阅过入口说明的 Skill。下载日期均为 2026-09-26。

| Skill | 上游来源 | 上游路径 | 下载分支 | 许可证 | 本地审计结论 |
| --- | --- | --- | --- | --- | --- |
| `security-best-practices` | [openai/skills](https://github.com/openai/skills) | `skills/.curated/security-best-practices` | `main` | Apache-2.0，见随附 `LICENSE.txt` | 仅 Markdown、YAML 与许可证；无脚本、无令牌读取、无主动联网逻辑。仅在明确要求安全审查或安全编码时触发。 |
| `security-threat-model` | [openai/skills](https://github.com/openai/skills) | `skills/.curated/security-threat-model` | `main` | Apache-2.0，见随附 `LICENSE.txt` | 仅 Markdown、YAML 与许可证；无脚本、无令牌读取、无主动联网逻辑。仅在明确要求威胁建模时触发。 |
| `fastapi` | [fastapi/fastapi](https://github.com/fastapi/fastapi) | `fastapi/.agents/skills/fastapi` | `master` | 上游仓库 MIT；下载路径未单独携带许可证文件 | 仅 Markdown 说明与参考资料；无脚本、无令牌读取、无主动联网逻辑。用于 FastAPI、Pydantic、路由和依赖注入变更。 |
| `nev-mcdm-vue` | 本项目维护 | `.agents/skills/nev-mcdm-vue` | 不适用 | 项目内部文件，随本项目授权 | 面向本项目 Vue 前端边界的轻量约束；随项目架构一起维护。 |

## 下载与更新规则

1. 外部 Skill 不自动更新，也不在运行时联网拉取内容。
2. 更新前先比较上游差异，重新检查入口文件、脚本、网络访问、令牌读取和破坏性命令。
3. 更新后运行 `quick_validate.py`，并同步本文件中的下载日期与审计结论。
4. 上游许可证以各 Skill 随附许可证或上游仓库许可证为准；不得删除随附的 `LICENSE.txt`。
5. Skill 是面向编码代理的高权限说明。若其内容与用户要求、项目 `AGENTS.md` 或安全边界冲突，以更高层级约束为准，并在交付说明中记录偏差。

## 本次校验记录

- `security-best-practices`：官方 `quick_validate.py` 通过。
- `security-threat-model`：Windows 默认 GBK 环境下校验器读取 UTF-8 标点时报编码错误；设置 `PYTHONUTF8=1` 后通过，文件本身无需修改。
- `fastapi`：官方 `quick_validate.py` 通过。
