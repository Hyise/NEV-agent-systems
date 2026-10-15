# 研究仪器型 UI 验收记录

验收日期：2026-10-15  
验收分支：`feat/raw-review-reader`  
验收站点：`http://127.0.0.1:8030/`

## 1. 本次范围

本次重构覆盖研究平台首页、评论数据采集工作台、多准则决策工作台和自适应评估规划页。页面采用“研究仪器型工作台”视觉方向：宋体用于品牌与研究标题，微软雅黑/PingFang 用于控制、正文、表格和图表；保留现有接口、路由、数据口径和工作区状态所有权，不修改采集、准则提取或模型计算逻辑。

评论数据流程固定为“获取数据 → 管理数据 → 用于研究”，并在步骤条中显示车系数量、原始评论数量和研究范围确认状态。研究交接页明确说明不会自动创建任务或调用大模型。

## 2. 自动化校验

| 检查 | 实际结果 |
| --- | --- |
| Emil Design Engineering Skill 校验 | 使用 Python UTF-8 模式运行 `quick_validate.py`，输出 `Skill is valid!` |
| 后端回归测试 | Python 3.11 环境下 274 项测试全部通过 |
| 前端单元测试 | 9 个测试文件、59 项测试全部通过 |
| 设计契约 | `Design contract passed.` |
| Prettier | 所有匹配文件符合格式 |
| Vue / TypeScript | `vue-tsc --noEmit` 通过 |
| 生产构建 | Vite 构建成功，2212 个模块完成转换 |
| 差异检查 | `git diff --check` 无输出 |

构建产生一项非阻塞警告：ECharts 所在的 `BaseChart` 分块压缩后约 530.82 kB，超过 Vite 默认 500 kB 提示线。该警告不影响运行，后续可单独评估图表模块拆分；本次不为了消除提示改变加载边界。

Windows 默认编码会使校验器以 GBK 读取 UTF-8 标点并报错，因此 Skill 校验使用 `python -X utf8`。这是校验器运行环境差异，Skill 文件本身未改写。后端使用项目启动脚本规定的 Python 3.11 环境；Python 3.9 不支持项目采用的 `StrEnum` 和 `dataclass(slots=...)`，不能用于本项目测试。

## 3. 真实浏览器验收

使用 Chromium/Playwright 对四个路由分别检查 1440×900、1024×768 和 390×844，共 12 个页面状态：

| 路由 | 桌面 | 平板 | 移动端 | 页面级横向溢出 |
| --- | --- | --- | --- | --- |
| `/` | 正常 | 正常 | 正常 | 无 |
| `/collection` | 正常 | 正常 | 正常 | 无 |
| `/mcdm` | 正常 | 正常 | 正常 | 无 |
| `/adaptive` | 正常 | 正常 | 正常 | 无 |

交互检查结果：

- “新建评论采集任务”弹窗可打开、关闭，关闭后焦点回到触发按钮。
- 原始评论抽屉可打开、关闭，关闭后焦点回到“查看原文”按钮。实测首条资产展示 5 个结构化评论段落，抽屉可读取文本约 1210 字，未使用表格摘要中的截断文本替代原文。
- “建立分析项目”弹窗可打开、关闭，关闭后焦点回到“新建研究”按钮。
- 移动导航可打开，并可通过侧栏外遮罩关闭；关闭后焦点回到菜单按钮。
- `prefers-reduced-motion: reduce` 下按钮的动画和过渡时长均降为 `0.00001s`。
- 200% 页面缩放检查结果为 `scrollWidth === clientWidth`，无页面级横向溢出。
- 干净验收会话控制台为 0 error、0 warning。

首次在旧的 8029 进程中检查自适应页时，浏览器缓存仍引用上一次构建的动态分块文件并出现 404。重新启动干净的 8030 生产进程后，四个路由与全部尺寸均复验通过。这说明生产构建更新后应重启旧服务进程，不能只刷新已加载旧资源映射的浏览器标签页。

## 4. 截图证据

截图位于工作树的 `output/playwright/`，命名规则为 `{desktop|tablet|mobile}-{home|collection|mcdm|adaptive}.png`。主要文件：

- `output/playwright/desktop-home.png`
- `output/playwright/desktop-collection.png`
- `output/playwright/desktop-mcdm.png`
- `output/playwright/desktop-adaptive.png`
- `output/playwright/tablet-home.png`
- `output/playwright/tablet-collection.png`
- `output/playwright/tablet-mcdm.png`
- `output/playwright/tablet-adaptive.png`
- `output/playwright/mobile-home.png`
- `output/playwright/mobile-collection.png`
- `output/playwright/mobile-mcdm.png`
- `output/playwright/mobile-adaptive.png`

`output/` 为本地验收产物目录，不作为应用运行依赖。

## 5. 已确认边界

- 未新增前端运行依赖。
- 未修改后端接口、数据库模型和原始评论数据。
- 未改变采集任务、评论资产、准则版本或 DeepSeek 调用的业务语义。
- 自适应评估系统仍为规划页，不提供模拟结果或虚构数据。
- 动效只用于按钮反馈、移动导航和评论抽屉，且遵循减少动效偏好。
