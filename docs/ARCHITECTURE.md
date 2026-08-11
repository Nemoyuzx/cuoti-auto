# 架构与模块职责

## 数据流

```text
图片 / 文件夹 / Codex 附件
        │
        ▼
识别适配器（Tesseract / OpenAI / MinerU / Codex JSON）
        │ 统一为 ExtractionBatch
        ▼
题目切分、科目与板块、答案、解析、置信度
        │ SHA-256 去重 + Pydantic 校验
        ▼
~/Desktop/<科目>/错题_auto/
  ├── wrong_questions.sqlite3
  ├── assets/
  ├── markdown/
  ├── exports/
  └── backups/
        │
        ├── FastAPI 聚合筛选 / 编辑复核
        └── KaTeX + WeasyPrint 双版本 PDF
```

## 模块

- `config.py`：科目、桌面目录、端口和模型配置；所有路径从这里派生。
- `models.py`：OCR/视觉模型与数据库之间唯一的结构化契约。
- `classification.py`：无模型时的透明关键词保底分类。低置信度一律待复核。
- `ingest.py`：图片发现、哈希、识别器适配和资源复制；不负责网页或 PDF。
- `db.py`：schema、四科数据库的 CRUD、联合查询与 Markdown 镜像。
- `app.py`：本地 FastAPI 路由。只绑定 `127.0.0.1`，不面向公网。
- `pdf_export.py`：批量 KaTeX 预渲染和 WeasyPrint 导出。
- `scripts/katex_batch.mjs`：复用官方 KaTeX 包把 LaTeX 转成可离线打印的 HTML+MathML。

## 为什么是四个数据库

用户要求每科在对应桌面目录独立建库。网页查询时依次读取四个小库后合并，因此既满足物理隔离，也保留统一筛选。数据库启用 WAL 和外键；`source_hash + question_text` 唯一约束用于阻止同一照片同一题重复入库。

## 可扩展点

新增 OCR 供应商时返回 `ExtractionBatch` 并加入 `ingest_path` 的适配器表即可。不要改变核心表来适配供应商。若以后增加复习算法，应写入 `attempts`，不要覆盖历史答案。
