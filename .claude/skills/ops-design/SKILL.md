---
name: ops-design
description: 运营物料自动化设计与图片生成。当用户需要制作 Banner 运营图片时触发。通过 AI 绘图单图直出完整 Banner（文字与视觉融为一体）。当用户提到"做一个Banner"、"制作海报"、"运营图"、"活动图片"、"物料设计"或任何涉及运营视觉内容生产的需求时，使用此技能。
---

# ops-design — 运营图片自动化创作（编排入口）

将模糊的运营需求转化为高质量 Banner 图片。单图直出，文字与视觉融为一体。

> **单步调试**：每个子 Skill 均可独立调用，用于调试或验证单个环节的效果。

## 全流程编排

```
用户需求
  │
  ▼
ops-brief（需求理解 + 创意概念）
  │
  ▼
ops-prompt（生成绘图 prompt）
  │  无参考图 → base_prompt + expand_prompt + text_prompt
  │  有参考图 → expand_prompt + text_prompt

  ▼
{project_root}/output/YYMMDD-NN/banner_<title>.png（缩放至 1920x960）
```
  │
  ▼
ops-gen（生成图片）
  │  无参考图 → 生成底图 → 扩图 → 加文字
  │  有参考图 → 扩图 → 加文字
  │
### Step 1：需求理解 + 创意概念 → `/ops-brief`

- 输入：用户自然语言描述 + 可选图片
- 输出：结构化 brief JSON（含 `creative_concept`）
- 此步骤会处理：标题翻译、图片用途判断、产出统一创意概念
- **注意**：参考图只需下载到 `/tmp/`，**不要**额外转存到 drafts/；`generate_image.py` 会自动复制，避免重复文件

### Step 2：生成绘图 Prompt → `/ops-prompt`

- 输入：Step 1 的 brief JSON
- 输出：绘图 prompt 组（expand_prompt + text_prompt，无参考图时额外输出 base_prompt）
- 此步骤会读取设计规范和构图参考案例
- **无需用户确认，直接进入 Step 3**

### Step 3：生成图片 → `/ops-gen`

- 输入：Step 2 的 prompt 组 + 可选参考图
- 输出：`output/banner_<title>.png`（1920x960）
- 统一流程：获取底图 → 扩图至 2:1 → 加标题文字

## 调整与迭代

如果用户对结果不满意：
- **调整创意方向**：重新调用 `/ops-brief`
- **调整 prompt**：重新调用 `/ops-prompt`
- **重新生成**：重新调用 `/ops-gen`（同一 prompt 每次结果不同）
- **文字不理想**：调用 `ops-prompt` 生成新 `text_prompt`，脚本检测到 `expanded.png` 已存在后自动跳过 squarify 和 expand，直接加文字

### 迭代过程管理

1. **记录修改建议**：用户在过程中给出的修改建议，追加写入 `drafts/request.txt`，格式为：
   ```
   --- 修改建议 (YYYY-MM-DD HH:MM) ---
   <用户的修改建议原文>
   ```

2. **文件版本管理**：迭代重新生成时，不覆盖已有文件，创建新版本文件：
   - 首次：`with_text.png`、`expanded.png`、`banner_<title>.png`
   - 第二次：`with_text_v2.png`、`expanded_v2.png`、`banner_<title>_v2.png`
   - 以此类推……
   - **仅重做文字时**：只产出 `with_text_vN.png` 和 `banner_<title>_vN.png`，不产出新 `expanded_vN.png`
   - **文字迭代基底**：始终使用 `drafts/` 下编号最大的 `expanded*.png`（即当前活跃扩图），而非固定使用 `expanded.png`

## 共享资源

设计规范（供 `ops-prompt` 读取）：
- `references/style-guide.md` — 品牌色板、字体风格、视觉调性
- `references/specs/banner.md` — Banner 规格、构图规范
- `references/examples/` — 构图参考案例（仅供理解，不参与生成）

脚本（供 `ops-gen` 调用）：
- `scripts/generate_image.py` — AI 绘图 API 调用（双后端：OpenAI + Gemini）
- `scripts/utils.py` — 共享工具函数

### 后端模型

| 步骤 | SDK | 模型 | 说明 |
|------|-----|------|------|
| 生成底图（无参考图时） | OpenAI SDK | `gpt-image-1.5` | 4:3 纯画面 |
| 扩图至 2:1 | Google GenAI SDK | `gemini-3.1-flash-image-preview` | 底图/参考图 → 宽幅 |
| 加标题文字 | Google GenAI SDK | `gemini-3.1-flash-image-preview` | 扩图 → 终稿 |

## 输出规范

每次任务在 `output/` 下创建独立子目录，命名为 `YYMMDD-NN`（日期+当日序号）：

```
output/
  260319-01/
    banner_<title>.png              ← 终稿 v1（1920x960）
    banner_<title>_v2.png           ← 终稿 v2（迭代后）
    drafts/
      request.txt                   ← 用户原始需求 + 追加的修改建议
      base.png                      ← 底图（无参考图时由 AI 生成）
      reference.png/webp            ← 用户参考图（有参考图时）
      square.png                    ← 1:1 正方形中间图（竖版参考图时自动生成）
      expanded.png                  ← 扩图 v1
      expanded_v2.png               ← 扩图 v2（迭代后，若该步骤重做）
      with_text.png                 ← 加文字 v1
      with_text_v2.png              ← 加文字 v2（迭代后）
  260319-02/
    ...
```

使用 `scripts/utils.py` 中的 `create_task_dir()` 自动创建目录并递增序号。
