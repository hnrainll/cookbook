# 饭否的飞书机器人

通过飞书机器人向饭否发送消息。

## 功能特点

- 支持通过飞书机器人接收消息
- 支持将消息转发到饭否平台
- 使用环境变量进行配置管理

## 安装依赖

```bash
uv sync
```

## 配置说明

1. 创建 `.env` 文件并配置以下环境变量：

```
# 飞书机器人配置
BASE_DOMAIN=https://open.feishu.cn
APP_ID=your_app_id
APP_SECRET=your_app_secret

# 饭否API配置
FANFOU_CONSUMER_KEY=your_consumer_key
FANFOU_CONSUMER_SECRET=your_consumer_secret
FANFOU_OAUTH_CALLBACK=your_oauth_callback
```

2. 创建飞书机器人
   - 在飞书开放平台创建机器人
   - 使用长链接的形式交互

3. 获取饭否 API 密钥：
   - 在饭否开放平台注册应用（饭否已经不审核新注册应用，故申请的应用也无法使用）
   - 获取 Consumer Key 和 Consumer Secret
   - 获取 Access Token 和 Access Token Secret

## 使用方法

运行主程序：

```bash
# 本地测试
uv run uvicorn fanshu.main:app --host 0.0.0.0 --port 8009 --reload --reload-dir .

# 后台运行
nohup gunicorn fanshu.main:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8009 >> fanshu.log 2>&1 &
```

## 注意事项

- 请确保所有必要的环境变量都已正确配置
- 保护好你的 API 密钥和令牌，不要泄露给他人
- 建议将 `.env` 文件添加到 `.gitignore` 中 

## 感谢
- [https://github.com/LitoMore/fanfou-sdk-python](https://github.com/LitoMore/fanfou-sdk-python)
- [https://github.com/fanfoujs/nofan](https://github.com/fanfoujs/nofan)