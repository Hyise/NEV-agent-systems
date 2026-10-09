# 观衡项目开发约束

本文件是后续人工开发与编码代理的常驻入口。详细规则按任务读取，不要一次性把全部文档加载进上下文。

## 项目边界

- 当前软件主体是“观衡研究平台”，面向汽车企业分析人员和研究人员，提供评论数据采集、多准则决策和自适应评估三个平级功能入口。
- 阶段一展示原研究归档并提供项目、准则版本、数据导入和结果浏览；不把归档结果表述成系统重新训练所得。
- 评论采集系统先独立发现并发布版本化车系目录，再由用户显式选择车系创建评论任务；只保存汽车之家车系和完整原始口碑，不拆分、拼接、改写评论。研究模块只读选择采集资产，不直接调用汽车之家适配器。
- 第二项“自适应评估”当前只有入口与规划说明页。研究材料未接入前，不添加评估表单、模拟数据、业务模型或 API。

## 不可破坏的约束

- 研究结果、数据来源、时间范围和局限必须可追溯；不得编造数据、指标、模型运行或验证结果。
- 预置研究归档只读；自定义准则冻结后不可修改，派生版本不得自动迁移旧数据。
- API、存储与界面使用同一业务口径。改变口径时必须同步契约、测试与文档。
- 本机服务无鉴权且只监听 `127.0.0.1`，不得将其直接暴露到公网。
- 不执行原研究归档中的未知代码；归档导入只复制白名单文件并记录 SHA-256。
- 保留用户已有变更。除非明确授权，不重置数据库、删除研究归档或引入新的运行依赖。

## 代码边界

- `backend/app.py`：HTTP 路由、请求编排与响应；`domain.py`：模型、校验和纯业务规则；`store.py`：SQLite 持久化；`research.py`：只读研究归档适配。
- `backend/collection/catalog_domain.py`、`catalog_repository.py`、`catalog_service.py`、`catalog_api.py`：版本化车系目录的状态、暂存/原子发布、后台发现和 HTTP 边界；不得把目录刷新重新塞回评论任务。
- `backend/collection/coordination.py`：目录发现与评论采集共享的单一外部访问预约；所有终态和异常路径都必须释放预约。
- `backend/collection/domain.py`、`repository.py`、`service.py`、`api.py`：评论任务契约、不可变 `collection_job_series` 快照、采集编排和 HTTP 边界。新任务不得写 `series_manifest`；旧任务只允许通过该字段兼容读取。
- `backend/collection/autohome.py`：汽车之家目录与评论适配器；适配器不写库，仓储不发网络请求。
- `frontend/src/App.vue` 与 `router/`：平台路由和模块装配；`platform/`：研究目录与模块元数据；`modules/mcdm/`：多准则工作台、页面、状态与 API；`BaseChart.vue`：通用图表生命周期。
- `frontend/src/modules/collection/workspace.ts` 独占任务、车系资产和评论查询状态；`catalogFlow.ts` 独占目录发现、轮询、搜索、跨页选择和任务创建；`api.ts` 统一 `/api/collection` 传输。平台层和研究模块不得导入这些内部状态。
- 平台层和自适应规划页不得导入多准则 `workspace.ts` 或 `api.ts`；多准则与采集 workspace 分别只能由各自模块壳创建一次。
- 依赖只能从外层流向领域/存储/适配边界；禁止让领域规则依赖 FastAPI、Vue 或页面组件。
- 文件大小不是拆分指标。按职责、生命周期和复用边界拆分，避免通用工具箱和只转发一行的包装层。

详细规则见 [开发与架构规范](docs/开发与架构规范.md)。修改前端结构时使用项目 Skill `$nev-mcdm-vue`；修改 FastAPI/Pydantic 时使用 `$fastapi`，但先核对本项目锁定版本。

## 变更流程

1. 先定位现有契约和测试；功能或缺陷变更先写能失败的测试，纯文档/机械格式变更除外。
2. 做满足需求的最小改动，不顺带扩展当前研究范围。
3. 按 [测试与质量门禁](docs/测试与质量门禁.md) 执行对应验证，并报告实际输出，不以“应该通过”代替证据。
4. 按 [文档同步规范](docs/文档同步规范.md) 检查文档影响；重大且可逆性低的架构决策写 ADR。
5. 明确要求安全审查时使用 `$security-best-practices`；明确要求威胁建模时使用 `$security-threat-model`。二者不替代一般代码审查。

## Git 约束

- `origin` 的规范地址是 `git@github.com:Hyise/NEV-agent-systems.git`，主分支为 `main`。
- 使用短生命周期主题分支和 `type(scope): summary` 原子提交；提交前执行受影响范围的质量门禁。
- 不提交运行数据库、研究数据归档、构建产物、依赖目录、凭据或本机临时文件。
- 不提交采集结果、JSONL 导出、Cookie、浏览器会话或 `output/playwright/` 截图。
- 日常验证不得启动完整 1000 车系发现后再采集全部评论；真实联网冒烟限制为少量目录记录和 1～3 个车系、每车系最多 2 页，并在验收记录中区分真实来源证据与受控数据库夹具。
- 不强推或改写共享 `main` 历史；合并、发布和版本标签遵循 [开发与架构规范](docs/开发与架构规范.md#10-git-版本管理)。

## 常用验证

从项目根目录执行：

```powershell
python -m pytest backend/tests -q
Set-Location frontend
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run build
```

本机也可用已验证解释器 `E:\anaconda927\envs\py311\python.exe` 替换 `python`。涉及界面交互时，还要在真实浏览器中验证受影响流程与窄屏布局。

Skill 的来源、触发边界和组合方式见 [Skill 使用清单](docs/Skill使用清单.md)。
