---
name: noname-extension-dev
description: 基于本仓库教程构建、讲解与调试无名杀扩展。用户请求涉及扩展结构、角色创建、技能触发/效果/条件/标记/类型、卡牌开发、AI 行为、联机同步、音频与皮肤配置、代码规范或 API 查询时使用此技能。
---

# 无名杀扩展开发

## 概述

使用本技能把用户需求转成符合无名杀扩展规范的代码与说明。先做任务分类，再只加载最小必要章节，避免无关文档占用上下文。

## 工作流

1. 编码前先分类请求。  
把需求映射到以下类别之一或多项：扩展骨架、角色、技能、触发时机、技能效果、条件判断、标记机制、卡牌、AI、联机、音频、皮肤、代码规范、API 查询。

2. 只加载最小必要参考。  
先读 `references/chapter-map.md`，再按映射打开 `references/tutorial/` 下对应章节。

3. 涉及技能实现时优先检索数据集。  
先把用户原话改写为关键词，再调用搜索脚本。  
搜索命令仅传关键词：`python scripts/search_dataset.py --query "<关键词串>" --top-k 8 --no-multi-route`。

固定执行链路（必须遵循）：  
用户原话（自然语言） -> 改写成关键词（触发词/效果词/同义词） -> 用关键词调用搜索脚本返回 Top-K。  
执行命令模板（不要带尖括号）：`python scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route`

4. 按无名杀常用写法实现。  
默认优先 async 风格，除非用户明确要求传统 step 风格。

5. 依据教程规范自检。  
对照 `references/tutorial/code-standard.md` 与 `references/tutorial/appendix/api.md` 检查命名、触发位置、filter/check 逻辑和 API 用法。

6. 输出可直接复用的结果。  
提供完整代码片段、建议放置位置和简要依据说明。

7. 生成技能/卡牌时强制 JS 对象格式输出。  
当用户请求“生成技能”或“生成卡牌”时，最终答案必须包含 JavaScript 对象字面量（`skill={...}` 或 `card={...}`）。  
允许使用无引号键名、单引号、尾逗号、函数与 `async content(){}` 等无名杀常见 JS 写法。  
若用户未指定格式，默认输出如下结构之一：  
技能：`skill={ ... }`  
卡牌：`card={ ... }`  
并在对象代码后追加一段“专业游戏技能描述”（面向玩家的正式文案，清楚写出触发时机、条件、效果与次数/限制）。  
固定输出模板（必须遵循）：  
第一段：完整 `skill={...}` 或 `card={...}` 对象；  
第二段：`技能描述：...`（单段专业文案）。  
除这两段外，不得输出额外说明、标题、步骤、Markdown 代码块（禁止 ```）。  
对象段第一行必须以 `skill={` 或 `card={` 开头。  
`skill={...}` 必须是单个技能配置对象本体，禁止写成 `skill={ 技能名:{...} }` 的二层包裹结构。  
`card={...}` 同理，必须直接是单卡配置对象本体。

## 任务路由

- 构建或修复扩展入口与目录：  
使用 `references/tutorial/structure.md`。

- 讲解本项目语境下的 JavaScript 基础：  
使用 `references/tutorial/basic.md`。

- 创建角色包、势力、前缀：  
使用 `references/tutorial/character.md`。

- 编写或审查技能代码：  
先用 `references/tutorial/skill.md`，再按需补充 `references/tutorial/trigger.md`、`references/tutorial/effect.md`、`references/tutorial/condition.md`、`references/tutorial/mark.md`、`references/tutorial/animation.md`、`references/tutorial/skill-types.md`。

- 编写或平衡卡牌：  
使用 `references/tutorial/card.md`。

- 优化 AI 行为：  
使用 `references/tutorial/ai.md`。

- 处理联机兼容与同步：  
使用 `references/tutorial/online.md`。

- 配置配音与皮肤：  
使用 `references/tutorial/audio.md` 与 `references/tutorial/skin.md`。

- 统一命名、格式、结构：  
使用 `references/tutorial/code-standard.md`。

- 查询可调用方法和引擎接口：  
使用 `references/tutorial/appendix/api.md`。

- 根据技能描述快速找实现模板：  
使用 `assets/dataset.sqlite3`，并运行 `scripts/search_dataset.py` 检索 Top-K 示例。

## 快速检索模式

优先用 `rg` 精准定位，再读取正文：

- 查找触发时机定义：  
`rg -n "trigger|时机|phase|damage|useCard" references/tutorial/trigger.md`

- 查找 filter/check/mod 条件示例：  
`rg -n "filter|check|mod|条件" references/tutorial/condition.md references/tutorial/skill.md`

- 快速定位技能类型示例：  
`rg -n "限定技|锁定技|主公技|觉醒技|转换技|使命技|蓄力技|clan|zhu|juexingji|zhuanhuanji|shimingji" references/tutorial/skill-types.md`

- 快速定位 API 分节：  
`rg -n "### 1\\.|### 1\\.[0-9]|### 2\\.|### 3\\.|### 4\\.|### 5\\.|### 6\\.|### 7\\." references/tutorial/appendix/api.md`

- 通过描述检索数据集：  
`python scripts/search_dataset.py --query "锁定技 体力变化 蓄力" --top-k 5`

- 手动关键词检索（示例）：  
`python scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route`

- 收紧匹配阈值（减少噪声）：  
`python scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route --min-overlap 3 --min-score 10`

- 启用 SQLite 检索（默认）：  
`python scripts/search_dataset.py --query "做一个收到伤害摸牌的技能" --top-k 8 --show-routes --candidate-pool 800 --min-score 12`

## 输出规则

- 保持代码风格与教程一致。  
- 优先给最小可运行实现，再补可选增强。  
- 用户问题涉及文档未覆盖的引擎细节时，明确标注不确定性。  
- 用户要求生成技能/卡牌时，必须返回无名杀可直接使用的 JS 对象格式。  
- 用户要求生成技能/卡牌时，最后必须再输出一段专业技能描述文案。  
- 生成前必须自检：括号是否闭合、逗号位置是否正确、字段是否落在同一对象中。  
- 若格式不满足模板，必须先在内部重写为合格格式，再输出最终结果。  
