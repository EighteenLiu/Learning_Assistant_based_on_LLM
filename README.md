# 基于 LLM 的 PPT 翻译学习平台

## 功能概览
- 上传并解析 `.ppt/.pptx/.pdf`
- 英文到中文翻译（含图片区域 OCR 翻译）
- 译后预览与导出翻译后的课件文件（PPT/PDF）
- 基于课件内容问答与总结

## 环境要求
- Python 3.10+
- Node.js 18+
- 可选：Ollama（用于本地模型）

## 后端配置
在 `backend/.env` 中配置模型。

### 方案 A：本地 Ollama（推荐，免费）
```env
USE_LOCAL_LLM=1
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen2.5vl:3b
```

### 方案 B：云端 API（百炼等）
```env
USE_LOCAL_LLM=0
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=qwen3.6-flash
```

## 本地部署 qwen2.5vl:3b（Ollama）
1. 安装 Ollama（Windows）。
2. 拉取模型：
```powershell
ollama pull qwen2.5vl:3b
```
3. 可选检查：
```powershell
ollama list
```
4. 确保 Ollama 服务运行（默认 `http://127.0.0.1:11434`）。

## 启动项目
### 后端
```powershell
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

### 前端
```powershell
cd frontend
npm install
npm run dev
```

## 访问地址
- 前端: `http://127.0.0.1:5173`
- 后端: `http://127.0.0.1:8000`
- API 文档: `http://127.0.0.1:8000/api/docs/`
