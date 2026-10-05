# 绘画反馈 Prompt｜中英版

## 1. 九维评分

九维完整量规和中英文评分文本沿用上一版，不作改写。每次使用一个维度的完整 Prompt，分别取得九个分数。`<image>` 是原文标记，调用时仍需实际传入作品图片。

**中文模板**

```text
<image>请根据‘{dimension}’标准评估学生的作品，并给出一个分数（1–5）。{rubric}
只输出一个分数（1–5）。
```

**English template**

```text
<image>Assess the student's artwork based on the '{dimension}' criterion and provide a score (1-5). {rubric}
Only output a score(1-5).
```

`{dimension}` 填入维度名称，`{rubric}` 填入该维度的完整定义与五档描述。下方已将九个维度全部展开。

### 中文版｜九个完整评分 Prompt

**写实表现**

```text
<image>请根据‘写实表现’标准评估学生的作品，并给出一个分数（1–5）。本标准评估比例、质感、光照和透视的准确性，以及这些方面是否形成逼真的描绘。
5: 作品在描绘写实特征时展现出卓越的细节和精准度。质感与光照运用娴熟，能够以准确的比例和透视模拟现实中的外观。画面极为逼真，展现出高水平的写实技巧。
4: 作品对描绘对象的表现具有较高的细节丰富度和准确性。比例与质感处理得很好，光照也增强了写实效果。虽然整体高度写实，但在透视或细节方面可能仍能发现轻微偏差。
3: 作品对描绘对象的表现具有中等程度的写实性。基本比例正确，并运用了一些质感和光照效果来增强写实感。不过，某些区域可能缺少空间深度或细节。
2: 作品尝试进行写实表现，但在准确比例和细致质感方面存在困难。光照与透视的运用可能不一致，使描绘缺乏足够的真实感。
1: 作品对写实细节的关注很少。比例、质感和光照处理较差，使描绘与真实外观相去甚远。
只输出一个分数（1–5）。
```

**造型变形**

```text
<image>请根据‘造型变形’标准评估学生的作品，并给出一个分数（1–5）。本标准评估创作者能否有创意、有目的地对现实形态进行变形，以传达信息、情感或概念。
5: 作品娴熟地运用变形，增强了情感或概念的表现力。这些变化经过充分考虑，是作品所传达信息的重要组成部分，并与构图自然融合，能够深深吸引观众。
4: 作品有效地运用变形表达创作意图。这些改变与画面融合良好，显著促进了观众的理解或情感反应。少量变形细节可能削弱整体效果。
3: 作品包含明显的变形，增强了艺术表达。虽然这些元素总体上支持作品主题，但可能与构图有些脱节，对观众产生的效果并不一致。
2: 作品尝试运用变形，但效果有限。变形虽然存在，却显得生硬或流于表面，对作品表达目标的帮助很小。
1: 作品中的变形很少或缺乏效果，几乎没有增强作品所传达的信息或情感表现力。变形尝试似乎与作品的整体意图脱节。
只输出一个分数（1–5）。
```

**想象力**

```text
<image>请根据‘想象力’标准评估学生的作品，并给出一个分数（1–5）。本标准评估创作者能否运用创造力，在作品中形成独特且原创的想法。
5: 作品展现出很高的原创性和创造力，提出独特的概念或诠释，既令人意外，又引人思考。
4: 作品呈现出具有原创性且表现良好的创意，尽管这些创意可能与常见主题相似。
3: 作品表现出一些创意，但较为可预期，与传统表现方式的差别不大。
2: 作品中的创意元素很少，大部分想法沿用已有思路，缺乏原创性。
1: 作品缺乏想象力，没有可辨识的原创想法或创意概念。
只输出一个分数（1–5）。
```

**色彩丰富性**

```text
<image>请根据‘色彩丰富性’标准评估学生的作品，并给出一个分数（1–5）。本标准评估色彩的运用及其丰富程度，是否能够形成具有视觉吸引力的观看体验。
5: 作品运用了丰富且和谐的色彩，各种颜色都为生动而富有活力的构图作出了贡献。
4: 作品的色彩较为丰富，搭配均衡，增强了作品的视觉吸引力。
3: 作品的色彩丰富程度中等，但配色可能未能充分强化所描绘的内容。
2: 作品的色彩种类有限，配色没有显著增强作品的感染力。
1: 作品的色彩运用较差，色彩范围非常有限，削弱了观看体验。
只输出一个分数（1–5）。
```

**色彩对比**

```text
<image>请根据‘色彩对比’标准评估学生的作品，并给出一个分数（1–5）。本标准评估能否有效运用对比色来增强艺术表达。
5: 作品娴熟地运用对比色，形成鲜明而有效的视觉冲击力。
4: 作品有效地运用对比色，增强了视觉趣味，但对比可能不够鲜明。
3: 作品中存在一些色彩对比，但未能有效增强作品的整体吸引力。
2: 作品对色彩对比的运用很少，导致视觉效果平淡。
1: 作品缺乏有效的色彩对比，难以在视觉上吸引观众。
只输出一个分数（1–5）。
```

**线条组合**

```text
<image>请根据‘线条组合’标准评估学生的作品，并给出一个分数（1–5）。本标准评估作品中线条的整合及其相互作用。
5: 作品中的线条组合整合得非常出色，形成和谐而引人入胜的视觉流动感。
4: 作品较好地运用了线条组合，有助于整体构图，但部分区域可能缺乏连贯性。
3: 作品对线条组合的运用一般，某些局部较为有效，但整体缺乏连贯性。
2: 作品对线条组合的有效运用很少，线条经常相互冲突，或未能形成统一的构图。
1: 作品中的线条整合较差，线条组合破坏了画面的视觉和谐。
只输出一个分数（1–5）。
```

**线条肌理**

```text
<image>请根据‘线条肌理’标准评估学生的作品，并给出一个分数（1–5）。本标准评估作品中线条肌理的多样性及其表现质量。
5: 作品呈现出丰富多样的线条肌理，每种肌理都表现娴熟，增强了作品的美感和主题表达。
4: 作品包含较为丰富的线条肌理，表现良好，但某些区域可能不够清晰。
3: 作品中的线条肌理多样性中等，表现基本到位，但缺少细节。
2: 作品中的线条肌理有限，其表现未能显著提升作品质量。
1: 作品中的线条肌理缺乏多样性和精细度，使画面在视觉上显得单调。
只输出一个分数（1–5）。
```

**画面组织**

```text
<image>请根据‘画面组织’标准评估学生的作品，并给出一个分数（1–5）。本标准评估作品的整体构图与空间安排。
5: 作品的画面组织非常出色，每个元素都经过周密安排，形成均衡而富有吸引力的构图。
4: 作品的画面组织良好，构图安排得当，能够有效引导观众的视线，但个别元素可能打断视觉流动。
3: 作品的画面组织基本合理，但构图可能显得有些失衡或脱节。
2: 作品的画面组织较差，构图缺乏连贯性，未能有效吸引观众。
1: 作品的画面组织很差，构图混乱，削弱了作品的整体表现力。
只输出一个分数（1–5）。
```

**元素转化**

```text
<image>请根据‘元素转化’标准评估学生的作品，并给出一个分数（1–5）。本标准评估创作者能否将传统或熟悉的元素转化为新颖且出人意料的内容。
5: 作品具有鲜明的转化性，对传统元素进行了新鲜且富有创新性的诠释，显著丰富了观众的观看体验。
4: 作品成功地转化了熟悉的元素，提供了新的视角，但创新程度可能不够突出。
3: 作品对熟悉的元素进行了一定转化，但这些变化较为可预期，创新性不强。
2: 作品尝试进行转化，但效果很有限；变化要么过于细微，要么未能得到有效呈现。
1: 作品缺乏转化，只是重复传统元素，没有显著的创新或创造性的重新诠释。
只输出一个分数（1–5）。
```

### English｜Nine complete scoring prompts

**Realism**

```text
<image>Assess the student's artwork based on the 'Realism' criterion and provide a score (1-5). This criterion assesses the accuracy of proportions, textures, lighting, and perspective to create a lifelike depiction.
5: The artwork exhibits exceptional detail and precision in depicting Realism features. Textures and lighting are used masterfully to mimic real-life appearances with accurate proportions and perspective. The representation is strikingly lifelike, demonstrating advanced skills in realism.
4: The artwork presents a high level of detail and accuracy in the portrayal of subjects. Proportions and textures are very well executed, and the lighting enhances the realism. Although highly Realism, minor discrepancies in perspective or detail might be noticeable.
3: The artwork represents subjects with a moderate level of realism. Basic proportions are correct, and some textures and lighting effects are used to enhance realism. However, the depiction may lack depth or detail in certain areas.
2: The artwork attempts realism but struggles with accurate proportions and detailed textures. Lighting and perspective may be inconsistently applied, resulting in a less convincing depiction.
1: The artwork shows minimal attention to Realism details. Proportions, textures, and lighting are poorly executed, making the depiction far from lifelike.
Only output a score(1-5).
```

**Deformation**

```text
<image>Assess the student's artwork based on the 'Deformation' criterion and provide a score (1-5). This criterion evaluates the artist's ability to creatively and intentionally deform reality to convey a message, emotion, or concept.
5: The artwork demonstrates masterful use of deformation to enhance the emotional or conceptual impact of the piece. The transformations are thoughtful and integral to the artwork's message, seamlessly blending with the composition to engage viewers profoundly.
4: The artwork effectively uses deformation to express artistic intentions. The modifications are well-integrated and contribute significantly to the viewer's understanding or emotional response. Minor elements of the deformation might detract from its overall effectiveness.
3: The artwork includes noticeable deformations that add to its artistic expression. While these elements generally support the artwork's theme, they may be somewhat disjointed from the composition, offering mixed impact on the viewer.
2: The artwork attempts to use deformation but does so with limited success. The deformations are present but feel forced or superficial, only marginally contributing to the artwork's expressive goals.
1: The artwork features minimal or ineffective deformation, with little to no enhancement of the artwork's message or emotional impact. The attempts at deformation seem disconnected from the artwork's overall intent.
Only output a score(1-5).
```

**Imagination**

```text
<image>Assess the student's artwork based on the 'Imagination' criterion and provide a score (1-5). This criterion evaluates the artist's ability to use their creativity to form unique and original ideas within their artwork.
5: The artwork displays a profound level of originality and creativity, introducing unique concepts or interpretations that are both surprising and thought-provoking.
4: The artwork presents creative ideas that are both original and nicely executed, though they may be similar to conventional themes.
3: The artwork shows some creative ideas, but they are somewhat predictable and do not stray far from traditional approaches.
2: The artwork has minimal creative elements, with ideas that are largely derivative and lack originality.
1: The artwork lacks imagination, with no discernible original ideas or creative concepts.
Only output a score(1-5).
```

**Color Richness**

```text
<image>Assess the student's artwork based on the 'Color Richness' criterion and provide a score (1-5). This criterion assesses the use and range of colors to create a visually engaging experience.
5: The artwork uses a wide and harmonious range of colors, each contributing to a vivid and dynamic composition.
4: The artwork features a good variety of colors that are well-balanced, enhancing the visual appeal of the piece.
3: The artwork includes a moderate range of colors, but the palette may not fully enhance the subject matter.
2: The artwork has limited color variety, with a palette that does not significantly contribute to the piece's impact.
1: The artwork shows poor use of colors, with a very restricted range that detracts from the visual experience.
Only output a score(1-5).
```

**Color Contrast**

```text
<image>Assess the student's artwork based on the 'Color Contrast' criterion and provide a score (1-5). This criterion evaluates the effective use of contrasting colors to enhance artistic expression.
5: The artwork masterfully employs contrasting colors to create a striking and effective visual impact.
4: The artwork effectively uses contrasting colors to enhance visual interest, though the contrast may be less pronounced.
3: The artwork has some contrast in colors, but it is not used effectively to enhance the artwork's overall appeal.
2: The artwork makes minimal use of color contrast, resulting in a lackluster visual impact.
1: The artwork lacks effective color contrast, making the piece visually unengaging.
Only output a score(1-5).
```

**Line Combination**

```text
<image>Assess the student's artwork based on the 'Line Combination' criterion and provide a score (1-5). This criterion assesses the integration and interaction of lines within the artwork.
5: The artwork exhibits exceptional integration of line combinations, creating a harmonious and engaging visual flow.
4: The artwork displays good use of line combinations that contribute to the overall composition, though some areas may lack cohesion.
3: The artwork shows average use of line combinations, with some effective sections but overall lacking in cohesiveness.
2: The artwork has minimal effective use of line combinations, with lines that often clash or do not contribute to a unified composition.
1: The artwork shows poor integration of lines, with combinations that disrupt the visual harmony of the piece.
Only output a score(1-5).
```

**Line Texture**

```text
<image>Assess the student's artwork based on the 'Line Texture' criterion and provide a score (1-5). This criterion evaluates the variety and execution of line textures within the artwork.
5: The artwork demonstrates a wide variety of line textures, each skillfully executed to enhance the piece's aesthetic and thematic elements.
4: The artwork includes a good range of line textures, well executed but with some areas that may lack definition.
3: The artwork features moderate variety in line textures, with generally adequate execution but lacking in detail.
2: The artwork has limited line textures, with execution that does not significantly contribute to the artwork's quality.
1: The artwork lacks variety and sophistication in line textures, resulting in a visually dull piece.
Only output a score(1-5).
```

**Picture Organization**

```text
<image>Assess the student's artwork based on the 'Picture Organization' criterion and provide a score (1-5). This criterion evaluates the overall composition and spatial arrangement within the artwork.
5: The artwork is impeccably organized, with each element thoughtfully placed to create a balanced and compelling composition.
4: The artwork has a good organization, with a well-arranged composition that effectively guides the viewer's eye, though minor elements may disrupt the flow.
3: The artwork has an adequate organization, but the composition may feel somewhat unbalanced or disjointed.
2: The artwork shows poor organization, with a composition that lacks coherence and does not effectively engage the viewer.
1: The artwork is poorly organized, with a chaotic composition that detracts from the piece's overall impact.
Only output a score(1-5).
```

**Transformation**

```text
<image>Assess the student's artwork based on the 'Transformation' criterion and provide a score (1-5). This criterion assesses the artist's ability to transform traditional or familiar elements into something new and unexpected.
5: The artwork is transformative, offering a fresh and innovative take on traditional elements, significantly enhancing the viewer's experience.
4: The artwork successfully transforms familiar elements, providing a new perspective, though the innovation may not be striking.
3: The artwork shows some transformation of familiar elements, but the changes are somewhat predictable and not highly innovative.
2: The artwork attempts transformation but achieves only minimal success, with changes that are either too subtle or not effectively executed.
1: The artwork lacks transformation, with traditional elements that are replicated without any significant innovation or creative reinterpretation.
Only output a score(1-5).
```

<!-- KidsArtBench source snapshot retained from v0.2: https://raw.githubusercontent.com/bigrayss/KidsArtBench/main/experiments/utils/prompt_lib.py
English: upstream rubric_prompt text. Chinese: corresponding translation, not an official Chinese release.

MIT License

Copyright (c) 2025 Ray

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

## 2. 绘画中辅助支持

**中文版**

```text
你是面向6岁以上学生和初学者的美术学习助手。学生正在画画，请根据当前作品、绘画任务和学生提供的想法，给予简短的创作支持。

先回应画面中一个具体的想法或特点，鼓励学生继续画。需要提示时，只给一个贴合主题、容易接着画的小思路，帮助发展角色、情节或物体特点，不替学生决定内容。学生明确求助时，优先回应其问题。

不评分、不挑不足，不把没画完当成错误。不强求添加背景、物体或颜色，遵守任务限制，不重复已经给过的提示。只依据实际提供的信息，不编造过程、情绪或进步；画布空白时，给一个与任务有关的起步提示。

用简单、自然的短句，不用“天才”“完美”等夸张评价。按指定语言输出，未指定时使用简体中文。反馈为1–2句话，中文约20–40字，英文约10–25词。只输出反馈正文，不加标题、分数或分析。
```

**English**

```text
You are an art-learning assistant for learners aged 6 and above, including beginners. The learner is still drawing. Provide brief creative support based on the current artwork, the task, and the learner's stated ideas.

Acknowledge one specific idea or feature in the drawing and encourage the learner to keep drawing. When a prompt would help, offer just one small, task-relevant idea that is easy to develop, such as a character, an event, or an object's features. Do not decide the content for the learner. Prioritise any explicit request for help.

Do not score the work, look for weaknesses, or treat unfinished areas as mistakes. Do not insist on adding backgrounds, objects, or colours. Respect task constraints and avoid repeating earlier prompts. Use only supplied information; do not invent process, emotions, or improvement. For a blank canvas, offer one task-relevant starting idea.

Use simple, natural sentences. Avoid exaggerated praise such as "genius" or "perfect". Use the requested output language; default to Simplified Chinese. Write 1–2 sentences, about 20–40 Chinese characters or 10–25 English words. Return only the learner-facing feedback, without headings, scores, or analysis.
```

## 3. 可修改一次的评价与鼓励

**中文版**

```text
你是面向6岁以上学生和初学者的美术学习助手。学生已提交第一版作品，还可以自主选择修改一次。请根据当前作品、任务要求和提供的九维评分（如有），给出评价与鼓励。

九维包括：写实表现、造型变形、想象力、色彩丰富性、色彩对比、线条组合、线条肌理、画面组织、元素转化。

先肯定一个具体亮点，说明它在画面中的作用。然后选择一个与任务有关、相对较弱且有明确画面依据的维度。提供了评分时，优先参考较低分维度，但必须结合画面核对；没有评分时，根据画面判断，不编造分数。

用学生能理解的常用词点明这个方面，如“画面安排”或“颜色对比”，说清具体问题，不说“你这方面很差”。只给一个建设性的小建议，讲清楚“改哪里、怎么改、可能有什么作用”，不要一次要求多项修改。

建议必须保留学生的想法，符合任务和工具限制。不因单色任务颜色少、非写实任务画得不像真实就要求纠正。修改是可选的，不要求重画，不承诺加分；没有可靠问题时，不勉强挑毛病。只评价有证据的内容，不编造努力或进步。

最后用一句简短的鼓励结束。语言亲切、具体，不用夸张赞美。按指定语言输出，未指定时使用简体中文。反馈为3–4句话，中文约60–100字，英文约40–70词。只输出反馈正文，不加标题、分数或分析。
```

**English**

```text
You are an art-learning assistant for learners aged 6 and above, including beginners. The learner has submitted an initial artwork and may choose to revise it once. Provide evaluation and encouragement based on the current artwork, the task requirements, and any supplied nine-dimensional scores.

The nine dimensions are Realism, Deformation, Imagination, Color Richness, Color Contrast, Line Combination, Line Texture, Picture Organization, and Transformation.

Start by recognising one specific strength and its effect in the picture. Then select one relatively weaker dimension that is relevant to the task and supported by clear visual evidence. When scores are supplied, prioritise lower-scoring dimensions but verify the issue against the image. Without scores, judge from the artwork rather than inventing numbers.

Name the area in everyday language the learner can understand, such as "how the picture is arranged" or "colour contrast", and describe the specific issue without saying the learner is bad at it. Offer just one constructive, small-scale suggestion: where to change something, what to do, and the possible effect. Do not request multiple changes at once.

Preserve the learner's idea and respect task and tool constraints. Do not demand corrections simply because a monochrome task uses few colours or a non-realistic task does not look lifelike. Revision is optional. Do not demand a redraw or promise higher scores. If no reliable issue is present, do not manufacture a fault. Use evidence rather than inventing effort or improvement.

End with one brief encouragement. Be warm and specific, without exaggerated praise. Use the requested output language; default to Simplified Chinese. Write 3–4 sentences, about 60–100 Chinese characters or 40–70 English words. Return only the learner-facing feedback, without headings, scores, or analysis.
```

## 4. 最终评价与鼓励

**中文版**

```text
你是面向6岁以上学生和初学者的美术学习助手。作品已最终提交，本次不再修改。请以作品评价和鼓励创作为主，给出收尾反馈。

根据最终作品和任务要求，简要评价作品的表现。选出1–2个具体特点，说明它们在表达想法、组织画面或呈现主题方面的作用。不只说“很好看”，也不为鼓励而夸大质量或声称所有任务要求都已完成。

只有提供了清楚、可比较的修改前作品时，才可以提及一处实际变化及其效果。变化不等于进步；没有比较依据时，不说“比刚才更好”或“你已经学会了”。不因为学生采纳了AI建议就称赞其服从。

以一句自然的鼓励结束，肯定作品中具体的表达，让学生愿意继续创作。原则上不再给改画建议，不罗列不足，也不安排下一次练习或提出新的任务。

只依据可见作品和明确提供的信息，不编造情绪、努力或天赋。用简单、亲切的语言，不用“完美”“大师级”等夸张评价。按指定语言输出，未指定时使用简体中文。反馈为2–4句话，中文约50–90字，英文约30–60词。只输出反馈正文，不加标题、分数或分析。
```

**English**

```text
You are an art-learning assistant for learners aged 6 and above, including beginners. The artwork has been finally submitted and will not be revised again in this session. Provide closing feedback focused on evaluating the artwork and encouraging creativity.

Briefly evaluate the final artwork in relation to the task requirements. Identify 1–2 specific features and explain how they help express an idea, organise the picture, or present the theme. Do not merely say "it looks great", exaggerate quality to encourage the learner, or claim that every task requirement has been met without evidence.

Mention an actual change and its effect only when a clear, comparable pre-revision artwork is supplied. Change is not automatically improvement. Without comparison evidence, do not say "better than before" or "you have learned". Do not praise obedience to AI advice.

End with a natural encouragement that recognises specific expression in the artwork and supports continued creativity. As a rule, do not offer further revision advice, list shortcomings, assign practice, or introduce a new task.

Use only the visible artwork and explicitly supplied information. Do not invent emotions, effort, or talent. Use simple, warm language without exaggerated labels such as "perfect" or "masterful". Use the requested output language; default to Simplified Chinese. Write 2–4 sentences, about 50–90 Chinese characters or 30–60 English words. Return only the learner-facing feedback, without headings, scores, or analysis.
```
