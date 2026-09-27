# 微信机器人

本项目是运行在 Windows 本地的微信机器人原型，当前已支持：

- 只读读取微信 4.x 加密数据库；
- 增量消息监听与游标持久化；
- DeepSeek 文本回复生成；
- Open-Meteo 实时天气查询；
- Firecrawl 通用联网搜索；
- 人工确认队列；
- 通过参考项目的 UI 适配器发送文本。

当前默认是自动回复模式；可设置 `WX_BOT_SEND_MODE=manual` 切换为人工确认。

天气问题会直接调用 Open-Meteo 查询，不需要额外 API Key。例如：

```text
今天宁波天气如何
北京现在会下雨吗
```

明确要求搜索或涉及最新资讯、新闻、官网、价格、汇率等时效信息时，机器人会先联网搜索，再交给 DeepSeek 组织回答。日常聊天和稳定知识问题不依赖联网搜索。通用联网搜索需要配置 `FIRECRAWL_API_KEY`。例如：

```text
请搜索最新的宁波新闻
帮我查一下这个产品的官网
```

未配置搜索 Key 时，只有需要当前信息的问题会明确提示联网搜索不可用，不会编造搜索结果；普通聊天仍可正常回答。

## 环境要求

- Windows 10/11；
- 64 位 Python 3.9+；
- 微信已登录并保持运行；
- 首个验证版本：微信 `4.1.13.12`。

## 安装

```powershell
python -m pip install -r requirements.txt
```

复制 `.env.example` 为本地环境配置，填写 DeepSeek Key。不要把真实 Key 写入 Git 或发送到聊天中。

可选配置：

- `WECHAT_ACCOUNT`：指定微信账号目录名；
- `DEEPSEEK_MODEL`：DeepSeek 模型名；
- `WX_BOT_POLL_INTERVAL`：消息轮询间隔，默认 1 秒；
- `WX_BOT_USER_REFRESH_INTERVAL`：重新发现新会话的间隔，默认 30 秒；
- `WX_BOT_WATERMARK_FILE`：游标文件路径。
- `WX_BOT_SEND_MODE`：`auto` 自动回复，或 `manual` 人工确认，默认 `auto`。
- `WX_BOT_FALLBACK_REPLY`：AI 请求失败时的兜底回复文本。
- `WX_BOT_CONTEXT_MESSAGES`：每个用户保留的最近上下文消息数，默认 20；
- `WX_BOT_CONTEXT_FILE`：按用户 ID 保存上下文的 JSON 文件路径。
- `WX_BOT_KNOWLEDGE_DIR`：本地知识文档目录，默认项目下的 `knowledge/`。
- `WX_BOT_KNOWLEDGE_DB`：知识库索引文件路径，默认 `%LOCALAPPDATA%\wx-bot\knowledge.sqlite`。
- `WX_BOT_SUMMARY_MESSAGES`：群聊总结读取的最近文本消息数，默认 50。
- `WX_BOT_PROMPT_FILE`：AI 系统提示词文档路径，默认 `prompts/assistant_system.md`。
- `WX_BOT_SCHEDULE_FILE`：定时发送任务 JSON 文件路径。
- `WX_BOT_GROUP_NAMES`：机器人在群里的昵称，多个昵称用英文逗号分隔。

## 启动

```powershell
python -m app.main
```

控制台命令：

- `list`：查看待确认回复；
- `approve <token>`：确认并发送；
- `reject <token>`：丢弃回复；
- `quit`：停止程序。

定时发送命令：

- 在微信中向机器人发送 `/定时 <ISO时间> <内容>`，创建给自己的单次任务；
- 在微信中向机器人发送 `/每 <秒数> <内容>`，创建给自己的周期任务；
- `schedule once <用户ID> <ISO时间> <内容>`：创建一次性任务；
- `schedule every <用户ID> <秒数> <内容>`：创建周期任务；
- `schedules`：查看任务；
- `cancel <任务ID>`：取消任务。

微信命令示例：

```text
/定时 2026-08-30T20:30:00+08:00 晚上好
/定时 21:40发送你好
/定时 21:40 发送你好
/每 86400 早上好
```

群聊总结：

```text
@机器人 总结最近群聊
```

隐私命令：

```text
/清除上下文
```

该命令只清除发起者自己的本地对话上下文，不影响其他用户。

`HH:MM` 和不带时区的 ISO 时间按本机时区执行；带时区的 ISO 时间按其明确时区执行。任务内部统一转换为 UTC 保存；如果当天的 `HH:MM` 已经过期，则自动安排到次日。

微信内创建的任务只能发送给命令发起者本人；控制台命令可用于管理员维护已存在的任务。

首次使用建议先在测试会话中验证。数据库读取、AI 生成和 UI 发送均可能受微信版本、桌面锁定状态和本地权限影响。

## 安全边界

- 不修改微信原始数据库；
- 不实现批量群发、自动加好友或自动拉群；
- 默认不保存完整聊天正文；
- API Key 仅通过环境变量读取；
- 自动模式仅处理监听会话收到的新消息，不处理机器人自己发送的消息。
- 群聊仅处理明确 @ 机器人昵称或 `@我` 的消息，普通群消息不会触发回复。
- 群聊回复使用普通文本发送，不使用引用回复。
- 对授权用户的群聊 @ 消息，若 @ 后紧跟 `，` 或 `,`，直接复述逗号后的内容；否则交给 AI 生成回复。
- 手动模式下，AI 回复必须执行 `approve <token>` 才会发送。
- 上下文按用户 ID 隔离保存，默认保存在本机 `contexts.json`，不提交到 Git。
