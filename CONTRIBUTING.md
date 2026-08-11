# 贡献指南

感谢你愿意改进错题_auto。提交代码前，请先搜索已有 Issue；较大的行为变更建议先开 Issue 说明使用场景、预期结果与兼容性影响。

## 本地开发

```bash
git clone https://github.com/Nemoyuzx/cuoti-auto.git
cd cuoti-auto
uv sync --locked --extra dev
npm ci
.venv/bin/cuoti doctor
.venv/bin/pytest
```

修改界面时还应启动真实服务并在浏览器中检查相关流程。修改 PDF 后需要导出纯题版与完整错题本版，再转为图片检查中文、公式、分页和留白。

## 架构约束

- SQLite schema 只在 `src/cuoti/db.py` 维护，四科数据库结构保持一致。
- OCR/视觉后端只在 `src/cuoti/ingest.py` 增加适配器，不把供应商字段写进核心表。
- 四科继续使用 `/subject/{slug}` 独立页面。
- PDF 通过 `export_jobs.py` 的单线程后台队列生成，网页只轮询进度。
- 删除题目时保留原始照片，并按现有备份流程处理结构化数据和派生资源。
- 同时修改模板和路由上下文时，为可选变量在两侧提供默认值。

更多设计背景见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，完整维护协议见 [`AGENTS.md`](AGENTS.md)。

## 测试与提交

每次改动至少运行：

```bash
.venv/bin/pytest
```

请让提交保持单一目的，并在 Pull Request 中写清：

- 解决的问题和采用的方案
- 用户可见行为或数据兼容性变化
- 已运行的测试与人工验证
- 界面改动前后的截图（如适用）

## 测试数据与隐私

不要提交真实学生照片、姓名、数据库、模型输出、API Key 或带批注的试卷。测试与文档示例必须使用自行编写或明确允许再分发的内容，并移除文件元数据中的个人信息。

安全问题不要公开提交 Issue，请按 [`SECURITY.md`](SECURITY.md) 私下报告。
