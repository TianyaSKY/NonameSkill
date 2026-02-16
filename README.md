# NonameSkill

基于《无名杀扩展开发教程》的 Codex Skill，提供教程检索与技能实现辅助。  
当前版本为精简模式：仅使用 SQLite 数据集与 `search_dataset.py` 检索脚本。

## 功能

- 教程章节路由：按任务定位到对应文档章节。
- 关键词检索：将技能需求映射为关键词并检索实现样例。
- 多路改写检索：支持规则改写与 LLM 改写后再检索。
- 双数据源：支持 `skill`（技能）与 `card`（卡牌）两套 SQLite 数据。

## 目录结构

```text
NonameSkill/
  SKILL.md
  README.md
  agents/openai.yaml
  assets/
    dataset.sqlite3
    card_code_effect_dataset.sqlite3
  references/
    chapter-map.md
    search-keywords.md
    tutorial/...
  scripts/
    search_dataset.py
```

## 环境要求

- Python 3.10+
- SQLite3（Python 内置 `sqlite3` 即可）

## 安装

将本目录放入 Codex skills 目录（示例）：

```powershell
Copy-Item -Recurse -Force .\NonameSkill "$env:USERPROFILE\.codex\skills\NonameSkill"
```

或直接将本仓库作为技能目录使用。

## 使用

在技能目录下执行：

```bash
python scripts/search_dataset.py --query "受伤后 摸牌 damageEnd draw" --top-k 8 --no-multi-route
```

### 常用示例

- 技能数据集检索：

```bash
python scripts/search_dataset.py --dataset-kind skill --query "锁定技 体力变化 蓄力" --top-k 5
```

- 卡牌数据集检索：

```bash
python scripts/search_dataset.py --dataset-kind card --query "濒死 回复体力" --top-k 5
```

- 启用多路改写并显示路由：

```bash
python scripts/search_dataset.py --query "做一个收到伤害摸牌的技能" --top-k 8 --show-routes --candidate-pool 800 --min-score 12
```

## LLM 改写（可选）

默认 `rewrite-mode=auto`，若配置了 OpenAI Key 会优先使用 LLM 改写，否则回退规则改写。

```powershell
$env:OPENAI_API_KEY="your_key"
python scripts/search_dataset.py --query "做一个受到伤害摸牌的技能" --rewrite-mode auto --show-routes
```

可选参数：

- `--llm-model`（默认 `gpt-4.1-mini`）
- `--llm-base-url`（默认 `https://api.openai.com/v1`）
- `--llm-timeout`
- `--llm-api-key`

## 说明

- 本项目已移除 `jsonl` 读写流程，仅保留 SQLite 检索链路。
- 维护脚本（索引构建/格式校验）已移除，当前定位为“即插即用检索版”。

## 许可证

请按你的仓库策略补充许可证信息。
