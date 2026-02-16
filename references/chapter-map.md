# 章节映射

先用本文件确定最小读取范围，再打开对应章节正文。

## 核心文档

- `tutorial/README.md`：教程总览与章节入口。  
- `tutorial/_sidebar.md`：文档站章节顺序。  
- `tutorial/structure.md`：扩展目录结构与 async/step 写法。  
- `tutorial/code-standard.md`：命名、格式、结构规范。  
- `tutorial/appendix/api.md`：玩家/卡牌/事件/游戏/UI 等 API 索引。
- `../assets/dataset.jsonl`：技能描述到实现代码的数据集（4398 条）。

## 按任务选文档

- JavaScript 基础与新手入门：  
`tutorial/basic.md`

- 角色、势力与前缀定义：  
`tutorial/character.md`

- 技能基础实现：  
`tutorial/skill.md`

- 触发时机与事件钩子：  
`tutorial/trigger.md`

- 技能效果实现模式：  
`tutorial/effect.md`

- 条件判断与门控逻辑：  
`tutorial/condition.md`

- 标记与存储机制：  
`tutorial/mark.md`

- 技能动画与视觉效果：  
`tutorial/animation.md`

- 技能类型总览与示例：  
`tutorial/skill-types.md`

- 卡牌定义、效果、动画、音效：  
`tutorial/card.md`

- AI 决策与目标优先级：  
`tutorial/ai.md`

- 联机同步与多人兼容：  
`tutorial/online.md`

- 配音与音频配置：  
`tutorial/audio.md`

- 皮肤与变体资源：  
`tutorial/skin.md`

## 附录示例

- 共享手牌技能示例：  
`tutorial/appendix/share-skill.md`

- 充能条技能示例：  
`tutorial/appendix/enery-skill.md`

## 数据集检索

- 数据集检索脚本：  
`../scripts/search_dataset.py`

- 数据集校验脚本：  
`../scripts/validate_dataset.py`

- 关键词清单：  
`search-keywords.md`

- 常用命令：  
`python ../scripts/validate_dataset.py`  
`python ../scripts/search_dataset.py --query "锁定技 体力变化"`  
`python ../scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route`  
`python ../scripts/search_dataset.py --query "主公技 群势力 杀" --top-k 8 --full-output`  
