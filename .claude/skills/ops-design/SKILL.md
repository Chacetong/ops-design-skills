---
name: ops-design
description: 运营物料自动化设计与图片生成。当用户需要制作 Banner 运营图片时触发。通过 AI 绘图单图直出完整 Banner（文字与视觉融为一体）。当用户提到"做一个Banner"、"制作海报"、"运营图"、"活动图片"、"物料设计"或任何涉及运营视觉内容生产的需求时，使用此技能。
---

# ops-design — 运营图片自动化创作（编排入口）

将模糊的运营需求转化为高质量 Banner 图片。**每一步都需要用户确认后才进入下一步。**

> **单步调试**：每个子 Skill 均可独立调用（`/ops-brief`、`/ops-prompt`、`/ops-gen`）。

## 全流程（逐步确认）

```
用户需求
  │
  ▼ Step 1: ops-brief
  生成 brief + 创意概念 → 【用户确认】
  │
  ▼ Step 2: ops-prompt + expand-only
  生成 prompt → 生成扩图 → 展示 expanded.png → 【用户确认】
  │
  ▼ Step 3: text-only
  生成带文字图 → 展示 with_text.png → 【用户确认】
  │
  ▼ Step 4: 缩放终稿
  生成 banner_<title>.png (1920x960) → 展示终稿 → 【用户确认或回退】
```

### Step 1：需求理解 + 创意概念 → `/ops-brief`

- 输入：用户自然语言描述 + 可选图片
- 输出：结构化 brief JSON（含 `creative_concept`）
- 处理：标题翻译、图片用途判断、统一创意概念
- **注意**：参考图下载到 `/tmp/`，不要额外转存到 drafts/（`generate_image.py` 会自动复制）

**用户确认**：展示创意概念和 brief，使用 AskUserQuestion 让用户确认或给出调整建议。
- 确认 → 进入 Step 2
- 给出建议 → 融入建议重新生成 brief，再次确认

### Step 2：生成扩图 → `/ops-prompt` + `/ops-gen`（expand-only）

1. 调用 `/ops-prompt` 生成全部 prompt（base_prompt / square_prompt / expand_prompt / text_prompt）
2. 调用 `/ops-gen` 以 **expand-only** 模式生成扩图（省略 `--text-prompt`）
3. 展示 `expanded.png` 给用户

**用户确认**：使用 AskUserQuestion 让用户确认扩图效果或给出调整建议。
- 确认 → 进入 Step 3
- 给出建议 → 将建议融入，重新生成 expand_prompt，再生成 `expanded_v2.png`，再次确认

### Step 3：生成带文字图 → `/ops-gen`（text-only）

1. 调用 `/ops-gen` 以 **text-only** 模式，基于当前活跃 expanded 加文字
2. 展示 `with_text.png` 给用户

**用户确认**：使用 AskUserQuestion 让用户确认文字效果或给出调整建议。
- 确认 → 进入 Step 4
- 给出建议 → 将建议融入，重新生成 text_prompt，再生成 `with_text_v2.png`，再次确认

### Step 4：生成终稿 Banner

1. 将 `with_text.png` 缩放为 1920x960，保存为 `banner_<title>.png`
2. 展示终稿给用户

**用户确认**：询问用户是否满意。
- 满意 → 流程结束
- 不满意 → 用户指定回退到哪一步，从该步骤重新进入流程：
  - 回退到 Step 1 → 重新生成 brief
  - 回退到 Step 2 → 重新生成扩图
  - 回退到 Step 3 → 重新生成文字

## 图片生成路径与资源依赖

每一步都使用**前一步的输出**作为输入，迭代时同理——不要回退到更早的原始素材。

### 三条路径

| 条件 | 资源链 |
|------|--------|
| 无参考图 | `base_prompt` → **base.png** → expand → **expanded.png** → text → **with_text.png** |
| 有参考图（竖版） | reference → squarify → **square.png** → expand → **expanded.png** → text → **with_text.png** |
| 有参考图（宽幅） | **reference.png** → expand → **expanded.png** → text → **with_text.png** |

### 迭代时的资源依赖

| 迭代什么 | `--reference` 应传入 | 说明 |
|----------|---------------------|------|
| 重做扩图 | **square.png**（竖版）或 **reference.png**（宽幅）或 **base.png**（无参考图） | 使用上一步的产物，不回退到原始 reference |
| 重做文字 | 不需要 reference，`--save-intermediate` 指向当前活跃 **expanded*.png** | 脚本自动检测已存在并跳过扩图 |
| 重做 squarify | **原始 reference**（这是唯一需要回到原始素材的场景） | 重新 squarify 后产出 square_v2.png，后续扩图基于它 |

### 脚本自动检测模式

| 检测条件 | 模式 |
|----------|------|
| `--save-intermediate` 路径已存在 | text-only：跳过扩图，直接加文字 |
| 无 `--text-prompt` | expand-only：只跑扩图 |
| 其余 | 完整流程 |

## 迭代记录

用户的修改建议追加到 `drafts/request.txt`：
```
--- 修改建议 (YYYY-MM-DD HH:MM) ---
<用户修改建议原文>
```

## 版本管理

迭代时不覆盖已有文件，创建新版本：
- 首次：`expanded.png`、`with_text.png` → `banner_<title>.png`
- 第 N 次：`expanded_vN.png`、`with_text_vN.png` → `banner_<title>_vN.png`
- 仅重做文字：只产出 `with_text_vN` 和 `banner_vN`，不产出新 `expanded_vN`
- 重做扩图：产出新 `expanded_vN`，后续文字均基于此版本

**活跃 expanded 规则**：取 `drafts/` 下编号最大的 `expanded*.png`。

## 输出目录规范

每次任务在 `output/` 下创建独立子目录（使用 `scripts/utils.py` 的 `create_task_dir()`）：

```
{project_root}/output/YYMMDD-NN/
  banner_<title>.png              ← 终稿（1920x960）
  banner_<title>_v2.png           ← 迭代版本
  drafts/
    request.txt                   ← 用户原始需求 + 修改建议
    base.png                      ← AI 生成底图（无参考图时）
    reference.png/webp            ← 用户参考图（有参考图时）
    square.png                    ← 1:1 中间图（竖版参考图时）
    expanded.png                  ← 扩图 v1
    expanded_v2.png               ← 扩图 v2（迭代后）
    with_text.png                 ← 加文字 v1
    with_text_v2.png              ← 加文字 v2（迭代后）
```

## 共享资源

设计规范（供 `ops-prompt` 读取）：
- `references/style-guide.md` — 品牌色板、字体风格、视觉调性
- `references/specs/banner.md` — Banner 规格、构图规范、参考案例

脚本（供 `ops-gen` 调用）：
- `scripts/generate_image.py` — AI 绘图 API 调用
- `scripts/utils.py` — 共享工具函数（`create_task_dir()` 等）

### 后端模型

所有步骤统一使用 Google GenAI SDK，模型 `gemini-3.1-flash-image-preview`。
