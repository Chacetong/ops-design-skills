---
name: ops-gen
description: 运营物料图片生成。调用 AI 绘图 API 单图直出完整 Banner（含文字和视觉）。可单独调用以调试生成效果。当用户说"生成图片"、"重新生成"或需要单独测试图片生成能力时触发。
---

# ops-gen — 图片生成

调用 AI 绘图 API 单图直出完整 Banner，文字与视觉融为一体。

## 输入

用户需提供：
- **expand_prompt**（必须）：扩图 prompt
- **text_prompt**（必须）：加文字 prompt
- **base_prompt**（无参考图时必须）：底图生成 prompt（纯画面，无文字）
- **reference**（可选）：参考图片路径，提供时跳过底图生成

## 输出目录结构

每次任务创建独立目录，命名为 `YYMMDD-NN`（如 `260319-01`）。
**output/ 位于项目根目录**，`create_task_dir()` 返回绝对路径，所有脚本参数均使用绝对路径。

```
{project_root}/output/
  260319-01/
    banner_<title>.png              ← 终稿 v1（1920x960）
    banner_<title>_v2.png           ← 终稿 v2
    banner_<title>_v3.png           ← 终稿 v3
    drafts/
      request.txt                   ← 用户原始需求 + 追加的修改建议
      base.png                      ← 底图（无参考图时由 AI 生成）
      reference.png                 ← 用户参考图（有参考图时）
      expanded.png                  ← 扩图 v1（用户不满意时重做）
      expanded_v2.png               ← 扩图 v2（当前活跃扩图）
      with_text.png                 ← 加文字 v1（基于 expanded.png）
      with_text_v2.png              ← 加文字 v2（基于 expanded_v2.png）
      with_text_v3.png              ← 加文字 v3（文字迭代，仍基于 expanded_v2.png）
```

使用 `utils.create_task_dir()` 自动创建任务目录并递增序号。

## 执行

统一流程：获取底图 → 扩图至 2:1 → 加标题文字。区别仅在底图来源。

> **文字迭代自动检测**：调用脚本时传入 `--save-intermediate` 路径。若该文件已存在，脚本自动跳过 squarify 和 expand，直接用新 `text_prompt` 加文字。
> **重要**：传入的必须是**当前活跃的 expanded 版本**（即生成最新 with_text 所用的那张），而不是固定的 `expanded.png`。
> 例如：若用户对 `expanded.png` 不满意，重新生成了 `expanded_v2.png`，后续所有文字迭代都应基于 `expanded_v2.png`。

### 无参考图（AI 生成底图 + 扩图 + 加文字）

`TASK_DIR` 为 `create_task_dir()` 返回的绝对路径（如 `/path/to/project/output/260320-01`）：

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<base_prompt>" \
  --expand-prompt "<expand_prompt>" \
  --text-prompt "<text_prompt>" \
  --output <TASK_DIR>/drafts/with_text.png \
  --save-base <TASK_DIR>/drafts/base.png \
  --save-intermediate <TASK_DIR>/drafts/expanded.png \
  --request "<用户原始需求文字>"
```

### 有参考图（扩图 + 加文字）

```bash
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --expand-prompt "<expand_prompt>" \
  --text-prompt "<text_prompt>" \
  --output <TASK_DIR>/drafts/with_text.png \
  --reference <image.png> \
  --save-intermediate <TASK_DIR>/drafts/expanded.png \
  --request "<用户原始需求文字>"
```

### 文字迭代（当前活跃 expanded 已存在时自动触发）

执行前先确认**当前活跃的 expanded 版本**：检查 `drafts/` 下的 expanded 文件，取编号最大的那个（即用户最后接受的扩图结果）。

```
drafts/expanded.png       ← 若只有这个，用这个
drafts/expanded_v2.png    ← 若存在，优先用最新版
```

```bash
# ACTIVE_EXPANDED = 当前活跃的 expanded 路径（如 expanded_v2.png）
python3 .claude/skills/ops-design/scripts/generate_image.py \
  --prompt "<fallback>" \
  --text-prompt "<新 text_prompt>" \
  --output <TASK_DIR>/drafts/with_text_vN.png \
  --reference <TASK_DIR>/drafts/reference.png \
  --save-intermediate <ACTIVE_EXPANDED>
```

`<ACTIVE_EXPANDED>` 已存在 → 脚本自动跳过扩图，直接基于该版本加文字。

## 输出后处理

将 `with_text.png` 缩放到 1920x960 作为终稿：

```bash
python3 -c "
from PIL import Image
img = Image.open('<TASK_DIR>/drafts/with_text.png')
img = img.resize((1920, 960), Image.LANCZOS)
img.save('<TASK_DIR>/banner_<title>.png')
"
```

## 输出

- 展示终稿图片给用户确认效果
- 如不满意，用户可修改 prompt 后重新生成

### 迭代版本管理

迭代时不覆盖已有文件，创建带版本后缀的新文件：
- 首次：`with_text.png` → `banner_<title>.png`
- 第二次：`with_text_v2.png` → `banner_<title>_v2.png`
- 第三次：`with_text_v3.png` → `banner_<title>_v3.png`
- 仅重做文字：只产出 `with_text_vN` 和 `banner_vN`，不产出新 `expanded_vN`
- 重做扩图：产出新 `expanded_vN`，后续文字迭代均基于此新版本

**确定当前活跃 expanded 的规则**：取 `drafts/` 下编号最大的 `expanded*.png`，即为当前应使用的扩图基底。文字迭代时 `--save-intermediate` 必须指向该文件。

同时将用户的修改建议追加到 `drafts/request.txt`：
```
--- 修改建议 (YYYY-MM-DD HH:MM) ---
<用户修改建议原文>
```

## 注意事项

- 文字由 AI 绘图模型直接渲染，质量可能不稳定
- 如果文字渲染不理想，可多次重试（同一 prompt 每次结果不同）
- 标题使用英文以提高渲染准确性
- 需确保 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 环境变量已配置
- 依赖 `google-genai` 和 `openai` Python 包
