# 日常操作与故障排查

## 启动与健康检查

```bash
cd /path/to/cuoti-auto
.venv/bin/cuoti doctor
.venv/bin/cuoti serve
```

如果端口被占用，可临时使用 `CUOTI_PORT=8877 .venv/bin/cuoti serve`。

### macOS 登录自启与常驻

```bash
.venv/bin/cuoti service install
.venv/bin/cuoti service status
.venv/bin/cuoti service uninstall
```

`install` 会在 `~/Library/LaunchAgents/` 安装两个用户级任务：`com.nemoyu.cuoti-auto` 常驻检查 Web 服务并在异常退出后自动拉起；`com.nemoyu.cuoti-auto.open` 每次登录只等待服务就绪并打开一次浏览器。由于 macOS 会禁止 launchd 直接读取桌面下的项目和数据库，监视器在需要时会通过 Terminal 的桌面访问权限启动后台 supervisor，无需给 Python 开启“完全磁盘访问”。日志保存在 `output/logs/`，重启服务不会反复弹出新标签页。

## 对比复核

- 首页点“开始对比复核”，左侧查看原始照片，右侧直接修改题干、选项、答案、解析和分类。
- 点“仅保存”会继续停留在当前题；点“确认无误”会将状态改为“已复核”并进入下一题。
- 误收题可点“删除本题”并二次确认。记录会从 SQLite、Markdown 和后续 PDF 中移除；删除前的 JSON 与派生图片会移到本科 `错题_auto/backups/`，原始照片不受影响。
- 展示副本在入库时会先应用 EXIF 方向，再用 Tesseract OSD 检测文字方向。原始照片不会被改动；复核页的左右旋转按钮是人工兜底。

## 科目分页与 PDF 导出

- 四科使用独立页面：`/subject/math`、`/subject/english`、`/subject/cs408`、`/subject/politics`。科目通过顶部页签切换，筛选表单不再包含科目下拉框。图片上传统一使用独立的 `/import` 页面，科目页不内嵌上传表单；导入完成后停留在导入页并提供对应科目与复核入口。
- 题库卡片、待复核队列和 PDF 导出共用统一顺序：科目 → 章节 → 小节/板块 → 题号。数字按自然数比较，因此第 2 章排在第 10 章之前；`待确认`内容放在末尾。
- 题库桌面端固定每行两题，选项横向排列且不叠加浏览器自动序号。点击题目后先显示题干、答案和解析，原图与编辑表单默认折叠在页底。
- 题号在网页、复核、Markdown 和 PDF 中同时显示建档日期。Markdown 三反引号代码块会在网页和 PDF 中渲染为独立代码区域；解答、应用、计算、证明等长题在 PDF 中独占一列。
- PDF 由单线程后台队列生成，不占用页面请求。顶部导航栏的“PDF 导出”浮窗轮询 `/api/exports/{job_id}`，用圆环显示进度、完成后显示对勾并提供下载。
- 公式密集的大批次会每 24 题启动一个独立 WeasyPrint 子进程，串行渲染后合并为一个 PDF；子进程结束即释放内存，避免数百道公式题使 Web 服务常驻数 GB 排版缓存。
- 完整错题本版只输出结构化题目、错误答案、正确答案、解析、错因和知识点，不带原始拍照页；纯题版只会带复核页中人工勾选的无答案题图。
- 任务记录保存在当前服务进程内，服务重启后旧任务进度会失效，但已生成的 PDF 仍保留在 `output/pdf/`。

## 408 数据结构目录分类

- 通用分类模板保存在 `src/cuoti/data/408_data_structure_taxonomy.json`，不对应特定教材或年份，可按自己的课程体系修改。
- 复核页的“章节”“知识板块”“知识点”输入框会读取该模板并提供名称建议，仍允许人工输入，避免模板无法覆盖新题型时被锁死。
- 历史标签归一化先预览，再确认写入：

  ```bash
  .venv/bin/python scripts/normalize_408_taxonomy.py
  .venv/bin/python scripts/normalize_408_taxonomy.py --apply
  ```

## 政治目录分类

- 通用分类模板保存在 `src/cuoti/data/politics_taxonomy.json`，覆盖标准板块但不包含特定教材页码或目录转录内容。
- 政治复核页将“知识板块”映射为模块，“章节”映射为主题，“知识点”提供“模块 / 分组 / 主题”完整路径。

## 推荐照片拍摄方式

- 镜头尽量与纸面平行，四角完整，避免手和阴影压住文字。
- 一页 1-3 题最利于题目切分；连续过程要按页码顺序命名。
- 批改符号、错误答案和正确答案都要入镜。反光严重或焦外的照片先重拍。
- 入库时同时查找订正痕迹和题号圈选：题号被圈出的题一律收录，与其是否能看清原错答无关。
- 答案位置为空但有明确对钩，且题号未圈、没有红笔订正或其他错误标记时，按“已经掌握”排除；空白本身不能作为错题证据。
- 自动结果进入“待复核”；详情页复核后改为“已复核”。
- 原始照片可能含答案，默认不进入纯题 PDF。几何图、材料图等无答案插图可在详情页勾选“纯题 PDF 图片”。

## 识别器选择

- `tesseract`：已经安装即可离线使用。适合清晰印刷文字；公式、手写、题目切分需要人工修订。
- `openai`：设置 `OPENAI_API_KEY` 后使用。一次生成结构化题目、分类和解析，仍需复核原图。
- `mineru`：复杂讲义或多栏版面优先。安装方法见 `OPEN_SOURCE.md`。
- Codex 附件：把图片直接发到项目对话，按根目录 `AGENTS.md` 执行，适合少量高质量整理。

## 备份

停止写入后复制四个 `wrong_questions.sqlite3` 以及 `assets/`、`markdown/` 即可完整恢复。WAL 模式运行中备份时优先用 SQLite 在线备份 API，不要只复制主库而漏掉 `-wal`。

## 本地批次记录与隐私边界

- 批次 JSON、图片映射、审计结果和一次性修复脚本只保存在被 Git 忽略的 `tmp/` 中；题目照片、数据库、Markdown、备份和导出文件只保存在各科本地 `错题_auto` 或运行时目录中。
- 写入前使用 SQLite 在线备份。解析照片的 `image_role` 是 `solution`，不会进入纯题 PDF。
- 挂接 `solution` 图片不等于文字解析已核对。批量导入时必须逐题按标准解析页忠实转写 `analysis`；若页面缺失、对应不确定或公式无法辨认，应留空、降低置信度并交由人工复核，禁止改用自写摘要。
- GitHub 只同步通用程序、通用文档与测试。不得提交或推送批次日期、原始文件名、题号清单、记录 ID、题目/答案映射、个人路径、照片、数据库、Markdown 镜像或导出文件。

## 常见问题

- 网页公式还是 `$...$`：运行 `npm install`，确认 `/vendor/katex/katex.min.js` 能访问。
- PDF 提示缺少 KaTeX：运行 `./scripts/setup.sh`。
- 中文 PDF 出现方框：确认 macOS 的 `Songti SC` 或 `SimSun` 字体存在。
- Tesseract 失败：运行 `tesseract --list-langs`，确认有 `chi_sim` 和 `eng`。
- OpenAI 导入失败：检查 `OPENAI_API_KEY` 和 `CUOTI_OPENAI_MODEL`，不要把 Key 写入项目文件。
- 同一题没有新建：这是哈希去重生效；请编辑已有记录，而不是重新导入。
