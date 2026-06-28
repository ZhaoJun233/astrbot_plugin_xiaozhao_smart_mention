# astrbot_plugin_xiaozhao_smart_mention

小昭智能提及与主动回复插件。用于让 AstrBot 在群聊中更自然地判断「什么时候该回复」，避免只要消息里出现某个关键词就机械接话，也支持在没有被点名时根据当前群聊场景谨慎主动回复。

## 功能

- 群聊提到配置的 `mention_keywords` 时，先判断当前消息是不是在叫机器人、问机器人、请求机器人帮忙。
- 对只是旁观讨论、复述、玩笑、明确说不用回复的消息，尽量不打扰。
- 支持普通群聊消息的智能主动回复：只有模型判断小昭此刻自然插话有帮助时才回复。
- 支持短时间续聊：小昭刚回复某人后，同一人不再点名但继续追问时也能自然接上。
- 自动读取 AstrBot 当前群聊上下文，辅助判断当前对话场景。
- 对插件触发的回复追加系统提醒，让小昭自然回应，不解释触发机制，也不特意强调对方是不是主人。
- 默认追加自然群聊风格约束：日常聊天由模型按语气和停顿判断是否拆成短段；列表、步骤、总结、配置说明时收束成紧凑回答；默认关闭括号动作描写和舞台动作输出。
- AstrBot 全局分段关闭时，可由插件调用内部智能模型分析回复，把日常聊天拆成更自然的多条消息发送；结构化、技术、列表和非纯文本回复会保守跳过。
- 插件内部智能模型支持自定义 OpenAI 兼容 URL、API Key 和模型名；未配置或调用失败时自动退回 AstrBot 当前 provider。
- 原生 `@机器人`、回复机器人消息等场景会先经过防刷屏冷却，再交给 AstrBot 默认流程处理。
- 主人 ID 可在插件配置里自定义；仓库默认不写入任何真实用户 ID。

## 适用场景

- 群友提到机器人昵称、别名或自定义关键词，但不一定是在叫机器人。
- 群里有人求助、卡住、邀请大家发表看法，希望小昭可以主动帮一句。
- 想减少机器人抢话、误回复、频繁插话。

不适合用它代替人设、权限或记忆管理；这些应该继续放在 AstrBot 人设配置或其他插件中。

## 安装

### Docker 部署的 AstrBot

进入宿主机项目目录后，将插件放进 AstrBot 数据卷里的插件目录：

```powershell
docker cp .\astrbot_plugin_xiaozhao_smart_mention astrbot:/AstrBot/data/plugins/astrbot_plugin_xiaozhao_smart_mention
docker compose -f .\compose.yml restart astrbot
```

也可以在容器内直接 clone：

```powershell
docker exec astrbot sh -lc "cd /AstrBot/data/plugins && git clone https://github.com/ZhaoJun233/astrbot_plugin_xiaozhao_smart_mention.git"
docker compose -f .\compose.yml restart astrbot
```

### 普通部署

把仓库克隆到 AstrBot 的 `data/plugins` 目录：

```bash
cd /path/to/AstrBot/data/plugins
git clone https://github.com/ZhaoJun233/astrbot_plugin_xiaozhao_smart_mention.git
```

重启 AstrBot 后，在 WebUI 的插件管理中确认插件已启用。

## 推荐 AstrBot 设置

如果使用本插件的主动回复，建议关闭 AstrBot 内置主动回复，避免两个机制同时触发：

```json
"provider_ltm_settings": {
  "active_reply": {
    "enable": false
  }
}
```

本插件只负责“是否让小昭接话”的判断，真正回复内容仍由当前 AstrBot provider、人设和上下文生成。

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `use_llm_judge` | bool | `true` | 规则无法明确判断时，调用当前模型判断是否回复。 |
| `judge_timeout_sec` | int | `8` | 智能判定模型调用超时时间，单位秒。 |
| `custom_ai_enabled` | bool | `false` | 是否启用自定义内部智能模型。开启后，提及判定、主动回复判定、智能分段，以及显式开启的自然改写会优先调用自定义 OpenAI 兼容接口。 |
| `custom_ai_api_base` | string | `""` | 自定义模型 API URL，可填 `https://example.com/v1`，也可填完整 `/chat/completions` 地址。 |
| `custom_ai_api_key` | string | `""` | 自定义模型 API Key。本地代理不需要鉴权时可留空。 |
| `custom_ai_model` | string | `""` | 自定义模型名，会作为 OpenAI 兼容接口的 `model` 字段发送。 |
| `active_reply_enabled` | bool | `true` | 是否启用未被点名时的智能主动回复。 |
| `active_reply_cooldown_sec` | int | `30` | 同一会话内主动回复冷却时间，避免连续抢话。 |
| `natural_chat_style_enabled` | bool | `true` | 是否在插件触发或原生点名回复中追加自然群聊风格约束。日常聊天由模型按语气自行判断是否短段分段，列表、步骤、总结、配置说明时收束成紧凑回答。 |
| `smart_segment_enabled` | bool | `true` | AstrBot 全局分段关闭时，是否由插件接管日常聊天回复的自然分段发送。 |
| `smart_segment_use_model` | bool | `true` | 是否调用内部智能模型分析自然分段；已配置自定义内部模型时优先使用自定义接口，否则使用当前会话模型，失败、超时或返回不合规时退回本地分段。 |
| `smart_segment_model_timeout_sec` | float | `2.0` | 智能分段模型最多等待秒数，超时后直接走本地分段，避免回复明显变慢。 |
| `natural_rewrite_use_model` | bool | `false` | 是否在回复生成后额外调用一次内部智能模型做自然化整理。默认关闭，只用本地规则清理动作描写、标题和基础分段；开启后效果更细，但会增加一次模型等待。 |
| `natural_rewrite_timeout_sec` | float | `1.2` | 自然改写模型最多等待秒数，仅在 `natural_rewrite_use_model=true` 时生效。 |
| `smart_segment_respect_astrbot` | bool | `true` | AstrBot 自带分段已启用时，插件是否避让以免重复分段。 |
| `smart_segment_interval_sec` | float | `0.8` | 插件接管分段发送时，多条消息之间的基础间隔秒数。 |
| `action_output_enabled` | bool | `false` | 是否允许括号动作描写、舞台旁白以及耳朵/尾巴/爪爪等动作输出；默认关闭。 |
| `natural_chat_max_sentences` | int | `3` | 自然分段安全上限。模型自行判断分成几条，此项只限制最多短段/短句数量，避免刷屏。 |
| `followup_reply_window_sec` | int | `180` | 小昭刚回复某人后，同一群同一人未点名但继续追问时的续聊窗口；设为 `0` 可关闭。 |
| `active_judge_attempt_cooldown_sec` | int | `45` | 无关键词主动回复判定尝试冷却时间；无论最后是否回复，都避免每条普通消息都请求模型判定。 |
| `judge_failure_backoff_sec` | int | `120` | 智能判定模型超时、429 或其他失败后的熔断时间；熔断期间跳过智能判定，但不会拦截明确的规则点名回复。 |
| `directed_reply_guard_enabled` | bool | `true` | 是否启用原生 `@机器人`、回复机器人消息、文字点名机器人的防刷屏冷却。 |
| `directed_reply_group_cooldown_sec` | int | `8` | 同一群聊内点名机器人的全局冷却时间。 |
| `directed_reply_sender_cooldown_sec` | int | `60` | 同一群聊内同一发送者点名机器人的冷却时间。 |
| `directed_reply_owner_bypass` | bool | `true` | 主人是否绕过点名防刷屏冷却。 |
| `owner_ids` | list | `[]` | 主人用户 ID 列表。仓库默认留空，请在本机配置里填写真实平台用户 ID。 |
| `mention_keywords` | list | `["小昭", "小昭猫娘"]` | 群聊提及时用于进入智能提及判断的关键词，可改成任意机器人昵称、别名或唤醒称呼。 |
| `aliases` | list | `["小昭", "小昭猫娘"]` | 旧版兼容项；新配置请优先使用 `mention_keywords`。 |
| `followup_reply_cue_patterns` | list | 见配置文件 | 续聊窗口内判断同一人未点名消息是否像追问、纠正或要求继续回答的规则。 |

配置修改后重启 AstrBot，或在 AstrBot 插件管理中重新加载插件。

例如想让“小昭”“小昭猫娘”“bot”都能进入智能提及判断，可以配置：

```json
"mention_keywords": ["小昭", "小昭猫娘", "bot"]
```

如果希望某些主人账号不受连续 `@机器人` 防刷屏冷却影响，可以配置：

```json
"owner_ids": ["<your_user_id>"]
```

如果希望插件的智能判断和自然分段使用单独模型，可以配置 OpenAI 兼容接口：

```json
"custom_ai_enabled": true,
"custom_ai_api_base": "https://api.example.com/v1",
"custom_ai_api_key": "<your_api_key>",
"custom_ai_model": "your-model-name"
```

`custom_ai_api_base` 也可以直接填完整的 `https://api.example.com/v1/chat/completions`。请不要把真实 Key 提交到仓库。

## 回复策略

### 提到关键词时

插件只处理群消息，并且消息文本里必须包含 `mention_keywords` 配置的任一关键词。命中后按下面顺序判断：

1. 明确“不用回复”“别理”等跳过表达，选择不回复。
2. 明确叫机器人、问机器人、请求机器人帮忙，选择回复。
3. 规则不确定时，如果 `use_llm_judge=true`，调用内部智能模型只输出 `REPLY` 或 `SKIP`；配置了自定义内部模型时优先走自定义接口，否则使用当前 provider。
4. 判定为 `REPLY` 时，把本轮消息标记为唤醒消息，交给 AstrBot 正常 LLM 流程生成回复。

如果 `natural_chat_style_enabled=true`，插件会在本轮 LLM 请求里追加一段稳定的系统提醒：按实时群聊自然对话回复，日常聊天由模型按语气、停顿和信息密度自行判断是否拆成短段；`natural_chat_max_sentences` 只作为安全上限，避免刷屏。列表、步骤、总结、配置说明时收束成一段紧凑的结构化回答，并且不要每句都抢答。`action_output_enabled=false` 时，插件还会在 LLM 回复后用本地规则兜底清理常见括号动作描写、日常聊天标题和基础短段格式，原生 @/引用机器人触发的群聊回复也会受这个开关影响。默认不会为了自然化整理再额外调用一次模型；只有 `natural_rewrite_use_model=true` 时才会启用模型自然改写。

如果 AstrBot 自带分段回复关闭，且 `smart_segment_enabled=true`，插件会在发送前对纯文本模型回复做一次分段判断：优先让内部智能模型输出 JSON 段落，段落数量由模型按自然语气决定，再把这些段落逐条发送；模型不可用、超时或返回不合规时退回本地自然分段。为避免破坏信息密度，含代码、路径、配置、日志、列表、图片、文件等内容不会被插件强行拆开。AstrBot 自带分段已开启时，默认由 `smart_segment_respect_astrbot=true` 让插件避让框架分段。

### 主动回复时

插件监听普通群聊消息，但会跳过以下情况：

- 插件未启用主动回复。
- 消息已经是 `@机器人`、回复机器人、唤醒命令。
- 消息来自机器人自己。
- 消息为空。
- 消息已经提到了配置关键词，避免和“提及判断”重复。
- 同一会话还在冷却时间内。
- 同一会话还在主动判定尝试冷却时间内。
- 最近一次智能判定超时、429 或失败后仍在熔断时间内。
- 当前消息不像提问、求助、配置讨论或需要补充意见的场景。

模型只在认为机器人自然插话有帮助时返回 `REPLY`。例如有人提出开放问题、求助、讨论卡住、需要总结或配置帮助。普通闲聊、短表情、刷屏、两人正在私下对话时应返回 `SKIP`。

主动回复生成内容时还会额外强调“轻量接话、不抢话”，让它更像群聊里顺手补一句，而不是把每条消息都当成正式问答。

### 续聊窗口

当小昭刚刚回复过某个发送者后，插件会记录这个“当前对话目标”。在 `followup_reply_window_sec` 秒内，如果同一群、同一机器人、同一发送者继续发出像追问、纠正、要求直接回答的消息，即使没有再次提到 `mention_keywords`，插件也会接着回复。

该机制只对同一发送者生效，别人插话不会继承这个窗口；普通闲聊也不会仅因为窗口存在而触发。续聊在主动回复或续聊回复之后也会尊重 `active_reply_cooldown_sec`，避免同一段无关键词对话被一句一句接管；明确点名仍走点名逻辑。如果觉得续聊太积极，可以把 `followup_reply_window_sec` 调小，或设为 `0` 关闭。

### 点名机器人时

当群聊消息原生 `@机器人`、`@全体`、回复机器人消息，或文字里明确点名触发关键词并提问/求助时，插件会先检查防刷屏冷却：

1. 如果 `directed_reply_guard_enabled=false`，不做限制。
2. 如果发送者在 `owner_ids` 中且 `directed_reply_owner_bypass=true`，不做限制。
3. 同一群聊在 `directed_reply_group_cooldown_sec` 秒内已经允许过一次点名回复时，后续点名会被静默拦截。
4. 同一发送者在 `directed_reply_sender_cooldown_sec` 秒内已经允许过一次点名回复时，后续点名会被静默拦截。

被拦截的消息不会进入模型调用，也不会让机器人每条都回复。

## 与小昭人设配合

本插件不会修改人设，只会决定是否触发回复。建议在人设中单独写清：

- 机器人名字、性格和说话风格。
- 谁是主人。
- 不要对非主人反复强调“你不是主人”。
- 群聊中按当前消息的发送人 ID 判断身份，不把多个人的发言混成同一个人。

## 日志

插件加载成功时可以在 AstrBot 日志中看到：

```text
[xiaozhao_smart_mention] loaded
```

常见运行日志：

```text
[xiaozhao_smart_mention] reply
[xiaozhao_smart_mention] skip
[xiaozhao_smart_mention] active reply
[xiaozhao_smart_mention] smart segmented send
```

这些日志可以用来确认插件是否正确判定了回复或跳过。

## 排障

### 提到关键词没有回复

- 确认消息在群聊中，私聊不会被本插件处理。
- 确认 `mention_keywords` 中包含实际使用的名字；旧配置也可以继续使用 `aliases`。
- 查看日志里是否出现 `skip`。
- 如果规则不够，可开启 `use_llm_judge`。
- 确认自定义内部模型配置可用；未启用自定义模型时，确认 AstrBot 当前 provider 可用，否则 LLM 判定会失败。

### 小昭主动回复太频繁

- 增大 `active_reply_cooldown_sec`。
- 调小或关闭 `followup_reply_window_sec`，减少同一人未点名续聊。
- 增大 `active_judge_attempt_cooldown_sec`，减少普通消息触发判定模型的频率。
- 关闭 `active_reply_enabled`，只保留提及判断。
- 确认 AstrBot 内置主动回复已关闭，避免重复机制。

### 出现 429 或 active judge failed

- `429 Too many requests` 表示当前 provider 限流；插件会在 `judge_failure_backoff_sec` 秒内跳过后续智能判定。
- `active judge failed: TimeoutError` 表示主动回复判定超时；插件同样会进入短暂熔断。
- 如果仍然频繁出现，增大 `active_judge_attempt_cooldown_sec` 或暂时关闭 `active_reply_enabled`。

### 连续 @ 机器人仍然每条都回复

- 确认 `directed_reply_guard_enabled=true`。
- 增大 `directed_reply_group_cooldown_sec` 或 `directed_reply_sender_cooldown_sec`。
- 确认刷屏账号没有被填进 `owner_ids`。
- 修改配置后重启 AstrBot，或在插件管理里重新加载插件。

### 小昭完全不主动回复

- 确认 `active_reply_enabled=true`。
- 确认当前群聊有可用 provider。
- 主动回复策略默认偏保守，这是为了减少抢话。

## 更新

```bash
cd /path/to/AstrBot/data/plugins/astrbot_plugin_xiaozhao_smart_mention
git pull
```

Docker 部署更新后重启 AstrBot：

```powershell
docker compose -f .\compose.yml restart astrbot
```
