# notebooklm-slide-refiner

将 NotebookLM 导出的 PDF 幻灯片批量渲染为统一 16:9 PNG，并可通过 Gemini Nano Banana 进行图像优化，最后组装成 PPTX。项目以 Prefect 3.6.10 编排，支持并发、重试与断点续跑。

## 特性

- Prefect 3.6.10 Flow + Tasks，支持并发/重试/断点续跑
- PDF -> 统一 16:9 PNG（letterbox 处理，不裁切）
- Gemini Nano Banana 图像编辑可选（stub 模式默认可运行）
- 失败页 manifest 输出（JSONL）
- PPTX 输出：每页一张 PNG 全屏铺满

## 环境要求

- Python 3.10+
- Prefect == 3.6.10

## 安装

推荐使用 `uv` 或 `venv`：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

开发依赖：

```bash
pip install -e ".[dev]"
```

## 最小示例（强制验收命令）

1) 生成示例 PDF（3 页，含中文/表格/图形）：

```bash
python examples/generate_sample_pdf.py
```

> 该脚本会下载中文字体（约 17MB）。如下载失败，可先手动下载字体并设置 `SAMPLE_FONT_PATH=/path/to/font.ttf`。

2) **仅渲染 + PPTX（跳过 refine）**：

```bash
python -m notebooklm_slide_refiner --input ./examples/sample.pdf --out ./output --resolution 1920x1080 --skip-refine
```

期望输出：

- `./output/pages/raw/page_0001.png` ...
- `./output/deck.pptx`

3) **启用 Gemini Nano Banana refine**（需配置环境变量）：

```bash
export REFINER_MODE=gemini
export GEMINI_API_KEY=your_key
export GEMINI_MODEL=nano-banana
# 可选：export GEMINI_ENDPOINT=your_endpoint

python -m notebooklm_slide_refiner --input ./examples/sample.pdf --out ./output --resolution 3840x2160
```

期望输出：

- `./output/pages/enhanced/page_0001.png` ...
- `./output/deck.pptx`

> 默认 `REFINER_MODE=stub`，不会调用外部 API，直接复制 raw -> enhanced（用于验收标准 1）。
>
> CLI 会自动加载当前工作目录（向上查找）的 `.env`，环境变量优先级为「终端已设置」> `.env`。例如：
>
> ```bash
> # .env
> REFINER_MODE=gemini
> GEMINI_API_KEY=your_key
> GEMINI_MODEL=nano-banana
> # GEMINI_ENDPOINT=your_endpoint
> ```

## CLI 参数

```bash
python -m notebooklm_slide_refiner \
  --input ./examples/sample.pdf \
  --out ./output \
  --resolution 1920x1080 \
  --dpi 200 \
  --concurrency 5 \
  --rps 2 \
  --pages 1-3,5 \
  --skip-refine \
  --remove-corner-marks true \
  --keep-temp true
```

- `--input`：PDF 路径（必填）
- `--out`：输出目录（必填）
- `--resolution`：目标分辨率（默认 1920x1080）
- `--dpi`：渲染 DPI（可选）
- `--concurrency`：refine 并发数（默认 5）
- `--rps`：refine 请求速率上限（默认 2 次/秒）
- `--skip-refine`：跳过 refine，仅渲染 + PPTX
- `--pages`：页码过滤（如 `1-3,5,7-9`）
- `--remove-corner-marks`：是否移除角标（影响 prompt）
- `--keep-temp`：保留中间文件（默认 true）

## 断点续跑

- 若 `pages/raw/page_0005.png` 已存在，则跳过该页 render。
- 若 `pages/enhanced/page_0005.png` 已存在，则跳过该页 refine。

## 失败重试

- Gemini 调用对 429/5xx 进行指数退避重试（至少 5 次）。
- 失败页写入 `output/manifest.jsonl`，流程结束时输出失败清单。

## 输出 manifest

`output/manifest.jsonl` 为逐行 JSON，字段：

- `page_index`
- `raw_path`
- `enhanced_path`
- `status`
- `duration_ms`
- `error`

## Gemini Nano Banana 适配说明

`GeminiNanoBananaRefiner` 采用 HTTP 请求上传图片并传递 prompt。不同环境（Google AI Studio / Vertex AI）API 格式可能不同，需要根据具体端点调整：

- 环境变量：`GEMINI_API_KEY`（API Key 或 Vertex 访问令牌）、`GEMINI_ENDPOINT`（可选）、`GEMINI_MODEL`（默认 nano-banana）、`GEMINI_CREDENTIALS`/`GOOGLE_APPLICATION_CREDENTIALS`（Vertex JSON，可选）、`GEMINI_VERTEX_REGION`（自动生成 Vertex endpoint 时使用，默认 us-central1）
- 代码位置：`notebooklm_slide_refiner/refine.py`
- TODO：根据你的 endpoint 调整请求 URL/JSON 结构

Stub 模式默认可运行，不依赖外部 API。

### Vertex AI 使用说明（示例）

如果使用 Vertex AI 的 Gemini API，可提供 OAuth2 访问令牌或 JSON 凭据文件（服务帐号/ADC）。当提供 JSON 且未设置 `GEMINI_ENDPOINT` 时，会自动用 JSON 中的 project_id + `GEMINI_VERTEX_REGION`（默认 us-central1）生成 endpoint。以下示例展示两种常见方式（具体 endpoint 与鉴权方式可能因项目设置不同而变化）： 

```bash
# 方式 A：使用服务帐号/ADC JSON（自动生成 endpoint）
export REFINER_MODE=gemini
export GEMINI_MODEL=nano-banana
# 指向你的 JSON 凭据文件（二选一）
export GEMINI_CREDENTIALS=/path/to/vertex-credentials.json
# export GOOGLE_APPLICATION_CREDENTIALS=/path/to/vertex-credentials.json
# 可选：设置 Vertex 区域（不设默认 us-central1）
export GEMINI_VERTEX_REGION=REGION
```

```bash
# 方式 B：直接使用访问令牌
export REFINER_MODE=gemini
export GEMINI_MODEL=nano-banana
# 将 ENDPOINT 替换为你的 project/region
export GEMINI_ENDPOINT=https://REGION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/publishers/google
# 将 token 放在 GEMINI_API_KEY 中
export GEMINI_API_KEY=$(gcloud auth print-access-token)
```

> 注意：Vertex AI 使用 OAuth2 访问令牌而不是 API Key。`GEMINI_API_KEY` 在 Vertex 场景下会被当作 access token 使用。你仍可能需要在 `notebooklm_slide_refiner/refine.py` 中按 Vertex AI 的要求调整请求 URL 与 payload 结构。

## 架构概览

- Flow：`build_deck_flow`
- Tasks：`render_page_task`、`refine_page_task`、`assemble_ppt_task`
- 关键模块：
  - `render.py`：PDF 渲染 + letterbox
  - `refine.py`：refiner 抽象层与 Gemini 实现
  - `assemble.py`：PPTX 组装
  - `manifest.py`：manifest 写入

## License

MIT
