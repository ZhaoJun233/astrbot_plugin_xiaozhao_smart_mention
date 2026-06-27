# astrbot_plugin_xiaozhao_smart_mention

小昭智能提及与主动回复插件。用于让 AstrBot 在群聊中更自然地判断「什么时候该回复」，避免只要消息里出现某个关键词就机械接话，也支持在没有被点名时根据当前群聊场景谨慎主动回复。

## 功能

- 群聊提到配置的 `mention_keywords` 时，先判断当前消息是不是在叫机器人、问机器人、请求机器人帮忙。
- 对只是旁观讨论、复述、玩笑、明确说不用回复的消息，尽量不打扰。
- 支持普通群聊消息的智能主动回复：只有模型判断小昭此刻自然插话有帮助时才回复。
- 自动读取 AstrBot 当前群聊上下文，辅助判断当前对话场景。
- 对插件触发的回复追加系统提醒，让小昭自然回应，不解释触发机制，也不特意强调对方是不是主人。
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
| `active_reply_enabled` | bool | `true` | 是否启用未被点名时的智能主动回复。 |
| `active_reply_cooldown_sec` | int | `30` | 同一会话内主动回复冷却时间，避免连续抢话。 |
| `active_judge_attempt_cooldown_sec` | int | `45` | 主动回复判定尝试冷却时间；无论最后是否回复，都避免每条普通消息都请求模型判定。 |
| `judge_failure_backoff_sec` | int | `120` | 智能判定模型超时、429 或其他失败后的熔断时间；熔断期间跳过智能判定。 |
| `directed_reply_guard_enabled` | bool | `true` | 是否启用原生 `@机器人`、回复机器人消息的防刷屏冷却。 |
| `directed_reply_group_cooldown_sec` | int | `8` | 同一群聊内原生点名机器人的全局冷却时间。 |
| `directed_reply_sender_cooldown_sec` | int | `60` | 同一群聊内同一发送者原生点名机器人的冷却时间。 |
| `directed_reply_owner_bypass` | bool | `true` | 主人是否绕过原生点名防刷屏冷却。 |
| `owner_ids` | list | `[]` | 主人用户 ID 列表。仓库默认留空，请在本机配置里填写真实平台用户 ID。 |
| `mention_keywords` | list | `["小昭", "小昭猫娘"]` | 群聊提及时用于进入智能提及判断的关键词，可改成任意机器人昵称、别名或唤醒称呼。 |
| `aliases` | list | `["小昭", "小昭猫娘"]` | 旧版兼容项；新配置请优先使用 `mention_keywords`。 |

配置修改后重启 AstrBot，或在 AstrBot 插件管理中重新加载插件。

例如想让“赵小昭”“小赵”“bot”都能进入智能提及判断，可以配置：

```json
"mention_keywords": ["赵小昭", "小赵", "bot"]
```

如果希望某些主人账号不受连续 `@机器人` 防刷屏冷却影响，可以配置：

```json
"owner_ids": ["<your_user_id>"]
```

## 回复策略

### 提到关键词时

插件只处理群消息，并且消息文本里必须包含 `mention_keywords` 配置的任一关键词。命中后按下面顺序判断：

1. 明确“不用回复”“别理”等跳过表达，选择不回复。
2. 明确叫机器人、问机器人、请求机器人帮忙，选择回复。
3. 规则不确定时，如果 `use_llm_judge=true`，调用当前模型只输出 `REPLY` 或 `SKIP`。
4. 判定为 `REPLY` 时，把本轮消息标记为唤醒消息，交给 AstrBot 正常 LLM 流程生成回复。

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

模型只在认为机器人自然插话有帮助时返回 `REPLY`。例如有人提出开放问题、求助、讨论卡住、需要总结或配置帮助。普通闲聊、短表情、刷屏、两人正在私下对话时应返回 `SKIP`。

### 原生 @ 或回复机器人时

当群聊消息原生 `@机器人`、`@全体` 或回复机器人消息时，插件会先检查防刷屏冷却：

1. 如果 `directed_reply_guard_enabled=false`，不做限制。
2. 如果发送者在 `owner_ids` 中且 `directed_reply_owner_bypass=true`，不做限制。
3. 同一群聊在 `directed_reply_group_cooldown_sec` 秒内已经允许过一次原生点名回复时，后续点名会被静默拦截。
4. 同一发送者在 `directed_reply_sender_cooldown_sec` 秒内已经允许过一次原生点名回复时，后续点名会被静默拦截。

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
```

这些日志可以用来确认插件是否正确判定了回复或跳过。

## 排障

### 提到关键词没有回复

- 确认消息在群聊中，私聊不会被本插件处理。
- 确认 `mention_keywords` 中包含实际使用的名字；旧配置也可以继续使用 `aliases`。
- 查看日志里是否出现 `skip`。
- 如果规则不够，可开启 `use_llm_judge`。
- 确认 AstrBot 当前 provider 可用，否则 LLM 判定会失败。

### 小昭主动回复太频繁

- 增大 `active_reply_cooldown_sec`。
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
