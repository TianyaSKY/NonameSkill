# 搜索关键词清单

用于手动拼接 `search_dataset.py --query` 的关键词串。  
建议每次组合 3-6 个词：`触发词 + 效果词 + 限制词/类型词`。

## 1. 触发词（时机）

- 受伤相关：`受到伤害` `收到伤害` `受伤后` `damageEnd` `damageAfter` `damageBegin`
- 体力相关：`体力变化` `changeHpAfter` `失去体力` `loseHp` `回复体力` `recoverEnd`
- 用牌相关：`使用牌` `useCard` `useCard1` `useCard2` `respond`
- 阶段相关：`phaseZhunbeiBegin` `phaseDrawBegin` `phaseUseBegin` `phaseJieshuBegin`
- 判定相关：`judge` `judgeEnd`
- 进出牌堆：`loseAfter` `cardsDiscardAfter` `gainAfter`

## 2. 效果词（行为）

- 牌差：`摸牌` `draw` `drawCards` `弃置` `discard` `chooseToDiscard` `获得牌` `gain`
- 生存：`回复` `recover` `减伤` `防止伤害` `免疫`
- 输出：`造成伤害` `damage` `直击` `directHit`
- 控制：`翻面` `横置` `失效` `fengyin`
- 资源：`加标记` `addMark` `蓄力` `charge`
- 能力修正：`maxHandcard` `cardUsable` `targetInRange`

## 3. 技能类型词

- `锁定技` `limited` `限定技` `觉醒技` `juexingji`
- `主公技` `zhuSkill` `使命技` `shimingji`
- `转换技` `zhuanhuanji` `蓄力技`
- `视为技` `viewAs` `chooseToUse`

## 4. 常见限制词

- 次数：`每回合限一次` `usable: 1` `本回合`
- 条件：`若` `否则` `filter` `check` `mod`
- 目标：`一名角色` `其他角色` `全体`
- 距离：`无距离限制` `targetInRange`

## 5. 关键词组合模板

- 受伤摸牌：`受伤后 摸牌 damageEnd draw`
- 受伤加伤：`受到伤害后 下次伤害+1 damageEnd damage`
- 失去体力获益：`失去体力 loseHpAfter 摸牌 draw`
- 用杀触发：`使用杀 useCard sha 摸牌`
- 判定改写：`判定前 judge 替换 黑色牌`
- 主公光环：`主公技 zhuSkill 群势力 杀 无距离`
- 标记成长：`addMark 标记 回合结束 maxHandcard`
- 蓄力机制：`蓄力 charge 体力变化 changeHpAfter`

## 6. 建议命令

```bash
python ../scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route
python ../scripts/search_dataset.py --query "主公技 zhuSkill 群势力 杀 无距离" --top-k 8 --no-multi-route
python ../scripts/search_dataset.py --query "判定前 judge 黑色牌 替换" --top-k 8 --no-multi-route
```
