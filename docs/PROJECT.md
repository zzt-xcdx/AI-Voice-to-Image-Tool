# AI 语音绘图工具 — 项目文档

> Voice2Canvas：纯语音驱动的 AI 生图与图表生成 Demo。  
> 对应训练营题目：**AI 语音绘图工具**。

---

## 1. 项目简介

用户通过**语音**描述需求，系统完成：

- **AI 画图**：口语 → LLM 润色英文提示词 → 千帆 API 生图
- **图表生成**：口语 → LLM 输出结构化 JSON → 前端 ECharts 渲染（饼图 / 柱状图 / 折线图）

全程支持语音导航、开关麦、历史保存、导出与 TTS 状态播报，无需依赖鼠标键盘完成主流程演示。

---

## 2. 功能一览

| 模块 | 能力 |
|------|------|
| 主页导航 | 语音进入 AI 画图 / 图表 / 画板库，展开菜单 |
| AI 生图 | VAD 自动分段录音，百度 ASR + LLM + 千帆生图 |
| 图表 | 同上链路，输出 `ChartSpec` JSON 并 ECharts 渲染 |
| 画板库 | SQLite 历史记录，列表/详情/删除；生图后自动入库 |
| 语音开关 | 识别常开；关麦时仅响应「开启语音」；开麦时「关闭语音」最高优先级 |
| 多轮润色 | 支持 `prior_prompt`，在连续口令基础上迭代提示词 |
| 防误触 | 生成锁、3 秒静音收口、提交后 3 秒冷却、返回主菜单不触发生成 |
| 导出 | 语音/按钮「保存到桌面」，记录 `exported` 标记 |

---

## 3. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  浏览器（frontend-react/dist/*.html）                        │
│  Web Speech 实时预览 + VAD + MediaRecorder                   │
│  关麦/开麦指令过滤 + 状态机 + TTS                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST multipart/form-data
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI（backend/app）                                      │
│  describe.py  → ASR → LLM →（image）千帆生图                 │
│  drawings.py  → SQLite CRUD / 导出标记                       │
│  voice.py     → 百度/讯飞 ASR、JSON 清理                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   百度/讯飞 ASR      DeepSeek 等 LLM    千帆图像 API
         │                 │                 │
         └─────────────────┴─────────────────┘
                           ▼
                    data/drawings.db
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+、FastAPI、httpx、pydantic、SQLite |
| 前端 | 静态 HTML、Tailwind CDN、ECharts、Web Speech API、MediaRecorder |
| AI | LLM（OpenAI 兼容 API）、百度短语音 ASR、千帆文生图 |
| 音频 | 系统 `ffmpeg`（webm → 16k PCM 供 ASR） |

---

## 4. 目录结构

```
QINIU/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口，挂载 frontend-react/dist
│   │   ├── config.py         # .env 配置
│   │   ├── paths.py          # 根目录、数据库、前端 dist 路径
│   │   ├── routers/
│   │   │   ├── describe.py   # 核心：语音描述 → LLM → 图/表
│   │   │   ├── drawings.py   # 画板库 CRUD、导出
│   │   │   ├── voice.py      # ASR、旧版画布 NLU（/api/asr-nlu）
│   │   │   └── health.py     # 健康检查
│   │   └── services/
│   │       └── llm.py        # LLM 统一调用
│   └── requirements.txt
├── frontend-react/
│   └── dist/                 # 当前使用的前端（无需构建即可运行）
│       ├── index.html        # 主页语音导航
│       ├── image.html        # AI 生图
│       ├── chart.html        # 图表
│       └── drawings.html     # 画板库独立页
├── frontend/                 # 旧版画布绘图页（/api/asr-nlu）
├── prompts/
│   └── voice_drawing.md      # LLM 系统提示词（image/chart 双模式）
├── data/
│   └── drawings.db           # SQLite（运行时生成）
├── docs/
│   ├── PROJECT.md            # 本文档
│   └── PRESENTATION.md       # 答辩/演示讲稿
├── scripts/                  # API 连通性测试脚本
├── .env.example
├── run.py                    # 一键启动
└── README.md
```

---

## 5. 环境配置

复制 `.env.example` 为 `.env`，填写以下变量：

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | 是 | LLM API Key（DeepSeek / 通义等 OpenAI 兼容） |
| `LLM_BASE_URL` | 是 | 如 `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 是 | 如 `deepseek-chat` |
| `IMAGE_API_KEY` | 生图必填 | 千帆图像 API Bearer Token |
| `IMAGE_MODEL` | 否 | 默认 `qwen-image` |
| `ASR_VENDOR` | 否 | `baidu` 或 `xfyun` |
| `BAIDU_API_KEY` / `BAIDU_SECRET_KEY` | ASR 必填 | 百度短语音 REST |
| `BAIDU_DEV_PID` | 否 | 默认 `1537`（普通话） |
| `DB_PATH` | 否 | 默认 `data/drawings.db` |
| `APP_HOST` / `APP_PORT` | 否 | 默认 `0.0.0.0:8000` |

**系统依赖**：本机需安装 `ffmpeg`（ASR 转码用），并加入 PATH。

---

## 6. 安装与运行

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. 安装依赖
pip install -r backend/requirements.txt

# 3. 配置环境变量
copy .env.example .env          # Windows
# cp .env.example .env

# 4. 启动（项目根目录）
python run.py
```

浏览器访问：**http://localhost:8000/**  
建议使用 **Chrome / Edge**，并允许麦克风权限。

---

## 7. 页面说明

| 路径 | 文件 | 作用 |
|------|------|------|
| `/` | `index.html` | 主页；语音导航到各功能；说「画板」进入画板库 |
| `/image.html` | `image.html` | AI 生图；VAD + 双 ASR + 千帆出图 |
| `/chart.html` | `chart.html` | 图表生成；ECharts 渲染 |
| `/drawings.html` | `drawings.html` | 画板库列表、详情、删除 |
| `/api/health` | — | 服务健康检查 |

---

## 8. 语音交互设计

### 8.1 识别常开 + 开关麦

- 进入页面后**自动开麦**（`voiceManualEnabled = true`）
- 底层 **Web Speech 识别持续运行**，关麦不会销毁音频管线
- **关麦时**：仅识别 **「开启语音」**（兼容「打开语音」），其余忽略
- **开麦时**：**「关闭语音」**（兼容「关掉语音」）**最高优先级**，听到立即关麦
- 悬浮球可手动 On / Off，与语音指令等价

### 8.2 双 ASR 策略（生图/图表页）

| 引擎 | 用途 |
|------|------|
| Web Speech API | 实时预览（`#live` 区域）、开关麦指令 |
| MediaRecorder + 百度 ASR | 正式提交给后端的音频识别 |

静音 **3 秒**且说话不少于 **0.8 秒**后，才收口上传音频。

### 8.3 防重复提交

- `generatingLock`：上一张图/表生成完成前，不接受新的生成请求
- 完成后 **3 秒冷却**再接受下一句语音

### 8.4 语音指令表

**主页（index.html）**

| 口令 | 效果 |
|------|------|
| AI 画图 / 生图 | 跳转 `/image.html` |
| 图表 / 图表功能 | 跳转 `/chart.html` |
| 画板 / 画板功能 | 跳转 `/drawings.html` |
| 展开菜单 | 展开主菜单 |
| 关闭语音 | 关麦 |
| 开启语音 | 开麦 |

**生图/图表页（image.html / chart.html）**

| 口令 | 效果 |
|------|------|
| 关闭语音 | 立即关麦（最高优先级） |
| 开启语音 | 恢复开麦 |
| 返回主菜单 / 回首页 / 退出 | 回主页，不触发生成 |
| 下载到桌面 / 保存到桌面 | 导出当前结果 |
| 刷新 | 刷新画板列表 |
| 加载第 N 条 / 打开第 N 条 | 加载历史第 N 条 |
| 删除第 N 条 | 删除历史第 N 条 |
| 重试 | 重试上一条生成请求 |

**图表页语音示例**（详见 `chart.html` 底部「语音示例文案」）

- 饼图：「帮我画一个饼图，标题叫水果销量占比，苹果百分之六十……」
- 柱状图 / 折线图 / 多系列柱状图等完整示例见页面

---

## 9. 业务流程

### 9.1 AI 画图

```
用户说话 → VAD 检测 → 录 webm
    → POST /api/voice/describe?mode=image&stage=full
    → 百度 ASR → asr_text
    → LLM（voice_drawing.md, mode=image）→ prompt_en
    → 千帆生图 → image_base64
    → 自动写入 drawings 表
    → 前端展示 + TTS 播报
```

可选参数 `prior_prompt`：多轮时在上一轮英文提示词基础上继续润色。

### 9.2 图表

```
用户说话 → 同上录音与上传
    → POST /api/voice/describe?mode=chart
    → 百度 ASR → LLM → ChartSpec JSON
    → 前端 buildOption() → ECharts 渲染
```

图表 JSON 结构示例：

```json
{
  "type": "pie",
  "title": "水果销量占比",
  "labels": ["苹果", "香蕉", "橙子"],
  "series": [{ "name": "销量", "type": "pie", "data": [60, 25, 15] }]
}
```

支持 `type`: `pie` | `bar` | `line`。

### 9.3 画板库

- **独立页** `/drawings.html`：查看全部历史、详情、删除
- **嵌入页**：`image.html` / `chart.html` 底部可保存、语音加载/删除
- 生图成功后 `describe.py` 会**静默**调用 `create_drawing_from_payload` 自动入库

---

## 10. API 文档

### 10.1 语音描述（核心）

**`POST /api/voice/describe`**

| Query | 说明 |
|-------|------|
| `mode` | `image` \| `chart`（必填） |
| `stage` | `full`（默认，含生图）\| `prompt`（仅润色，image 模式） |

| Form 字段 | 说明 |
|-----------|------|
| `file` | 音频文件（webm 等），与 `text` 二选一 |
| `text` | 直接传文本（跳过 ASR） |
| `prior_prompt` | 可选，上一轮英文提示词（image 多轮） |

**响应（image 模式）**

```json
{
  "mode": "image",
  "asr_text": "用户原话",
  "llm_text": "LLM 原始输出",
  "prompt_en": "英文提示词",
  "prompt_cn": "中文摘要",
  "merged_prompt_en": "合并后提示词",
  "image_base64": "base64 字符串",
  "stage": "full"
}
```

**响应（chart 模式）**

```json
{
  "mode": "chart",
  "asr_text": "...",
  "llm_text": "...",
  "chart": { "type": "pie", "title": "...", "labels": [], "series": [] }
}
```

### 10.2 其他语音接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/voice/asr` | 仅 ASR，返回 `asr_text` |
| POST | `/api/voice/generate-image` | 已有 `prompt_en` 时仅生图 |
| POST | `/api/asr-nlu` | 旧版画布绘图 NLU（`frontend/index.html`） |

### 10.3 画板库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/drawings?limit=20` | 列表 |
| GET | `/api/drawings/{id}` | 详情 |
| POST | `/api/drawings` | 新建 |
| PUT | `/api/drawings/{id}` | 更新 |
| DELETE | `/api/drawings/{id}` | 删除 |
| POST | `/api/drawings/export` | 导出并标记 |
| POST | `/api/drawings/{id}/export` | 按 ID 导出 |

### 10.4 健康检查

**`GET /api/health`** → `{"status": "ok"}`

---

## 11. 数据库

**文件**：`data/drawings.db`（SQLite）

**表 `drawings`**

| 字段 | 说明 |
|------|------|
| `id` | 自增主键 |
| `title` | 标题 |
| `commands_json` | 画布命令 JSON（图表模式存 chart spec） |
| `asr_text` | 语音识别文本 |
| `reply_text` | LLM 回复 / 英文 prompt |
| `background_base64` | 图片或图表快照 base64 |
| `exported` | 是否已导出 |
| `export_target` | 导出目标（如 desktop） |
| `export_time` | 导出时间 |
| `created_at` | 创建时间 |

---

## 12. LLM 提示词

文件：`prompts/voice_drawing.md`

- **image 模式**：输出 `prompt_en`、`prompt_cn`、`style`、`detail`
- **chart 模式**：输出 `type`、`title`、`labels`、`series`、`note`
- 要求模型**仅输出 JSON**，后端用 pydantic 校验

---

## 13. 前端状态机（生图/图表页）

| 状态 | 含义 |
|------|------|
| `idle` | 关麦或等待 |
| `listening` | 倾听中 |
| `recording` | VAD 检测到语音，录音中 |
| `uploading` | 上传音频 |
| `analyzing` | LLM 处理中 |
| `generating` | 生图/渲染中 |
| `tts` | 语音播报中 |
| `done` | 完成 |
| `error` | 出错 |

---

## 14. 已知限制

1. Web Speech API 浏览器兼容性不一，实时预览在部分环境可能不准；正式识别走后端百度 ASR。
2. 百度 ASR 对口语数字、专有名词可能误识别，可改用讯飞（`ASR_VENDOR=xfyun`）。
3. 画板库「进入」语音入口仅在**主页**；生图/图表页需说「退出」回主页再说「画板」。
4. `frontend/index.html` 为早期画布绘图 Demo，与当前主流程（image/chart）相对独立。

---

## 15. 相关文档

| 文档 | 说明 |
|------|------|
| [README.md](../README.md) | 快速上手 |
| [PRESENTATION.md](./PRESENTATION.md) | 答辩演示讲稿与 Demo 脚本 |
| [.env.example](../.env.example) | 环境变量模板 |

---

## 16. 测试脚本

```bash
# LLM 连通性
python scripts/test_llm.py

# 各 API 连通性
python scripts/test_apis.py
```

---

*文档版本与代码同步至当前主分支功能（语音常开、开关麦指令、3 秒静音/冷却、生成锁）。*
