# AI 语音绘图工具

> 纯语音驱动的 AI 生图 & 图表生成。开口即用，无需点击，支持语音导航、生成、导出与历史管理。

bilibili:https://www.bilibili.com/video/BV1fqJw6WEYf/?spm_id_from=333.1387.homepage.video_card.click&vd_source=8a035e308519ac60a7a4d83c6c575bab

docs/DESIGN.md 设计文档

## 功能概览
- **双模式生成**
  - 图片：口语 → LLM 提示词润色 → Qianfan 生图。
  - 图表：口语 → 结构化 JSON → ECharts 渲染（饼/柱/折）。
- **全程语音**
  - 主菜单语音导航（AI 画图/图表/画板、展开菜单）。
  - 模式页自动开麦，口令控制生成、刷新、加载/删除第 N 条、重试、停止、下载到桌面。
  - TTS 语音反馈，播报时自动暂停 ASR，防“自说自听”。
- **多轮融合**
  - 支持 `prior_prompt`，连续口令在上一次提示词基础上继续润色/完善。
- **防误触**
  - “返回主菜单”指令直接跳回，不触发生成。
  - VAD 时长判定：至少 ~0.8s 语音且静音 >2s 才收口，减少半句提交。
- **存储与导出**
  - 自动保存生成结果到 SQLite（含导出标记）。
  - “下载到桌面”按钮/语音触发，记录 `exported/export_target/export_time`。
- **图表美化**
  - 玫瑰饼图、渐变柱/折、标题留白、高清截图（DPR）。

## 快速开始
### 环境
- Python 3.10+
- Node 18+（仅在重构前端时需要）

### 安装与运行
```bash
# 后端
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r backend/requirements.txt
copy .env.example .env  # 填写 LLM_API_KEY / IMAGE_API_KEY / DB_PATH 等
python -m uvicorn app.main:app --reload

# 前端（当前使用 dist 静态文件，通常无需构建）
# 如需重新构建：cd frontend-react && npm install && npm run build
```

### 访问
- 主菜单：`http://localhost:8000/`
- AI 生图：`/image.html`
- 图表：`/chart.html`
- 画板库：`/drawings.html`
- 健康检查：`/api/health`

## 语音指令（示例）
- 主菜单：  
  - “AI 画图” / “图表功能” / “画板”  
  - “展开菜单”
- 模式页通用：  
  - “返回主菜单”/“回首页”（不提交生成，直接跳回）  
  - “下载到桌面”/“保存到桌面”/“下载”  
  - “刷新”  
  - “加载第3条”/“删除第2条”  
  - “重试”  
  - “停止”/“取消”
- 生图多轮：  
  - “在刚才基础上加 … / 改 …” 会携带 `prior_prompt` 继续润色。


  ## 项目结构
```
QINIU/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口，挂载 dist
│   │   ├── config.py            # 配置读取（.env）
│   │   ├── paths.py             # 路径常量
│   │   ├── routers/
│   │   │   ├── describe.py      # 语音描述→LLM→图/表，支持 prior_prompt
│   │   │   ├── drawings.py      # 历史记录 CRUD / 导出标记
│   │   │   └── voice.py         # ASR 调用 & JSON 清理
│   │   └── services/llm.py      # LLM 统一调用
│   └── requirements.txt
├── frontend-react/
│   └── dist/                    # 静态前端
├── prompts/
│   └── voice_drawing.md         # LLM 提示词模板（图片/图表双模式）
├── data/
│   └── drawings.db              # SQLite 记录
├── README.md
├── .env.example
└── run.py
```


## 主要文件
- 后端
  - `backend/app/routers/describe.py`：语音描述入口，LLM 解析，Qianfan 生图，支持 `prior_prompt`。
  - `backend/app/routers/drawings.py`：历史记录 CRUD、导出标记。
  - `backend/app/routers/voice.py`：ASR 调用 & JSON 清理。
  - `backend/app/config.py` / `backend/app/paths.py`：配置与路径。
- 前端（静态 dist）
  - `frontend-react/dist/index.html`：主菜单，自动语音导航。
  - `frontend-react/dist/image.html`：AI 生图页，状态机/VAD/TTS/导出/列表语音指令。
  - `frontend-react/dist/chart.html`：图表页，状态机/VAD/TTS/导出/列表语音指令，ECharts 渲染。
  - `frontend-react/dist/drawings.html`：画板库查看/删除。

## 接口速览
- `POST /api/voice/describe?mode=image|chart`  
  - Form: `file`(audio) 或 `text`，可选 `prior_prompt`  
  - Resp: `asr_text`, `llm_text`, `prompt_en`, `merged_prompt_en`, `image_base64` | `chart`
- `GET /api/drawings` / `GET /api/drawings/{id}` / `POST /api/drawings` / `DELETE /api/drawings/{id}`
- `POST /api/drawings/{id}/export` / `POST /api/drawings/export`

## 已知限制 & 后续可做
- Web Speech API 在部分浏览器兼容性有限，若需更稳可强制使用后端 ASR。

