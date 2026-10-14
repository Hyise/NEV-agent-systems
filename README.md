# 观衡 · 新能源汽车研究平台

面向汽车企业分析人员和研究人员。启动后先进入研究平台，可选择评论数据采集、多准则决策，或查看自适应评估的建设规划。

## 当前能力

- 预置研究：读取用户提供的 `llm-beast-mcdm(1).zip`，展示1609条车型月份记录、132种车型、24个月和十项准则。
- 研究总览、数据浏览/搜索/分页、归档权重曲线、条件选择份额比较、基线和消融实验档案。
- 自定义项目、准则编辑、冻结、派生新版本；SQLite持久化、版本隔离和并发修改保护。
- 按冻结准则导入UTF-8加工CSV、严格验证概率与月度数据；导出加工CSV和带来源的JSON研究快照。
- 三个平级功能入口和模块级路由；自适应评估当前仅有规划说明，不提供模拟功能。
- 评论采集采用“先发现目录、再选择采集”的两步流程：目录独立缓存按 `series_id` 去重后的前 1000 个唯一车系，刷新失败或取消时继续保留上一版可用目录。
- 两种采集模式都要求显式选择车系：“功能验证”选择 1～3 个车系、每车系最多 2 页；“正式采集”选择 1～1000 个车系并采集全部评论。日常开发和验收只使用功能验证，不运行完整 1000 车系采集。
- 评论任务保存不可变车系快照，并支持完整原始口碑保存、限速、重试、暂停、继续、停止、断点和 JSONL 导出。
- 评论数据工作台按“获取数据—管理数据—用于研究”组织：既可在线采集，也可通过 JSON/JSONL 两步校验后人工导入；资产表支持查询、标签、备注和分析启用状态，原始评论始终只读。
- 永久删除评论时必须填写原因并输入评论 ID；删除只保留不含正文的最小审计和重采墓碑，已经建立的研究快照与结果继续可复核。
- 多准则工作台支持从已采集完整评论中发现准则候选，经人工审核并冻结后，使用 DeepSeek `deepseek-flash` 对每条评论提取多项准则、等级、原文证据和简短依据；结果绑定评论哈希、准则指纹、模型和 Prompt 哈希。

**当前图表和指标是原研究归档，不是本系统新训练结果。** 原研究的训练与测试时间存在重叠，界面明确标注。评论级 LLM 标注已经接入，但标注不会自动生成训练矩阵；模型训练、新预测、登录协作及 Word/PDF 报告尚未接入。

系统设计、后续模块和验收标准见 [系统设计与实施路线](docs/系统设计与实施路线.md)。首次运行前请阅读 [运行须知](docs/运行须知.md)，接口见 [API与数据契约](docs/API与数据契约.md)。历史双研究入口决策见 [ADR-0001](docs/ADR/0001-双研究系统平台与模块路由.md)，采集系统独立化取舍见 [ADR-0002](docs/ADR/0002-评论采集作为独立平台子系统.md)，目录与任务解耦见 [ADR-0003](docs/ADR/0003-车系目录发现与评论任务解耦.md)，实际结果见 [评论数据采集系统验收记录](docs/评论数据采集系统验收记录.md)。

## 工程治理

- 开发边界与模块职责：[开发与架构规范](docs/开发与架构规范.md)
- 变更所需验证证据：[测试与质量门禁](docs/测试与质量门禁.md)
- 代码变化对应的文档责任：[文档同步规范](docs/文档同步规范.md)
- 编码代理的 Skill 选择与触发边界：[Skill 使用清单](docs/Skill使用清单.md)
- 重大架构选择记录方式：[ADR 说明](docs/ADR/README.md)
- 分支、提交、Pull Request 与版本标签：[Git 版本管理](docs/开发与架构规范.md#10-git-版本管理)

编码代理从根目录 [AGENTS.md](AGENTS.md) 读取常驻约束，再按任务加载上述详细规范；外部 Skill 的来源和审计记录保存在 [`.agents/skills/SOURCES.md`](.agents/skills/SOURCES.md)。

## 本机启动

如需使用评论语义分析，先复制 `.env.example` 为 `.env`，只在本机填写：

```dotenv
DEEPSEEK_API_KEY=你的本机密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_REQUEST_TIMEOUT_SECONDS=120
```

`.env` 已被 Git 忽略。未配置 Key 时，评论采集、归档浏览和人工准则编辑仍可使用，仅创建大模型任务会返回明确的 503 提示。选中的公开评论正文会传输给 DeepSeek API，请在授权范围内少量验证并自行管理、轮换密钥。

当前机器已经准备了依赖。Windows 下直接双击项目根目录的 `启动观衡网站.cmd`；脚本会在需要时重新构建前端、启动服务并打开浏览器。停止时双击 `停止观衡网站.cmd`。

命令行等价方式：

```powershell
Set-Location 'E:\aaaxz\daima1022\软著\nev-mcdm-platform'
.\scripts\start-site.ps1
```

脚本会自动打开 <http://127.0.0.1:8018> 的研究平台入口。接口文档：<http://127.0.0.1:8018/docs>。

仅启动服务、不打开浏览器：

```powershell
.\scripts\start-site.ps1 -NoBrowser
```

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
.\scripts\install-collection-browser.ps1 -PythonExe '.\.venv\Scripts\python.exe'
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

## 评论资产验证夹具

人工导入只接受 UTF-8 JSON 或 JSONL，最大 8 MB、最多 10,000 条。仓库仅保存脱敏合成夹具：

- `backend/tests/fixtures/import/reviews-valid.jsonl`：可完成“选择文件→校验预览→确认写入”的正例。
- `backend/tests/fixtures/import/reviews-invalid.jsonl`：用于验证行号、非法车系 ID、非 HTTPS 来源和空正文错误；不得确认写入。

验收永久删除时必须使用临时 SQLite 数据库或上述合成数据，不得对 `.runtime/platform.sqlite3` 中的正式采集评论做删除演练。

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
backend/collection/ 版本化车系目录、评论采集、评论资产治理、共享外部访问协调器、仓储、适配器和API
frontend/          Vue 3 + TypeScript + ECharts
algorithms/reference/  原研究代码副本（归档脚本生成）
backend/data/research/ 原始加工数据和报表（归档脚本生成）
scripts/           归档与本机启动脚本
docs/              设计、接口、验收
.runtime/          本机数据库、日志和进程记录
output/playwright/ 浏览器验收截图
```

目前的 SQLite 数据库、采集结果和研究归档为本机数据，不计入源码仓库。采集车系、评论、任务断点与研究项目共用 `.runtime/platform.sqlite3`；正式迁移需单独备份该文件和 `backend/data/research`。正式采集以实验室对汽车之家授权持续有效为前提，系统不会绕过 403、429 或验证页面。
