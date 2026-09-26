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
