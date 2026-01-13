# notebooklm-slide-refiner

Turn NotebookLM-generated PDFs into presentation-ready slides — crisp Chinese text, consistent layout, zero manual tweaking.

⸻

✨ What This Project Does

NotebookLM can generate great content, but its exported slides often suffer from:
	•	Blurry Chinese text
	•	Inconsistent rendering across platforms
	•	Hard-to-edit layouts
	•	Page footers or visual artifacts not suitable for presentations

notebooklm-slide-refiner solves this by introducing a deterministic, automatable post-processing pipeline.

⸻

🧠 Core Idea

Instead of trying to “fix” PPT files directly, this project uses a more robust strategy:

PDF → High-resolution images → AI visual refinement → Clean PPT

This approach avoids font, encoding, and layout issues — especially for Chinese content.

⸻

🏗️ Pipeline Overview
	1.	Render
Convert each page of a NotebookLM-exported PDF into a fixed-aspect PNG (16:9, 1080p or 4K)
	2.	Refine
Use Gemini Nano Banana image editing to:
	•	Preserve original layout and colors
	•	Sharpen Chinese text
	•	Improve visual clarity
	•	Remove page footers or corner marks (optional, content-owner only)
	3.	Assemble
Rebuild a PowerPoint file with one refined image per slide
	4.	Orchestrate
Use Prefect for parallelism, retries, rate limiting, and resumability

⸻

🔧 Tech Stack
	•	Python 3.10+
	•	Prefect 2.x – workflow orchestration
	•	PyMuPDF – PDF rendering
	•	Pillow / OpenCV – image processing
	•	python-pptx – slide assembly
	•	Gemini API (Nano Banana) – image refinement
  
⸻

📁 Project Structure

```
notebooklm-slide-refiner/
├─ flows/
│  └─ notebooklm_pipeline.py
├─ tasks/
│  ├─ render_pdf.py
│  ├─ refine_image.py
│  └─ assemble_ppt.py
├─ lib/
│  ├─ layout.py
│  ├─ prompts.py
│  └─ manifest.py
├─ configs/
│  └─ default.yaml
└─ README.md
```

⸻

🚀 Quick Start

```bash
pip install -r requirements.txt
prefect server start
python flows/notebooklm_pipeline.py \
  --input notebooklm.pdf \
  --output slides.pptx
```

⸻

🖼️ Prompt Design Philosophy

Image refinement prompts are designed to be strictly layout-preserving:
	•	No reflow or re-layout
	•	No text rewriting
	•	No visual “creativity”
	•	Focus on clarity, sharpness, and fidelity

This makes the output suitable for investor decks, reports, and formal presentations.

⸻

⚠️ Notes on Content Ownership

This project assumes you own or have the right to modify the content you process.

If a PDF contains platform-imposed watermarks or copyright indicators, ensure that your usage complies with the source platform’s terms.

⸻

🛣️ Roadmap
	•	Page-type detection (title / table / dense text)
	•	Multi-language optimization presets
	•	Optional OCR → editable PPT mode
	•	Web UI (Prefect + simple frontend)

⸻

🤝 Contributing

PRs and issues are welcome.
This project favors clarity, determinism, and reproducibility over “magic”.

⸻

📜 License

MIT
