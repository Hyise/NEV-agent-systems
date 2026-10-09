# API与数据契约 · 阶段一

所有路径以 `/api` 开头，错误使用非2xx状态码，响应 `detail` 包含原因；422为格式或数据不合法，409为状态/版本冲突，404为不存在或不属于当前项目。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /health | 服务状态 |
| GET/POST | /projects | 列出/创建项目，mode为preset或custom |
| GET | /projects/{id}/overview | 统计、当前版本、来源、可用月份 |
| GET | /projects/{id}/schemas | 准则版本列表 |
| PUT | /projects/{id}/schemas/{sid} | 提交criteria与revision，更新草稿 |
| POST | /projects/{id}/schemas/{sid}/freeze | 提交revision，冻结版本 |
| POST | /projects/{id}/schemas/{sid}/fork | 从冻结版本派生草稿，数据不迁移 |
| GET | /projects/{id}/data | 月度记录，参数schema_id/month/search/page/page_size |
| POST | /projects/{id}/schemas/{sid}/datasets | name与csv_text，整体验证后保存 |
| GET | /projects/{id}/curves | kind=weights或rationality；自定义项目为空 |
| GET | /projects/{id}/predictions | month；返回历史条件份额估计 |
| GET | /projects/{id}/experiments | 原研究基线、消融记录 |
| GET | /projects/{id}/export | kind=dataset/report/template；支持schema_id |

准则保存示例：

```json
{
  "revision": 1,
  "criteria": [
    {"name": "续航体验", "labels": ["优秀", "良好", "一般", "较差"]}
  ]
}
```

加工CSV示例（仅解释格式，不是研究数据）：

```csv
产品型号,观察区间,时间压力,Real_Sales,续航体验
示例车型甲,2025-09,0.4,70,"{""L0"":0.4,""L1"":0.3,""L2"":0.2,""L3"":0.1}"
示例车型乙,2025-09,0.4,30,"{""L0"":0.3,""L1"":0.3,""L2"":0.3,""L3"":0.1}"
```

响应record：

```json
{
  "month": "2025-09",
  "model": "示例车型甲",
  "sales": 70,
  "pressure": 0.4,
  "probabilities": {"续航体验": [0.4, 0.3, 0.2, 0.1]},
  "share": 0.7
}
```

名称和标签数量限制见接口自动文档。概率和允许浮点误差1e-5，同月压力允许误差1e-6。导入上限10000行、前端文件上限8MB。CSV版本导出使用UTF-8 BOM。JSON快照包含准则、来源哈希、统计和历史结果，不声称是Word/PDF正式报告。

当前每一准则版本显示最近导入的数据集；数据库保留此前导入记录，历史数据集切换界面列入后续开发。第一版不提供删除API。

## 评论数据采集 API

评论采集路径统一以 `/api/collection` 开头。资源不存在返回 404，当前状态不允许操作或已有活动任务返回 409，输入范围不合法返回 422。本机任一时刻最多运行一个发现/采集任务。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/overview` | 车系数、评论数、异常数与活动任务 |
| GET | `/catalog` | 分页读取当前活动目录，支持 `query`、`page`、`page_size` |
| GET | `/catalog/selection` | 返回当前查询命中的全部车系 ID，供跨页全选 |
| GET | `/catalog/status` | 当前目录摘要与活动发现运行 |
| POST | `/catalog/discover` | 启动目标为 1000 个唯一车系的后台发现 |
| GET | `/catalog/discover/{run_id}` | 查询发现进度和终态错误摘要 |
| POST | `/catalog/discover/{run_id}/cancel` | 协作式取消指定发现运行 |
| GET/POST | `/jobs` | 分页查询任务；按选定车系创建并启动验证或正式任务 |
| GET | `/jobs/{id}` | 任务配置、游标、统计及事件 |
| POST | `/jobs/{id}/pause` | 协作式请求暂停 |
| POST | `/jobs/{id}/resume` | 从已提交页的断点继续 |
| POST | `/jobs/{id}/stop` | 停止任务并保留已保存数据 |
| GET | `/series` | 按名称或 `series_id` 分页查询车系 |
| GET | `/reviews` | 按 `series_id` 分页查询评论摘要 |
| GET | `/reviews/{id}` | 读取单条完整原始评论 |
| GET | `/export?series_id=...` | 按已存在车系导出 JSONL |

创建功能验证任务：

```json
{
  "mode": "verification",
  "selected_series_ids": ["5769", "8627"]
}
```

正式模式提交 `{"mode":"production","selected_series_ids":[...]}`。功能验证必须选择 1～3 个车系且每车系最多 2 页；正式采集必须选择 1～1000 个车系且每车系不限页数。ID 必须是唯一数字字符串并属于提交瞬间的活动目录。两种模式都使用服务端强制限速；任务与不可变车系快照在同一事务中创建，新任务的旧 `series_manifest` 字段固定为空。

目录发现先写入暂存批次，只有成功完成后才在同一事务中切换 `active_batch_id`；失败或取消会清理暂存数据并保留旧目录。`completed_short` 表示来源正常耗尽但不足 1000 个，不是错误。目录发现与评论采集共享进程级外部访问协调器，同一时刻只允许其中一个执行，浏览目录和读取历史数据不占用该预约。

创建任务时，目录不存在或外部访问正被占用返回 `409`；空选择、重复、数量越界或格式错误返回 `422`。如果选择已因目录刷新失效，返回对象形态错误：

```json
{
  "detail": {
    "message": "所选车系已不属于当前有效目录",
    "invalid_series_ids": ["8627"]
  }
}
```

`collection_job_series` 保存 `series_id`、名称、车系/口碑链接、目录批次、发现顺序和选择顺序的不可变快照。升级前没有快照行的历史任务仍可只读解析 `collection_jobs.series_manifest`，但新任务不得回退到任务内发现或写入该 JSON 字段。

评论列表不返回大型 `original_review`。采集时先保留汽车之家列表接口对象，再根据 `showId` 读取口碑详情页 HTML，以 `.space.kb-item` 中的完整正文补齐对应的 `contents[].content`；“最满意/最不满意”分别映射回原结构化名称“满意/不满意”，其他原始字段不拆分、不拼接、不改写。若列表正文已截断但详情页缺少对应分区，任务暂停且不提交该页。详情和 JSONL 中的每条记录包含 `platform`、`review_id`、`series_id`、采集时车系名称快照、可直接访问的口碑详情地址、内容哈希、采集时间和补齐后的完整 `original_review`。JSONL 媒体类型为 `application/x-ndjson; charset=utf-8`，每行是独立 JSON 对象；不生成拼接评论文本，也不把嵌套对象压平为 CSV。

车系唯一键为 `platform + series_id`；评论唯一键为 `platform + review_id`。来源存在 `Koubeiid` 或 `showId` 时直接使用；两者都缺失时，回退 ID 为 `sha256-{series_id}-{原始对象规范哈希}`，避免相同无 ID 对象在不同车系间碰撞。不同年款、改款和配置保留在原始对象字段中，但不形成独立车系任务。每页评论和下一页游标在同一事务提交；重复请求依靠唯一键幂等，同一评论 ID 内容变化会写入采集事件。

任务详情返回最近 100 条事件，并按发生时间正序展示；长任务的更早事件仍保留在 SQLite。分页终止以来源响应中已校验的 `pageindex`、`pagesize`、`pagecount` 和 `seriesid` 为准，不假设每页固定返回 20 条。
