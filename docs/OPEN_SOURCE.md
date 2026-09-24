# 开源组件与许可证

项目自身代码和内置的通用分类模板使用 [MIT License](../LICENSE)。用户导入的数据不包含在项目许可范围内。

本项目只编排成熟组件，不重造 OCR、公式引擎或 PDF 排版器。

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)：Apache-2.0；PP-StructureV3 能处理版面、文字、表格和公式并输出 Markdown/JSON。适合以后增加轻量本地适配器。
- [MinerU](https://github.com/opendatalab/MinerU)：面向复杂文档的结构化解析，支持图片/PDF、公式 LaTeX、Markdown/JSON、CLI 和 WebUI。模型和安装体积较大，因此作为可选后端。
- [pix2tex / LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR)：专门把公式截图转成 LaTeX；适合未来做“框选公式重识别”，不负责整页题目切分。
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)：Apache-2.0；本机已有中英文语言包，作为无需下载模型的保底识别器。
- [KaTeX](https://github.com/KaTeX/KaTeX)：MIT；本地离线渲染 LaTeX，用于网页与 PDF，避免公式依赖在线 CDN。
- [FastAPI](https://github.com/fastapi/fastapi)：MIT；提供本地筛选、编辑和上传接口。
- [jieba](https://github.com/fxsjy/jieba)：MIT；本地中文搜索模式分词，用于命令行线索检索。
- [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)：MIT；本地容错匹配，用于 OCR 拼写或字符偏差的候选排序。
- [WeasyPrint](https://github.com/Kozea/WeasyPrint)：BSD-3-Clause；把紧凑双栏 HTML 排版为 PDF。

检索方案评估：[SQLite FTS5](https://www.sqlite.org/fts5.html) 的 trigram 索引适合日后题量明显增大时加速中文片段查询；[sqlite-vec](https://github.com/asg017/sqlite-vec) 可在 SQLite 内存放向量，但还需要本地嵌入模型，当前不启用。现阶段题量下使用 jieba 和 RapidFuzz 对现有四库直接排序，避免多一份待同步索引和常驻模型。

选择原则：默认安装保持轻量；重型 OCR 通过适配器接入；识别结果统一进入同一 Pydantic schema；自动化结果必须可编辑和可追溯到原图。
