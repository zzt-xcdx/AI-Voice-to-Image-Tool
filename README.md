# Voice2Canvas（语音绘图 Demo）

训练营 3 天考核脚手架。语音 → ASR → LLM 解析为绘图命令 → 前端 Canvas 执行，全程语音操作（撤销/清空/保存）。

## 目录结构
```
QINIU/
├── backend/                 # 后端（FastAPI）
│   ├── requirements.txt
│   └── app/
│       ├── main.py          # 入口，挂载 frontend
│       ├── config.py        # 读取 .env
│       ├── paths.py         # 路径常量
│       ├── routers/         # API 路由（health, voice）
│       └── services/        # LLM
├── frontend/                # 前端（Canvas + 录音）
├── prompts/                 # Prompt 模板
├── scripts/                 # 工具脚本
├── run.py                   # 一键启动
├── .env.example             # 环境变量模板
└── README.md
```

## 快速开始
```bash
python -m venv .venv
.venv\Scripts\activate

pip install -r backend/requirements.txt

copy .env.example .env
# 编辑 .env，填入 LLM/ASR 的 key

python scripts/test_apis.py
python run.py
```
- 演示页：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs

## 环境变量
- LLM：`LLM_API_KEY` `LLM_BASE_URL` `LLM_MODEL`（任意可用通用模型即可）
- ASR（默认 baidu_rest，支持 xfyun）：
  - 百度 REST：`ASR_VENDOR=baidu_rest`，`BAIDU_API_KEY` `BAIDU_SECRET_KEY` `BAIDU_DEV_PID` `BAIDU_CUID`
  - 讯飞流式：`ASR_VENDOR=xfyun`，`XFYUN_APPID` `XFYUN_APIKEY` `XFYUN_APISECRET`
  - `FFMPEG_BIN`：录音已是 16k WAV，ffmpeg 仅兜底，不在 PATH 时填绝对路径

## 当前能力
- 语音上传（16k WAV）→ ASR → LLM 解析命令 JSON
- 前端录音、Canvas 绘制，支持撤销/清空/保存
- 仅文本回复（已关闭语音播报）

## 主要文件
- 后端：`backend/app/routers/voice.py`（/api/asr-nlu）、`backend/app/main.py`
- Prompt：`prompts/voice_drawing.md`
- 前端：`frontend/index.html`
- 配置：`.env.example`

## 题目对照
- 语音绘图：`routers/voice.py` + `prompts/voice_drawing.md` + 前端 Canvas
