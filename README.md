# notebooklm-slide-refiner

将 NotebookLM 导出的 PDF 幻灯片批量渲染为统一 16:9 PNG，可选通过 Vertex AI（默认 `gemini-3-pro-image-preview`，可通过 `VERTEX_MODEL_NAME` 覆盖）进行图像编辑，并组装成 PPTX。内置 Prefect 3.6.10 编排，支持断点续跑、并发、重试与限流。

## 安装

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 快速开始（强制验收）

**A) 无 Vertex 调用的验收（100% 可运行）**

```bash
python examples/generate_sample_pdf.py
python -m notebooklm_slide_refiner --input ./examples/sample.pdf --out ./output --resolution 1920x1080 --skip-refine
```

期望输出：

- `./output/pages/raw/*.png`
- `./output/deck.pptx`

**B) Vertex 调用的验收（配置环境变量后可运行）**

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

python -m notebooklm_slide_refiner --input ./examples/sample.pdf --out ./output --resolution 3840x2160
```

期望输出：

- `./output/pages/enhanced/*.png`
- `./output/deck.pptx`

## Vertex 环境变量

- `GOOGLE_CLOUD_PROJECT`：可选。若未设置，将尝试从 `GOOGLE_APPLICATION_CREDENTIALS` 的 `project_id` 读取
- `GOOGLE_CLOUD_LOCATION`：默认 `global`
- `GOOGLE_APPLICATION_CREDENTIALS`：服务账号 JSON 路径，或使用 `gcloud auth application-default login`
- `VERTEX_MODEL_NAME`：可选，Vertex 模型名（默认 `gemini-3-pro-image-preview`）

## 常见问题

- **为什么 sample.pdf 中文显示为方块？**
  `examples/generate_sample_pdf.py` 会自动下载并使用 Noto Sans SC 字体（保存到 `examples/fonts/`）。若下载失败，可设置 `SAMPLE_FONT_PATH=/path/to/font.ttf` 指向本地字体，再重新生成 sample.pdf。
- **断点续跑如何工作？**
  若 `out/pages/raw/page_0001.png` 存在则跳过渲染；若 `out/pages/enhanced/page_0001.png` 存在则跳过 refine。
