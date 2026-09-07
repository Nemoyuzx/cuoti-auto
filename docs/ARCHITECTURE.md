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

## 选项标签不变量

`questions.options_json` 只保存选项正文，不保存 `A.`、`B.` 等序号。导入、复核保存和数据库更新通过 `normalize_options` 去除与当前位置相符的历史前缀；网页、实时预览、Markdown 和 PDF 在渲染时通过 `option_label` 统一补回标签。空字符串会作为缺失选项的占位保留，渲染时隐藏但不改变后续字母；人工编辑中的普通空行则由 `parse_options_text` 忽略。这样可避免 `A. A. ...` 重复、选项错位，并保证所有出口编号一致。

`questions.correct_answer` 中位于字段开头的选择题字母只保存裸标签，例如 `C` 或 `C $O(n)$`，不保存 `(C)`、`（C）`。导入模型和数据库更新统一通过 `normalize_correct_answer` 清理开头标签；规则锚定字段开头，因此不会改动公式或正文内部的括号。

## 复核图片角色

`images.image_role` 区分 `question`（题目）、`work`（学生作答/订正）、`solution`（答案/标准解析）和待细分的 `supplement`。复核页将题目与作答照片放在前组、答案解析照片放在后组并提供快捷跳转；答案解析图永远不进入纯题 PDF 的可选图片列表。新增附图必须通过 `SubjectStore.add_image` 明确写入角色。

`analysis` 的内容来源遵循严格优先级：已关联的标准解析页 > 无标准解析时的补充解析。有标准解析页时只做忠实转写，不允许用人工摘要或模型自解替换书中的方法。无法确定页面对应或公式时，保留解析图并降为低置信度待复核，不得生成看似已核对的文字。

## 行间公式间距不变量

结构化富文本字段和选项在 Pydantic 导入、数据库更新及网页/PDF 渲染入口统一经过 `normalize_rich_text_spacing`。独立公式 `$$...$$` 与前后正文之间只保留一个换行，不能出现空白行；连续独立公式同样紧邻。Markdown 代码围栏内部不执行该规则，避免改变示例程序的原始格式。历史数据迁移脚本位于 `tmp/normalize_display_math_spacing.py`。

## 错因证据不变量

`questions.error_reason` 只记录能从学生解答过程确认的具体错误。题号圈选、红笔订正、未作答和标准解析只能决定收录或辅助讲解，不能据此推断错因；没有作答过程时字段保持空字符串。识别模型、结构化导入和复核保存通过 `normalize_error_reason` 清除已知的泛化占位话术，复核输入框保持为空。“再做一次”是用户指定的黑笔圈题复习标记，不属于待核对占位话术，予以保留。

## 错误答案不变量

`questions.wrong_answer` 只保存学生最终写出的具体答案，不保存“待确认（见原图红笔答案或订正）”“思路错误”等状态性占位话术，也不保存作答过程描述。识别到答题区为空白、只有思路未形成最终答案，或只有红笔答案/订正而无法确认学生原答案时统一存为“不会”；能看清具体原错误答案时仍忠实保存。作答过程错误写入 `error_reason`。结构化导入和复核保存统一通过 `normalize_wrong_answer` 执行基础规则。

## 可扩展点

新增 OCR 供应商时返回 `ExtractionBatch` 并加入 `ingest_path` 的适配器表即可。不要改变核心表来适配供应商。若以后增加复习算法，应写入 `attempts`，不要覆盖历史答案。
