# 帧流 FrameFlow

一个在本地浏览器中运行的图片转视频工作台。上传首帧图片，填写生成提示词，选择模型，即可通过官方云端 API 创建视频任务，并在本地跟踪、预览和下载结果。

支持：

| 界面名称 | 官方平台 | 默认模型 ID | 图生视频参数 |
| --- | --- | --- | --- |
| Seedance 2.5 | 火山方舟 | `doubao-seedance-2-5-260628` | 4-30 秒，480p / 720p / 1080p |
| Seedance 2.0 | 火山方舟 | `doubao-seedance-2-0-260128` | 4-15 秒，480p / 720p / 1080p / 4k |
| MiniMax H3 | MiniMax 国际开放平台 | `MiniMax-H3` | 4-15 秒，768P / 2K |

本项目不使用第三方模型中转。所有 API Key 仅由本地 Python 服务端读取。网页中的“生成提示词”直接作为视频模型的提示词发送，不会额外调用大语言模型改写。

## 快速启动

### 1. 准备环境

Windows 10/11，Python 3.11 或更新版本。当前已在 Python 3.13 环境开发。

在项目目录打开终端：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

### 2. 启动

```bash
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

也可以双击 `start.bat`。浏览器访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

首次启动时不会自动产生云端费用。只有点击“开始生成视频”并成功提交到官方平台后，才可能产生费用。

### 3. 在页面中配置模型

点击页面右上角的“模型配置”，填写并保存即可立即生效，不需要手动编辑文件或重启服务。

**火山方舟**

1. 在[火山方舟](https://console.volcengine.com/ark)开通 Seedance 模型并创建 API Key。
2. 在模型配置中填写火山方舟 API Key。
3. 默认模型 ID 已填好；如果账号实际可用的 ID 不同，直接在页面中修改。
4. 模型开通、计费或资源包条件以[官方文档](https://console.volcengine.com/ark/region:cn-beijing/docs/ark/create-video-generation-task-api?lang=zh)为准。

**MiniMax H3 和 S3 图片存储**

MiniMax H3 官方接口要求图片 URL。本地图片需先上传到可公开读取的 S3 兼容对象存储，再提交生成的 HTTPS 地址。支持 AWS S3、Cloudflare R2 等服务。

在 [MiniMax 国际开放平台](https://platform.minimax.io)创建 API Key，然后在模型配置中填写：

- MiniMax API Key
- MiniMax 接口地址：国际平台使用 `https://api.minimax.io`，中国内地平台使用 `https://api.minimaxi.com`
- MiniMax H3 模型 ID
- S3 服务端点、区域、存储桶、Access Key、Secret Key、公开访问地址和存储路径

AWS S3 的服务端点可留空，区域填存储桶所在区域。Cloudflare R2 需要设置账户级 S3 endpoint，建议使用绑定存储桶的自定义公开域名。请确认“公开访问地址/对象路径”可以让 MiniMax 直接读取图片。

保存后配置写入 `data/settings.json`，覆盖环境变量中的默认值。页面不会回显已经保存的密钥；密钥输入框留空表示保持原值。环境变量和 `.env.example` 仍可用于高级部署，但不是必需步骤。

**隐私提醒：** 使用 MiniMax 时，图片会被上传到你配置的公开对象存储。清空本地记录不会删除云端图片。建议为该工具使用独立存储桶，并设置生命周期自动删除规则，不要在公开桶中放其他私密文件。API Key 以明文保存在本机 `data/settings.json`，请勿分享该文件。

## 使用说明

1. 选择首帧图片，支持拖放，最大 30 MB。
2. 填写主体动作、镜头运动、环境变化等提示词。
3. 选择模型、时长、清晰度。画幅自动跟随首帧，Seedance 可选同步音频。
4. 点击生成。网页会展示排队、生成中、成功或失败状态。
5. 生成成功后预览视频，点击“下载 MP4”保存。
6. “最近创作”保存在 `data/` 中，刷新页面可恢复。重启服务后会继续查询已经取得云端任务 ID 的任务。

图片要求：

- Seedance：宽、高各 300-6000 像素，宽高比 0.4-2.5，支持 JPG、PNG、WEBP、BMP、TIFF、GIF、HEIC、HEIF。
- MiniMax H3：宽、高各 256-5760 像素，宽高比 0.4-2.5，支持 JPG、PNG、WEBP、HEIC、HEIF。
- HEIC/HEIF 是否能在浏览器中预览取决于浏览器支持；工具已使用 `pillow-heif` 在后端验证格式。
- 真人人脸、内容安全和其他输入限制以平台最新文档为准。请仅上传有权使用的素材。

## 项目结构

```text
app/
  api.py               HTTP 接口
  config.py            运行时配置、页面配置持久化与本地路径
  database.py          SQLite 持久化
  downloads.py         域名限制、私网拦截与视频下载
  main.py              应用入口与生命周期
  models.py            模型能力与任务结构
  schemas.py           参数及图片校验
  storage.py           S3 图片上传
  tasks.py             云端任务轮询和恢复
  providers/           Ark 与 MiniMax 官方 API 适配器
  static/              网页交互与样式
  templates/           单页工作台
tests/                 全部使用模拟云端响应的测试
```

## 运行测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试不会使用 `.env` 中的真实密钥，也不会请求真实模型或产生费用。前端可用浏览器访问本地服务进行测试。

## 故障处理

- **尚未配置 API Key：** 检查 `.env` 文件名、配置项和值，保存后重启服务。
- **模型无权限或模型 ID 不可用：** 在对应平台开通模型，并通过环境变量覆盖为账号实际可用的 ID。
- **MiniMax 提示缺少 S3 配置：** 填齐四个必需项：存储桶、访问密钥、私密密钥和公开地址。
- **MiniMax 无法读取图片：** 在无痕浏览器测试公开图片 URL；检查存储桶权限、公开域名、区域和 HTTPS。
- **视频域名被拦截：** 下载仅允许已知云厂商 HTTPS 域名，并拒绝重定向和私网地址。如果平台实际使用其他 CDN，请确认该域名属于你使用的平台后，将其主域名加入 `DOWNLOAD_HOST_SUFFIXES`，不要设置为任意 URL。
- **网络超时：** 创建任务不会自动重复提交，以避免无幂等键情况下重复生成和扣费。请先检查云端控制台是否已有任务。任务查询会自动重试三次。
- **清空记录：** 会取消本地轮询并删除本地图片、视频和数据库记录，不会取消云端任务，也不会删除 S3 图片或退还费用。
- **不要把服务暴露到公网：** 默认仅监听 `127.0.0.1`，没有用户认证，不适合多人或公网部署。

## 官方资料

- [火山方舟：创建视频生成任务](https://console.volcengine.com/ark/region:cn-beijing/docs/ark/create-video-generation-task-api?lang=zh)
- [火山方舟：查询视频生成任务](https://docs.volcengine.com/docs/82379/1520757)
- [MiniMax：Video Generation](https://platform.minimax.io/docs/guides/video-generation)
- [MiniMax：H3 Prompt Guide](https://platform.minimax.io/docs/guides/video-prompt)
