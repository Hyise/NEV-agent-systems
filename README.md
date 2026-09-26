# 观衡 · 新能源汽车情景多准则决策分析系统

第一阶段可运行版本 `0.1.0`。面向汽车企业分析人员和研究人员。

## 当前能力

- 预置研究：读取用户提供的 `llm-beast-mcdm(1).zip`，展示1609条车型月份记录、132种车型、24个月和十项准则。
- 研究总览、数据浏览/搜索/分页、归档权重曲线、条件选择份额比较、基线和消融实验档案。
- 自定义项目、准则编辑、冻结、派生新版本；SQLite持久化、版本隔离和并发修改保护。
- 按冻结准则导入UTF-8加工CSV、严格验证概率与月度数据；导出加工CSV和带来源的JSON研究快照。

**当前图表和指标是原研究归档，不是本系统新训练结果。** 原研究的训练与测试时间存在重叠，界面明确标注。原始评论LLM分析、训练/推理worker、完整矩阵生成、登录协作及Word/PDF报告尚未接入。

系统设计、后续模块和验收标准见 [系统设计与实施路线](docs/系统设计与实施路线.md)。首次运行前请阅读 [运行须知](docs/运行须知.md)，接口见 [API与数据契约](docs/API与数据契约.md)，本轮结构取舍见 [代码审查记录](docs/代码审查记录.md)。

## 工程治理

- 开发边界与模块职责：[开发与架构规范](docs/开发与架构规范.md)
- 变更所需验证证据：[测试与质量门禁](docs/测试与质量门禁.md)
- 代码变化对应的文档责任：[文档同步规范](docs/文档同步规范.md)
- 编码代理的 Skill 选择与触发边界：[Skill 使用清单](docs/Skill使用清单.md)
- 重大架构选择记录方式：[ADR 说明](docs/ADR/README.md)
- 分支、提交、Pull Request 与版本标签：[Git 版本管理](docs/开发与架构规范.md#10-git-版本管理)

编码代理从根目录 [AGENTS.md](AGENTS.md) 读取常驻约束，再按任务加载上述详细规范；外部 Skill 的来源和审计记录保存在 [`.agents/skills/SOURCES.md`](.agents/skills/SOURCES.md)。

## 本机启动

当前机器已经准备了依赖和生产前端，执行：

```powershell
Set-Location 'E:\aaaxz\daima1022\软著\nev-mcdm-platform'
.\scripts\start-local.ps1 -PythonExe 'E:\anaconda927\envs\py311\python.exe'
```

然后打开 <http://127.0.0.1:8018>。接口文档：<http://127.0.0.1:8018/docs>。

停止本启动脚本启动的进程：

```powershell
.\scripts\stop-local.ps1
```

本版本仅监听127.0.0.1，无用户鉴权；用于本机研究和评审，不直接暴露到公网。

## 新环境准备

推荐Python 3.11、Node.js 22.12+。本环境验证使用Python 3.11.15和Node.js 24.15.0。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe scripts/bootstrap_research.py --archive '原研究压缩包的绝对路径'
Set-Location frontend
npm ci
npm run build
Set-Location ..
.\scripts\start-local.ps1 -PythonExe '.\.venv\Scripts\python.exe'
```

归档脚本只复制明确列出的数据和参考源码，不执行研究代码，也不覆盖已有研究归档。归档位于 `backend/data/research`，来源清单保存原压缩包及文件SHA-256。

## 开发模式

后端：

```powershell
python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8018 --reload
```

另一个终端中：

```powershell
Set-Location frontend
npm run dev
```

前端开发地址 <http://127.0.0.1:5178>，`/api`代理到后端。前端生产构建后由后端单端口提供。

## 验证

```powershell
python -m pytest backend/tests -q
Set-Location frontend
npm run build
```

本次验证记录见 `docs/阶段一验收记录.md`，浏览器截图在 `output/playwright/`。

## 数据与计算约定

- 份额按当前数据集当月所有入选车型的销量总和归一化；搜索仅过滤显示，不改变分母。
- 归档份额估计仅2025年11月和12月可用；其他月份明确为空。
- 自定义准则等级由优到劣排列，CSV概率键为L0、L1…，按键映射而非JSON原始顺序读取。
- 自定义版本冻结后不可修改。派生新版本后，旧数据仍属于原版本，不自动迁移。
- 预置自然语言等级定义与原模型维数不完全一致；使用数值等级代码浏览，不猜测缺失标签。
- 原研究结果和代码位于独立归档；后续修复版采用新的模型、数据和实验版本。

## 目录

```text
backend/           FastAPI、SQLite、数据与准则规则、测试
frontend/          Vue 3 + TypeScript + ECharts
algorithms/reference/  原研究代码副本（归档脚本生成）
backend/data/research/ 原始加工数据和报表（归档脚本生成）
scripts/           归档与本机启动脚本
docs/              设计、接口、验收
.runtime/          本机数据库、日志和进程记录
output/playwright/ 浏览器验收截图
```

目前的SQLite数据库和研究归档为本机数据，不计入源码仓库。正式迁移需单独备份 `.runtime/platform.sqlite3` 和 `backend/data/research`。
