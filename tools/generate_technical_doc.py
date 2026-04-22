# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt


ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "技术.docx"

EXCLUDE_DIR_NAMES = {
    ".venv",
    "node_modules",
    "media",
    "dist",
    "__pycache__",
    "chroma_db",
    ".idea",
    ".cursor",
    ".pytest_cache",
}

TEXT_EXTENSIONS = {
    ".py",
    ".pyw",
    ".vue",
    ".ts",
    ".js",
    ".css",
    ".html",
    ".md",
    ".txt",
    ".bat",
    ".json",
    ".d.ts",
}

TEXT_FILENAMES = {
    ".env",
    ".env.example",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "README.md",
}

MANUAL_NOTES: dict[str, dict[str, str]] = {
    "backend/learning/services/translation_service.py": {
        "role": "翻译主引擎。负责术语提示、容器级结构化翻译、缓存命中、并发调度与失败回退。",
        "tech": "OpenAI 兼容接口调用、JSON 结构化输出约束、SHA256 缓存键、线程池并发、Django ORM 批量更新。",
        "hard": "需要同时保证翻译质量、版式一致性和吞吐稳定性；通过“结构化翻译->缺失重试->文本兜底”三段式降低失败率。",
    },
    "backend/learning/services/ppt_parser_service.py": {
        "role": "PPT 解析核心。抽取文本容器、段落、坐标、字体信息，并重建阅读顺序。",
        "tech": "python-pptx、Windows COM 兼容转换、占位符过滤、分组形状递归、容器/块排序策略。",
        "hard": "PPT 结构异构且噪声多，需兼顾标题识别、表格单元拆分、分组形状路径定位和顺序稳定性。",
    },
    "backend/learning/services/image_processing_service.py": {
        "role": "译后可视化处理核心。将译文回填到形状并进行字体/颜色自适应，输出可读预览。",
        "tech": "python-pptx + Pillow、字体候选回退、二分法字号拟合、背景采样、对比度比值优化。",
        "hard": "不同语言字符密度差异大，必须在固定文本框中实现尽量不溢出且可读的自动排版。",
    },
    "backend/learning/services/qa_service.py": {
        "role": "问答编排服务。支持整份课件与单页两种上下文范围，构造引用信息。",
        "tech": "RAG（Chroma 检索）、历史对话拼接、提示词边界约束、引用片段回传。",
        "hard": "要在“上下文充分性、响应时延、答案可追溯”间平衡，避免泛化回答和幻觉。",
    },
    "backend/learning/services/vector_index_service.py": {
        "role": "向量索引服务。负责课件级重建索引、按课件/页过滤检索。",
        "tech": "Chroma PersistentClient、文档ID规则、where 条件过滤、距离分数输出。",
        "hard": "索引重建与版本一致性需要稳定的 ID 设计和旧索引清理策略。",
    },
    "backend/learning/services/summary_service.py": {
        "role": "课件总结服务。生成章节摘要、重点、术语表与思维导图。",
        "tech": "结构化 JSON 提示词、JSON 载荷提取、异常兜底本地总结。",
        "hard": "大模型输出格式不稳定，需做严格解析与可降级策略，避免前端空结果。",
    },
    "backend/learning/services/llm_client.py": {
        "role": "统一大模型客户端封装，负责请求发送、重试、鉴权异常处理与日志记录。",
        "tech": "requests、指数退避、401 自动刷新 .env、错误分型异常。",
        "hard": "外部 API 的抖动与鉴权失效是高频问题，客户端必须具备韧性与可观测性。",
    },
    "backend/learning/views.py": {
        "role": "后端接口主编排层。串联上传、翻译、状态、问答、总结、记录等业务闭环。",
        "tech": "DRF APIView、事务控制、后台线程任务、批量更新、进度统计。",
        "hard": "长任务异步化与状态可见性是关键，需要保持前后端状态一致和错误可恢复。",
    },
    "backend/learning/models.py": {
        "role": "核心数据模型定义：课件、页内容、问答记录、总结记录、术语库、翻译缓存。",
        "tech": "Django ORM、JSONField、联合唯一约束、索引优化。",
        "hard": "模型既要支持业务查询，也要支撑翻译性能与历史追踪场景。",
    },
    "backend/learning/serializers.py": {
        "role": "API 输入输出规范层，含上传校验、问答历史清洗、字段结构约束。",
        "tech": "DRF Serializer/ModelSerializer、格式校验、字段裁剪。",
        "hard": "前端多场景调用下必须保持参数健壮，避免脏数据直接进入服务层。",
    },
    "frontend/src/views/UploadTranslateView.vue": {
        "role": "前端核心工作台。承载上传、翻译进度、双语对照、问答、总结全链路交互。",
        "tech": "Vue3 组合式 API、轮询策略、Markdown 渲染、组件状态编排。",
        "hard": "单页内状态非常多（上传/翻译/问答/总结/页跳转），需控制复杂状态流和用户反馈。",
    },
    "frontend/src/views/RecordsView.vue": {
        "role": "历史复盘中心。支持课件切换、历史问答复用、总结复用、导图与术语查看。",
        "tech": "路由联动、消息还原、侧边栏结构化导航、Markdown 展示。",
        "hard": "需要同时处理历史数据一致性与当前工作台联动，保证上下文连续体验。",
    },
    "frontend/src/views/DashboardLayout.vue": {
        "role": "主布局壳层。负责顶部导航、课件切换、登录态及子页面 keep-alive 管理。",
        "tech": "Vue Router、keep-alive、localStorage 持久化、全局事件广播。",
        "hard": "跨页面共享“当前课件”状态，避免切页导致上下文丢失。",
    },
    "frontend/src/router/index.ts": {
        "role": "路由与守卫配置，定义登录保护、默认跳转与滚动行为。",
        "tech": "vue-router、beforeEach 权限守卫。",
        "hard": "确保未登录重定向与已登录回流逻辑稳定。",
    },
    "frontend/src/api/client.ts": {
        "role": "HTTP 客户端统一入口。自动注入 JWT，统一处理 401 失效。",
        "tech": "axios 实例、请求/响应拦截器。",
        "hard": "鉴权过期场景需快速回收状态并防止页面处于半登录态。",
    },
    "launch_platform.pyw": {
        "role": "桌面启动器（Tkinter），用于一键启动前后端并查看日志。",
        "tech": "Tkinter GUI、subprocess、线程日志流式输出。",
        "hard": "多进程生命周期管理与跨环境 npm 探测易出兼容性问题。",
    },
}


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIR_NAMES for part in path.parts)


def is_text_file(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if path.name in TEXT_FILENAMES:
        return True
    if path.name.endswith(".d.ts"):
        return True
    return False


def safe_read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "cp936", "latin1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def extract_python_symbols(content: str) -> tuple[list[str], list[str], list[str]]:
    classes: list[str] = []
    funcs: list[str] = []
    imports: list[str] = []
    try:
        tree = ast.parse(content)
    except Exception:
        return classes, funcs, imports

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    imports = sorted(set(imports))
    return classes, funcs, imports


def extract_ts_like_symbols(content: str) -> list[str]:
    result: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("export interface ", "interface ")):
            result.append(stripped.split("{")[0].strip())
        elif stripped.startswith(("export const ", "const ")):
            name = stripped.split("=")[0].replace("export", "").replace("const", "").strip()
            if name:
                result.append(name)
        elif stripped.startswith(("export function ", "function ")):
            name = stripped.split("(")[0].replace("export", "").replace("function", "").strip()
            if name:
                result.append(name)
    return result[:20]


def detect_tech_keywords(content: str, relative_path: str) -> str:
    tags: list[str] = []
    lower = content.lower()
    if "django" in lower:
        tags.append("Django/DRF")
    if "simplejwt" in lower or "jwt" in lower:
        tags.append("JWT 鉴权")
    if "chromadb" in lower:
        tags.append("Chroma 向量检索")
    if "python-pptx" in lower or "from pptx" in lower:
        tags.append("PPT 解析/编辑")
    if "pillow" in lower or "from pil" in lower:
        tags.append("图像处理")
    if "threadpoolexecutor" in lower or "threading" in lower:
        tags.append("并发/异步任务")
    if "requests.post" in lower and "chat/completions" in lower:
        tags.append("OpenAI 兼容接口")
    if "markdown-it" in lower:
        tags.append("Markdown 渲染")
    if "axios" in lower:
        tags.append("Axios HTTP")
    if "vue-router" in lower:
        tags.append("前端路由")
    if "element-plus" in lower:
        tags.append("Element Plus UI")
    if "pytest" in lower or "testcase" in lower or "apitestcase" in lower:
        tags.append("测试与Mock")
    if "python-docx" in lower or "from docx" in lower:
        tags.append("Word 文档生成")
    if "tkinter" in lower:
        tags.append("桌面 GUI 启动器")
    if relative_path.endswith("requirements.txt"):
        tags.append("Python 依赖清单")
    if relative_path.endswith("package.json"):
        tags.append("前端依赖与脚本")
    if relative_path.endswith("package-lock.json"):
        tags.append("依赖版本锁定")
    if not tags:
        tags.append("工程配置/通用脚本")
    return "、".join(dict.fromkeys(tags))


def infer_default_role(relative_path: str, ext: str) -> str:
    rp = relative_path.replace("\\", "/")
    name = Path(rp).name
    if "migrations/" in rp:
        return "数据库迁移脚本，记录数据模型演进与字段变更。"
    if "/tests/" in rp:
        return "自动化测试文件，用于验证 API 链路、服务逻辑与边界行为。"
    if rp.endswith("/urls.py"):
        return "路由注册文件，定义接口路径到视图处理器的映射。"
    if rp.endswith("/settings.py"):
        return "全局配置中心，管理中间件、数据库、鉴权、模型与存储参数。"
    if rp.endswith("/models.py"):
        return "ORM 数据模型定义文件。"
    if rp.endswith("/serializers.py"):
        return "序列化与参数校验文件。"
    if rp.endswith("/views.py"):
        return "接口视图编排文件。"
    if rp.endswith("README.md"):
        return "项目说明文档，描述运行方式、技术栈与使用流程。"
    if rp.endswith(".vue"):
        return "Vue 单文件组件，承载页面结构、状态与交互逻辑。"
    if rp.endswith((".ts", ".js")):
        return "前端脚本/类型定义文件，用于路由、API 调用与类型约束。"
    if rp.endswith(".css"):
        return "全局或页面样式文件。"
    if rp.endswith(".html"):
        return "前端入口模板文件。"
    if rp.endswith(".json"):
        return "配置或依赖锁定文件。"
    if rp.endswith(".py") or rp.endswith(".pyw"):
        return "Python 业务/工具脚本。"
    if name in {".env", ".env.example"}:
        return "环境变量模板/本地配置文件，用于模型接口、密钥与服务参数。"
    return "项目资源或配置文件。"


def infer_default_hard(content: str, relative_path: str, line_count: int) -> str:
    lower = content.lower()
    if "threadpoolexecutor" in lower or "threading" in lower:
        return "并发执行下需要处理任务顺序、异常隔离与状态一致性。"
    if "chromadb" in lower:
        return "检索效果依赖索引构建与过滤条件，需平衡召回率和噪声。"
    if "pythoncom" in lower or "win32com" in lower:
        return "Office COM 自动化存在环境依赖与进程稳定性挑战。"
    if "json" in lower and "llm" in lower:
        return "需要应对模型输出格式不稳定，保证解析健壮性。"
    if relative_path.endswith(".vue") and line_count > 500:
        return "页面状态多且交互复杂，需控制状态流与副作用。"
    if "/tests/" in relative_path.replace("\\", "/"):
        return "测试需覆盖真实边界并尽量降低外部依赖波动。"
    if line_count > 300:
        return "文件职责较重，阅读时需关注模块边界与调用链。"
    return "实现难度中等，主要在于与上下游模块接口保持一致。"


def build_file_record(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    ext = path.suffix.lower()
    is_text = is_text_file(path)
    content = safe_read_text(path) if is_text else ""

    lines = content.splitlines() if is_text else []
    line_count = len(lines)
    nonempty = len([ln for ln in lines if ln.strip()]) if is_text else 0

    symbols = ""
    if is_text and ext in {".py", ".pyw"}:
        classes, funcs, imports = extract_python_symbols(content)
        symbol_parts = []
        if classes:
            symbol_parts.append("类: " + ", ".join(classes[:8]))
        if funcs:
            symbol_parts.append("函数: " + ", ".join(funcs[:10]))
        if imports:
            symbol_parts.append("关键依赖: " + ", ".join(imports[:8]))
        symbols = "；".join(symbol_parts) if symbol_parts else "无显式类/函数定义。"
    elif is_text and ext in {".ts", ".js", ".vue"}:
        ts_symbols = extract_ts_like_symbols(content)
        symbols = "；".join(ts_symbols[:12]) if ts_symbols else "以模板/组合式状态和配置为主。"
    elif is_text:
        symbols = "配置或静态内容文件。"
    else:
        symbols = "二进制/产物文件，不适合做源码级符号提取。"

    note = MANUAL_NOTES.get(relative, {})
    role = note.get("role") or infer_default_role(relative, ext)
    tech = note.get("tech") or detect_tech_keywords(content, relative) if is_text else "文档/资源产物"
    hard = note.get("hard") or infer_default_hard(content, relative, line_count) if is_text else "主要作为资源产物，难点不在算法而在流程管理。"

    return {
        "path": relative,
        "is_text": is_text,
        "line_count": line_count,
        "nonempty": nonempty,
        "role": role,
        "tech": tech,
        "hard": hard,
        "symbols": symbols,
        "size": path.stat().st_size,
    }


def configure_style(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(11)


def add_paragraph(doc: Document, text: str, *, bold: bool = False) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    run.bold = bold


def add_title(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(22)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def add_heading(doc: Document, text: str, level: int = 1) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    run.bold = True
    if level == 1:
        run.font.size = Pt(16)
    elif level == 2:
        run.font.size = Pt(13)
    else:
        run.font.size = Pt(11)


def generate_document(records: list[dict[str, Any]]) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc = Document()
    configure_style(doc)

    add_title(doc, "双语课程辅助学习平台技术介绍文档")
    add_paragraph(doc, f"生成时间：{now_str}")
    add_paragraph(doc, "编码说明：本报告由 UTF-8 编码脚本自动生成。")
    add_paragraph(doc, "统计范围：已排除 node_modules、.venv、media、dist、__pycache__、chroma_db 等依赖/缓存/媒体目录。")

    text_records = [r for r in records if r["is_text"]]
    binary_records = [r for r in records if not r["is_text"]]
    total_lines = sum(r["line_count"] for r in text_records)
    total_nonempty = sum(r["nonempty"] for r in text_records)

    add_heading(doc, "1. 项目总体技术说明", 1)
    add_paragraph(
        doc,
        "本项目采用“Django + Vue3”的前后端分离架构，以大语言模型能力为核心，围绕课件学习流程构建了上传解析、翻译预览、RAG问答、自动总结与历史复盘的一体化闭环。"
    )
    add_paragraph(
        doc,
        "后端通过服务层分离（PPT解析、翻译、向量检索、摘要、图像回写），保障复杂业务可维护；前端通过单页工作台编排多状态交互，提升学习连续性与操作效率。"
    )

    add_heading(doc, "2. 关键算法与技术点", 1)
    algo_points = [
        "PPT 结构化解析算法：递归遍历文本框/表格/分组形状，抽取容器坐标、段落和字体信息，并通过排序策略重建阅读顺序。",
        "版式感知翻译策略：优先容器级 JSON 翻译，缺失项重试，最终单容器兜底，兼顾可用性与质量。",
        "翻译缓存算法：以版本号、翻译类型、模型名、术语哈希、源文本构建 SHA256 缓存键，降低重复请求成本。",
        "并发调度策略：ThreadPoolExecutor 有界并发，逐批提交与回收任务，减少长课件翻译时延。",
        "可读性增强算法：字体大小二分拟合、背景采样与对比度修正，保证译文在原框中尽量清晰可读。",
        "RAG 问答策略：向量检索召回 + 历史对话拼接 + 范围约束（单页/全局）+ 引用片段回传。",
        "摘要鲁棒性策略：要求 LLM 严格 JSON 输出，失败时执行本地总结兜底，确保前端永不空白。",
    ]
    for point in algo_points:
        add_paragraph(doc, f"- {point}")

    add_heading(doc, "3. 代码难点总览", 1)
    hard_points = [
        "异构 PPT 数据的稳定解析：不同模板、占位符和分组嵌套导致解析复杂。",
        "长任务后台化与状态一致性：翻译是长耗时任务，需要前后端可观测且可恢复。",
        "模型输出不稳定：结构化输出有概率格式漂移，需要健壮的提取与回退机制。",
        "可视化译后处理：在不破坏版式的前提下保证文本可读，涉及字体、换行与颜色多维协同。",
        "复杂前端状态编排：上传、翻译、问答、总结共存于同一页面，必须控制状态复杂度。",
    ]
    for point in hard_points:
        add_paragraph(doc, f"- {point}")

    add_heading(doc, "4. 代码规模统计", 1)
    add_paragraph(doc, f"- 文本源码文件数：{len(text_records)}")
    add_paragraph(doc, f"- 文本源码总行数（含空行）：{total_lines}")
    add_paragraph(doc, f"- 文本源码总行数（非空行）：{total_nonempty}")
    add_paragraph(doc, f"- 非文本产物文件数：{len(binary_records)}")

    add_heading(doc, "5. 逐文件详解", 1)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        top = record["path"].split("/")[0]
        grouped.setdefault(top, []).append(record)

    for top in sorted(grouped.keys()):
        add_heading(doc, f"5.{sorted(grouped.keys()).index(top) + 1} {top}", 2)
        for rec in sorted(grouped[top], key=lambda x: x["path"]):
            add_heading(doc, rec["path"], 3)
            if rec["is_text"]:
                add_paragraph(doc, f"作用：{rec['role']}")
                add_paragraph(doc, f"涉及技术/算法：{rec['tech']}")
                add_paragraph(doc, f"代码难点：{rec['hard']}")
                add_paragraph(doc, f"关键符号：{rec['symbols']}")
                add_paragraph(doc, f"规模：{rec['line_count']} 行（非空 {rec['nonempty']} 行）")
            else:
                add_paragraph(doc, "作用：文档/图像/数据库/日志等非源码产物。")
                add_paragraph(doc, f"用途说明：{rec['role']}")
                add_paragraph(doc, f"文件大小：{rec['size']} bytes")

    add_heading(doc, "6. 结论与建议", 1)
    add_paragraph(
        doc,
        "该项目已经具备完整产品链路与明显工程化特征：模型调用韧性、缓存优化、并发调度、结构化解析与前端复杂交互均有落地。"
    )
    add_paragraph(
        doc,
        "后续建议优先关注三点：1) 将长流程改造为任务队列（Celery/RQ）；2) 增加离线评测集与质量指标；3) 为超大课件提供分段翻译与增量索引能力。"
    )

    doc.save(str(OUT_PATH))


def main() -> None:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path.relative_to(ROOT)):
            continue
        files.append(path)

    records = [build_file_record(path) for path in sorted(files)]
    generate_document(records)
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()

