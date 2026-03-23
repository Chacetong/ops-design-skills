---
name: ops-gen
description: 运营物料图片生成。调用 AI 绘图 API 生成 Banner 图片。可单独调用以调试生成效果。当用户说"生成图片"、"重新生成"或需要单独测试图片生成能力时触发。
---

# ops-gen — 图片生成

调用 AI 绘图 API 分步生成 Banner。每步生成后展示给用户确认，确认后**自动继续后续步骤**。

> 目录结构、版本管理、完整编排流程见 `ops-design/SKILL.md`。

## 输入

由 `ops-prompt` 生成的 prompt 组：
- **expand_prompt**（必须）：扩图 prompt
- **text_prompt**（text-only 步骤必须）：加文字 prompt
- **square_prompt**（竖版参考图时）：将竖版图重构为 1:1 的 prompt
- **base_prompt**（无参考图时必须）：底图生成 prompt
- **reference**（可选）：参考图片路径

## 执行

使用 `utils.create_task_dir()` 创建任务目录，所有路径使用绝对路径。`TASK_DIR` 为返回值。

### Step 2a：生成扩图（expand-only）

省略 `--text-prompt`，脚本自动进入 expand-only 模式，结果直接写入 `--output`。

**无参考图**（先生成底图再扩图）：

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<base_prompt>" \
  --expand-prompt "<expand_prompt>" \
  --output <TASK_DIR>/drafts/expanded.png \
  --save-base <TASK_DIR>/drafts/base.png \
  --request "<用户原始需求文字>"
```

**有参考图**（首次，含 squarify）：

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --expand-prompt "<expand_prompt>" \
  --output <TASK_DIR>/drafts/expanded.png \
  --reference <image.png> \
  --square-prompt "<square_prompt>" \
  --request "<用户原始需求文字>"
```

生成后展示 `expanded.png` 给用户确认。
- **确认** → 自动继续 Step 2b（加文字）
- **给出建议** → 融入建议重新生成 expand_prompt，基于**前一步的产物**重新扩图：

**重做扩图（使用前序资源，不回退到原始 reference）**：

```bash
# 竖版参考图场景：--reference 传 square.png（不传原始 reference）
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --expand-prompt "<新 expand_prompt>" \
  --output <TASK_DIR>/drafts/expanded_v2.png \
  --reference <TASK_DIR>/drafts/square.png

# 宽幅参考图场景：--reference 传 reference.png
python3 ... --reference <TASK_DIR>/drafts/reference.png

# 无参考图场景：--reference 传 base.png
python3 ... --reference <TASK_DIR>/drafts/base.png
```

### Step 2b：加文字（text-only）

`--save-intermediate` 指向当前活跃 expanded（取 `drafts/` 下编号最大的 `expanded*.png`），脚本检测到已存在后自动跳过扩图。

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --text-prompt "<text_prompt>" \
  --output <TASK_DIR>/drafts/with_text.png \
  --reference <TASK_DIR>/drafts/reference.png \
  --save-intermediate <ACTIVE_EXPANDED>
```

生成后展示 `with_text.png` 给用户确认。
- **确认** → 自动继续 Step 2c（生成终稿）
- **给出建议** → 融入建议重新生成 text_prompt，再生成新版本：

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --text-prompt "<新 text_prompt>" \
  --output <TASK_DIR>/drafts/with_text_v2.png \
  --reference <TASK_DIR>/drafts/reference.png \
  --save-intermediate <ACTIVE_EXPANDED>
```

### Step 2c：生成终稿

将当前 `with_text.png` 缩放到 1920x960：

```bash
python3 -c "
from PIL import Image
img = Image.open('<TASK_DIR>/drafts/with_text.png')
img = img.resize((1920, 960), Image.LANCZOS)
img.save('<TASK_DIR>/banner_<title>.png')
"
```

展示终稿给用户。用户可指定回退到任意步骤重新生成。

## 注意事项

- 文字由 AI 绘图模型直接渲染，质量可能不稳定，可多次重试
- 标题使用英文以提高渲染准确性
- 需确保 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 环境变量已配置
- 依赖 `google-genai` 和 `openai` Python 包
