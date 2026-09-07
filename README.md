# 错题_auto

把纸质错题照片变成可复核、可检索、可重做和可打印的本地错题库。

系统面向数学、英语、408、政治四科：每科数据分别保存在本机桌面的 `错题_auto` 目录，网页只在本机聚合查询。识别结果会保留来源图片并默认标记为“待复核”，适合把自动 OCR 与人工校对结合起来。

> [!IMPORTANT]
> 本项目没有账号与权限系统，默认只监听 `127.0.0.1`。不要把服务直接绑定到公网地址；错题照片、数据库、导出文件和 API Key 也不要提交到 Git。

## 功能

- Tesseract 离线 OCR、OpenAI 视觉模型和 MinerU 可选适配器
- 同一照片与题干联合去重，Pydantic 校验后写入 SQLite
- 四科独立数据库与 Markdown 镜像
- 原图对照复核、分类建议、公式与代码块渲染
- 后台生成纯题重做版和完整错题本版 PDF
- 原始照片与校正后的展示副本分离保存

## 运行要求

目前主要在 macOS 与 Python 3.12 上验证。核心 Python 服务支持 Python 3.11–3.13；其他系统可以使用命令行启动，但桌面快捷方式、中文字体和 Tesseract 安装方式可能不同。

安装前请准备：

- [uv](https://docs.astral.sh/uv/)
- Node.js 与 npm（用于离线 KaTeX 渲染）
- Tesseract，建议安装 `chi_sim` 和 `eng` 语言包

## 快速开始

```bash
git clone https://github.com/Nemoyuzx/cuoti-auto.git
cd cuoti-auto
./scripts/setup.sh
```

安装脚本会创建 `.venv`、安装 Python 与 npm 依赖、初始化四科数据库，并在 macOS 桌面创建“打开错题本.command”快捷方式。macOS 上同时会安装用户级 LaunchAgent：登录后自动启动服务并打开一次浏览器，服务异常退出后会自动拉起。也可以手动管理：

```bash
.venv/bin/cuoti doctor
.venv/bin/cuoti service status
.venv/bin/cuoti service install
.venv/bin/cuoti service uninstall
```

浏览器会打开 <http://127.0.0.1:8765>。

默认数据目录如下：

```text
~/Desktop/<数学|英语|408|政治>/错题_auto/
├── wrong_questions.sqlite3
├── assets/
├── markdown/
├── exports/
└── backups/
```

## 配合 Codex 使用（推荐）

这是一个适合配合 Codex 使用的高效错题整理工具。仓库内置了 [`AGENTS.md`](AGENTS.md)，其中定义了照片筛选、多题拆分、公式 LaTeX、答案与解析补全、分类、JSON 校验、入库和复核规则。

1. Clone 本项目并按上面的“快速开始”完成首次安装。
2. 在 Codex 中把 `cuoti-auto` 文件夹打开或导入为一个项目。
3. 把待整理的照片文件夹复制到项目的 `data/inbox/` 目录；该目录中的照片默认不会被 Git 提交。
4. 在 Codex 中直接说：

   > 按 `AGENTS.md` 处理 `data/inbox/照片文件夹` 中的错题照片，拆题、生成解析、导入数据库并复核。

之后只需把新的照片文件夹放进 `data/inbox/` 并交给 Codex。Codex 会按项目协议逐张理解图片、拆分同页多题、整理为 LaTeX 和结构化 JSON、调用项目命令入库，并检查 Markdown 同步结果。自动识别和生成的内容默认仍需人工复核。

## 导入错题

### 网页上传

启动服务后，在页面底部上传图片并选择识别器。Tesseract 适合清晰印刷文字；复杂公式、手写和多栏版面仍需人工复核。

### 命令行

```bash
.venv/bin/cuoti ingest "/绝对路径/错题照片文件夹" --provider tesseract

# 仅在当前 shell 中设置 Key，不要写进项目文件
export OPENAI_API_KEY="你的 API Key"
.venv/bin/cuoti ingest "/绝对路径/错题照片文件夹" --provider openai
```

### 结构化 JSON

按 [`docs/extraction-example.json`](docs/extraction-example.json) 的格式准备数据后导入：

```bash
.venv/bin/cuoti import-json tmp/codex_batch.json --source "/绝对路径/原图.jpg"
```

## PDF 导出

网页顶部“PDF 导出”浮窗会在后台创建任务并显示进度。也可以使用命令行：

```bash
.venv/bin/cuoti export --variant practice --subject 数学
.venv/bin/cuoti export --variant notebook --subject 408 --section 操作系统
```

- 纯题重做版不显示答案，只会使用人工勾选的不含答案或批注的题图。
- 完整错题本版包含答案、解析、错因和知识点，不包含原始拍照页。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `CUOTI_DESKTOP` | `~/Desktop` | 四科数据根目录 |
| `CUOTI_HOST` | `127.0.0.1` | Web 监听地址 |
| `CUOTI_PORT` | `8765` | Web 端口 |
| `CUOTI_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 识别模型 |
| `OPENAI_API_KEY` | 未设置 | 启用 OpenAI 识别器 |

## 开发

```bash
uv sync --locked --extra dev
npm ci
.venv/bin/pytest
uv build --out-dir tmp/dist
```

提交改动前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。架构边界见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，运维与故障排查见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)，第三方组件说明见 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md)。

## 数据与隐私

`.gitignore` 默认排除虚拟环境、模型运行产物、上传副本、错题照片、SQLite、导出 PDF 和临时 OCR 文件。首次提交或分享补丁前仍建议运行密钥扫描，并人工检查暂存文件列表。

OCR 与视觉模型可能识别错误；自动生成的答案和解析不能替代人工核对。

## 许可证

项目代码与自带的通用分类模板采用 [MIT License](LICENSE)。用户自行导入的错题、照片、教材目录和模型输出不因使用本项目而改变其原有权利归属。
