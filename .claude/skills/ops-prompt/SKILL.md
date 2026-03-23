---
name: ops-prompt
description: 运营物料绘图 Prompt 生成。根据结构化 brief（含创意概念）和设计规范，生成单图直出的绘图 prompt。可单独调用以调优 prompt 质量。当用户说"生成绘图 prompt"、"优化 prompt"或需要单独测试 prompt 生成能力时触发。
---

# ops-prompt — 绘图 Prompt 生成

根据结构化 brief JSON（含创意概念）和设计规范，生成**单图直出**的绘图 prompt。文字与画面融为一体，一次性生成完整 Banner。

**所有 prompt 必须严格遵循 brief 中的 `creative_concept`。**

## 输入

标准化 brief JSON（由 `ops-brief` 输出），必须包含 `creative_concept` 字段。以下两个条件决定生成哪些 prompt：

- `reference_images` 是否为空 → 决定是否需要生成 `base_prompt`
- `expanded.png` 是否已存在（文字迭代场景）→ 只生成 `text_prompt`，跳过 `base_prompt` 和 `expand_prompt`

## 处理流程

### 1. 判断生成模式

| 条件 | 生成 |
|------|------|
| 无参考图，`expanded.png` 不存在 | base_prompt + expand_prompt + text_prompt |
| 有参考图（竖版），`expanded.png` 不存在 | square_prompt + expand_prompt + text_prompt |
| 有参考图（非竖版），`expanded.png` 不存在 | expand_prompt + text_prompt |
| `expanded.png` 已存在（文字迭代） | text_prompt 只 |

**文字迭代时**：结合用户的修改建议（如"文字太小"、"换成红色"）调整 text_prompt，其余不变。

### 2. 加载设计规范

读取两份参考文件（路径相对于 `.claude/skills/ops-design/`）：

1. **风格参考** — 读取 `references/style-guide.md`
   - 获取项目整体视觉调性、品牌色板、字体风格等

2. **Banner 规格** — 读取 `references/specs/banner.md`
   - 固定尺寸 1920x960（2:1），单图直出
   - 构图要点：文字左上大字 + 主视觉偏右 + 互相穿插
   - 查看构图参考案例（仅理解构图，不作为生成输入）

### 3. 生成绘图 Prompt

**从 `creative_concept` 提取并遵循**：`visual_theme`、`color_scheme`、`composition`、`style`、`typography_direction`、`mood_keywords`。

根据步骤 1 的判断结果决定生成哪些 prompt。文字迭代时只生成 `text_prompt`，并将用户修改建议融入其中。

#### base_prompt（仅无参考图时生成）

底图生成 prompt，纯画面无文字。底图应画面饱满、内容丰富，留白由后续扩图步骤处理。

```
[visual_theme 展开为具体场景描述],
[主视觉元素] as the focal point of the composition,
[装饰元素] filling the scene richly,
[color_scheme 色彩] background with [具体背景氛围/纹理描述], [mood_keywords 氛围],
rich and full composition with no empty areas,
high quality, detailed illustration.
No text. No title. No letters. No words.
No pure white background.
```

**要点**：
- 只描述画面视觉，完全不包含文字相关描述
- 主视觉元素居中为焦点，画面内容饱满丰富，不刻意偏移或留白
- 必须有实际的背景色/氛围/纹理，禁止纯白背景（后续扩图需要背景信息来延伸）
- 明确写 "No text" 避免 AI 自动生成文字

#### square_prompt（仅竖版参考图时生成）

将竖版参考图重构为 1:1 正方形，保留主体完整性。脚本在宽高比 < 0.85 时自动触发 squarify 步骤。

```
Redraw this [原图风格] image as a perfect square 1:1 composition.
Recompose the [主体描述]: center it in the frame, and scale it up so it occupies
at least 60-70% of the canvas area — the subject should feel bold and dominant.
Keep the subject's proportions, art style, and details intact, but make it larger
and more centered than the original if needed.
Fill the remaining space with [背景描述], matching the original [color_scheme] seamlessly.
The background should support the subject, not compete with it — keep it simple and cohesive.
No text. No letters. Square 1:1 aspect ratio.
```

**要点**：
- **居中**：主体偏边时必须调整到画面中心
- **放大**：主体在原图中占比小时需放大，使其在 1:1 画面中饱满突出（至少占 60-70% 画面）
- 保留主体细节和风格，不裁切、不变形
- 背景延伸需匹配原图色调和风格，保持简洁不喧宾夺主
- 根据 creative_concept 中的视觉主题定制背景元素
- 明确写 "No text" 避免生成文字

#### expand_prompt（始终生成）

将底图/参考图扩展至 2:1 宽幅，不含文字。

```
Expand this [原图风格] image into a wide 2:1 banner composition.
Keep the [主体描述] on the right side of the frame.
Extend the scene in both directions with [场景延伸描述].
IMPORTANT: The left ~40% area should have a relatively clean, unified background
with subtle decorative elements only — this area needs to remain visually simple
to accommodate title text in the next step. Avoid dense or complex details on the left.
The right side can remain rich and detailed around the subject.
Match the original [风格/色调] seamlessly.
No text. No title. No letters.
Wide 2:1 aspect ratio.
```

**要点**：
- **左侧留呼吸空间**：左侧 ~40% 保持简洁统一的背景调性，只放少量散点装饰
- 强调 "No text"，确保扩图不会意外生成文字
- 双向拓展（不仅仅向左），让主体放置于中间偏右侧
- 主体区域可以视觉丰富

#### text_prompt（始终生成）

在扩图结果上叠加标题文字。

```
Add large prominent title text "[title]" in [typography_direction] on the upper left area.
Use highly creative typographic design: vary the size, weight, and baseline of both
individual words AND individual letters to create strong visual hierarchy and rhythm.
Make one or two anchor letters extra-large and bold (e.g. the first letter of each word),
while other letters shift in size, weight, and vertical baseline — some rising above,
some dropping below — to create a sense of dynamic movement and artistic hand-crafted typography.
Do NOT use uniform lettering where all characters are the same size and alignment.
The text should have [文字材质/颜色/装饰效果描述],
with [装饰细节: 如光效、粒子、纹理、阴影等与画面风格匹配的点缀].
Text and [周围元素] should naturally intertwine and overlap.
Keep the existing scene and [主体] completely intact, do not alter the background.
The text should be large and impactful, occupying about 50-60% of the image height.
Match the [风格] of the existing illustration.
IMPORTANT: Maintain the exact same image dimensions and wide 2:1 aspect ratio. Do not crop, resize, or change the canvas proportions.
```

**要点**：
- 标题文字用引号包裹，确保 AI 准确渲染
- 强调不要改变已有画面，只添加文字
- **字体设计感**：通过单词和字母间的大小、粗细、基线错位制造视觉层次和节奏感，避免所有字符等大排列
- **装饰细节**：根据画面风格添加与文字融合的装饰效果（光晕、粒子、纹理、阴影等），让文字成为画面的有机组成部分
- 文字风格描述要具体
- 确保文字清晰可识别
- **必须要求保持原图尺寸和 2:1 宽高比**，防止模型输出比例漂移

#### 通用要点

- 所有 prompt 的风格描述需保持一致
- 避免硬分区描述（不要说 "left side is text area, right side is image"）
- 背景是全幅统一场景

### 3. 输出与后续流程

生成的 prompt 组无需用户单独确认，**自动继续后续生成流程**：

1. 调用 `/ops-gen` expand-only 生成扩图 → 展示 `expanded.png` → 用户确认
2. 调用 `/ops-gen` text-only 加文字 → 展示 `with_text.png` → 用户确认
3. 缩放为终稿 banner → 用户确认

**迭代时**：当用户对扩图或文字不满意并给出调整建议时，只重新生成对应的 prompt（expand_prompt 或 text_prompt），将用户反馈融入新 prompt，再调用 `/ops-gen` 重新生成对应步骤，然后继续后续流程。
