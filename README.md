# 微信机器人

本项目是运行在 Windows 本地的微信机器人原型，当前已支持：

- 只读读取微信 4.x 加密数据库；
- 增量消息监听与游标持久化；
- DeepSeek 文本回复生成；
- 人工确认队列；
- 通过参考项目的 UI 适配器发送文本。

当前默认是人工确认模式，不会自动发送消息。

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
- `WX_BOT_WATERMARK_FILE`：游标文件路径。

## 启动

```powershell
python -m app.main
```

控制台命令：

- `list`：查看待确认回复；
- `approve <token>`：确认并发送；
- `reject <token>`：丢弃回复；
- `quit`：停止程序。

首次使用建议先在测试会话中验证。数据库读取、AI 生成和 UI 发送均可能受微信版本、桌面锁定状态和本地权限影响。

## 安全边界

- 不修改微信原始数据库；
- 不实现批量群发、自动加好友或自动拉群；
- 默认不保存完整聊天正文；
- API Key 仅通过环境变量读取；
- AI 回复不会自动发送，必须人工批准。
