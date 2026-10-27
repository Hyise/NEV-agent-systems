# 采集轮询与启动入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除采集任务轮询造成的页面闪烁，并统一生产启动端口为 8029。

**Architecture:** 采集工作区的定时轮询调用静默刷新路径，首次加载与用户动作仍走可见加载路径。启动器、PowerShell 默认参数、测试和文档共同固定 8029，避免入口之间漂移。

**Tech Stack:** Vue 3、TypeScript、Vitest、PowerShell、pytest

**Spec:** `docs/superpowers/specs/2026-10-27-collection-polling-launcher-design.md`

## Global Constraints

- 不新增依赖或修改后端接口。
- 不改变 2000ms 轮询周期和采集任务状态机。
- 生产启动默认端口统一为 8029。
- 保留当前分支所有既有功能和用户数据。

## Review Focus

- 首次加载仍必须显示忙碌状态，不能因静默轮询改动而失去加载反馈。
- 运行任务轮询期间不能切换全页忙碌状态，也不能停止后续轮询。
- 轮询失败后必须保留既有数据并允许后续用户操作恢复。
- CMD 与两个 PowerShell 脚本必须指向同一端口。
- 文档不能继续把 8018/8019 描述为生产默认端口。

---

### Task 1: 静默采集轮询

**Files:**
- Modify: `frontend/src/modules/collection/workspace.ts`
- Modify: `frontend/src/modules/collection/workspace.spec.ts`

**Interfaces:**
- Consumes: `loadWorkspace()`、`schedulePoll()` 和现有 `busy` ref。
- Produces: `loadWorkspace(options?: { silent?: boolean })`；定时轮询调用 `{ silent: true }`。

- [ ] **Step 1: Write the failing test**

新增测试：首次激活完成后推进定时器，挂起轮询响应，断言 `busy` 仍为 `false` 且旧概览仍存在；响应完成后数据更新并继续安排轮询。

- [ ] **Step 2: Run test to verify it fails**

Run: `npm.cmd test -- --run src/modules/collection/workspace.spec.ts`

Expected: FAIL，因为轮询期间当前实现将 `busy` 设为 `true`。

- [ ] **Step 3: Implement the minimal silent refresh path**

给 `loadWorkspace` 增加可选 `silent` 参数；只有非静默请求更新 `busy`，`schedulePoll` 使用静默模式。

- [ ] **Step 4: Run targeted test to verify it passes**

Run: `npm.cmd test -- --run src/modules/collection/workspace.spec.ts`

Expected: PASS。

### Task 2: 统一 8029 启动入口

**Files:**
- Modify: `启动观衡网站.cmd`
- Modify: `scripts/start-site.ps1`
- Modify: `scripts/start-local.ps1`
- Modify: `backend/tests/test_launch_scripts.py`
- Modify: `README.md`
- Modify: `docs/运行须知.md`

**Interfaces:**
- Consumes: CMD 到 `start-site.ps1`、`start-site.ps1` 到 `start-local.ps1` 的端口传递。
- Produces: 三个入口一致的生产默认端口 `8029`。

- [ ] **Step 1: Write the failing launcher contract test**

测试断言 CMD 显式包含 `-Port 8029`，两个 PowerShell 参数默认值均为 8029，生产运行文档不再声明 8018/8019 为默认地址。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_launch_scripts.py -q`

Expected: FAIL，因为当前两个 PowerShell 脚本默认 8018，CMD 未显式传端口。

- [ ] **Step 3: Update launchers and documentation**

将生产默认端口统一为 8029，并保持自定义 `-Port` 参数仍可覆盖默认值。

- [ ] **Step 4: Run launcher tests to verify they pass**

Run: `python -m pytest backend/tests/test_launch_scripts.py -q`

Expected: PASS。

### Task 3: 全量验证与分支交付

**Files:**
- Verify all modified and untracked files on `feat/raw-review-reader`

**Interfaces:**
- Consumes: Task 1、Task 2 以及当前分支已有未提交功能。
- Produces: 通过测试的功能分支提交，以及合并后的远端 `main`。

- [ ] **Step 1: Run frontend verification**

Run: frontend tests、typecheck、format check、design contract 和 production build。

- [ ] **Step 2: Run backend verification**

Run: 完整 `backend/tests` 测试套件。

- [ ] **Step 3: Review the complete diff and commit the feature branch**

确认无密钥、运行数据库、日志或其他临时文件进入提交；提交当前分支的全部产品代码、测试和文档。

- [ ] **Step 4: Merge and push**

在主工作区更新 `main`，合并 `feat/raw-review-reader`，重新核验提交图，然后推送 `origin/main`。
