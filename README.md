<div align="center">
  <h1>Re:Novel <br> 文境重塑</h1>

  <a href="https://git.io/typing-svg">
    <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&pause=1000&color=3591F7&center=true&vCenter=true&width=435&lines=大模型小说精修助手;以记忆之名，重塑故事之境" alt="Typing SVG" />
  </a>

  <p>
    <strong>智能化的小说重写工作台</strong>
  </p>

  <p>
    <a href="https://github.com/BiranSama/ReNovel-AI/graphs/contributors">
      <img src="https://img.shields.io/github/contributors/BiranSama/ReNovel-AI?style=flat-square&color=orange" alt="contributors" />
    </a>
    <a href="https://github.com/BiranSama/ReNovel-AI/network/members">
      <img src="https://img.shields.io/github/forks/BiranSama/ReNovel-AI?style=flat-square&color=blue" alt="forks" />
    </a>
    <a href="https://github.com/BiranSama/ReNovel-AI/stargazers">
      <img src="https://img.shields.io/github/stars/BiranSama/ReNovel-AI?style=flat-square&color=red" alt="stars" />
    </a>
    <a href="https://github.com/BiranSama/ReNovel-AI/blob/main/LICENSE">
      <img src="https://img.shields.io/github/license/BiranSama/ReNovel-AI?style=flat-square&color=green" alt="license" />
    </a>
    <a href="https://github.com/BiranSama/ReNovel-AI/releases">
      <img src="https://img.shields.io/github/v/release/BiranSama/ReNovel-AI?style=flat-square&color=purple" alt="release" />
    </a>
  </p>
</div>

## **目前的功能 项目的愿景**

- [x] **导入TXT文件并进行章节分析与记忆保存**
- [x] **查看小说内容/分章节或全文**
- [x] **根据需求进行精修**
- [x] **针对AI生成内容的精校**
- [x] **动态的记忆保存功能**
- [x] **通过*聊天*的形式获取小说内容**
- [x] ***不仅是小说***
- [ ] **完全兼容酒馆（sillytavern）的预设与角色卡**

<details>
  <summary>**👉 还有些其他的....**</summary>
  
  ***或许可以用来改论文？***
  
  **给小说加料？*(NSFW)***
  
  **还有什么....**

  
</details>

## 🌟 核心特性 (Features)

### 1. 🧠 全局记忆与一致性 (RAG Memory)
告别"吃书"，系统内置向量记忆（SQLite + numpy），自动记忆全书内容。向量默认由本地中文模型 bge-small-zh 生成（首次使用时自动下载，可设置镜像），也可改用 OpenAI 兼容的 `/embeddings` 接口。
* **智能检索**：当你改写第 100 章时，AI 会自动检索参考第 1 章的伏笔、设定和人物关系。
* **智能联想**：即使你只写了"那把剑"，系统也能联想到"生锈的铁剑"并提取相关设定。
* **一致性检查**：独立的 Reviewer AI 检测 OOC（角色崩坏）或逻辑漏洞。

### 2. ✍️ 卡片流式编辑器 (Card-Flow Editor)
* **平行对比**：左侧原文，右侧 AI 改写，段落级绝对对齐。
* **动态操作**：支持任意插入新段落、删除冗余。AI 可根据指令进行扩写或无中生有。
* **沉浸体验**：基于 **CodeMirror** 的美化编辑器，支持全屏专注写作。

### 3. 🤖 三模态 AI 协作 (Tri-Model Architecture)
独特的双模态写作-写作与校验同步运行-保证你的文章质量
| 角色 | 功能描述 |
| :--- | :--- |
| **Writer (作家)** | 负责根据你的指令进行改写、润色、扩写。 |
| **Reviewer (总监)** | 独立的审校 AI。检查 OOC（角色崩坏）或逻辑漏洞。 |
| **Chat (助手)** | 右侧常驻助手，随时回答"这一章讲了什么？"或"主角第一次出场是在哪？"。 |

### 4. ⚡ 自动化工作流 (Batch Workflow)
* **全书精修**：一键启动流水线，自动遍历全书逐章改写。
* **断点续传**：随时暂停，进度自动保存。
* **数据安全**：支持一键 **Fork 项目副本**，改坏了随时回滚，安全感拉满。

### 5. 🎭 角色扮演与风格控制
* **SillyTavern 兼容**：支持导入酒馆 (Tavern) 格式的 PNG/JSON 角色卡，自动提取人设。**ToDo**
* **风格矩阵**：精细控制保留度（20%-100%）、扩写欲望（保守/狂野）、内容尺度和文风倾向。

---

## 🚀 快速开始 (Quick Start)


### 🚀最简单的方式

**右侧release下载zip文件解压，打开Run.Bat即可**

## 🌟 开始

### 环境要求
* **OS**: Windows / macOS / Linux
* **Python**: 3.10 或 3.11 (推荐 3.11)

> [!IMPORTANT]
> **Windows 用户请注意**：你需要安装 C++ Build Tools 以编译向量库依赖。
> 下载地址: https://visualstudio.microsoft.com/visual-cpp-build-tools/

### 安装步骤

**1. 克隆仓库**
```bash
git clone https://github.com/BiranSama/ReNovel-AI.git
cd ReNovel-AI
```

**2. 一键安装 (推荐)**

# Windows
```bash
双击运行 setup.bat
```
# macOS / Linux
```bash
chmod +x setup.sh
./setup.sh
```

**3. 配置 API Key**

启动程序后，点击右上角 ⚙️ 设置 (Settings) 图标，填入你的 OpenAI 或 Google Gemini API Key。

**4. 启动！**
```bash
# Windows
venv\Scripts\activate
python main.py

# macOS / Linux
source venv/bin/activate
python main.py
```

<details>
<summary>📖 手动安装 (高级用户)</summary>

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

</details>

## 📖 使用指南

**1. 导入与分章**

  点击右上角 "导入"，拖入 .txt 小说文件。

  系统会自动识别"第X章"或纯文本标题，并将小说切分为章节存入数据库。

  导入时系统会自动进行一次全书向量化，大文件请耐心等待。
  
**2. 单章精修**

  在左侧书架选择一章。

  在顶部输入指令（例如："把这段对话写得更幽默"）。

  点击段落中间的魔法棒。

  AI 会生成改写内容。如果开启了 Reviewer，它会自动进行评分和拦截。

  **3. 全书自动化精修**

  点击顶部的 "批量任务" 按钮。

  选择范围（全书 / 继续进度）。

  勾选 "创建副本"（强烈推荐）。

  点击启动，观察 AI 自动工作。
  
## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术方案 |
| :--- | :--- |
| Frontend | NiceGUI (Vue/FastAPI) |
| Database | SQLite（项目与章节；向量记忆用 SQLite + numpy） |
| Embedding | 本地 ONNX 模型（onnxruntime + tokenizers，无需 PyTorch）或 `/embeddings` API |
| AI Core | OpenAI Python SDK（OpenAI 兼容接口：OpenAI / DeepSeek / 各类中转 / Ollama；Gemini 走官方兼容端点） |
| Knowledge Graph | NetworkX + ECharts |

## 📂 目录结构
```
ReNovel-AI/
├── data/                      # 用户数据 (运行 FirstTime.py 创建，已在 .gitignore 中忽略)
│   ├── config.json            # 设置 (含 API Key，切勿提交)
│   ├── projects/              # SQLite 数据库 + 知识图谱 JSON
│   ├── memory.db              # 向量记忆（旧版本的 vectordb/ 会在首次启动时自动迁移）
│   ├── models/                # 下载的本地向量模型
│   └── presets/               # 角色卡与预设
├── src/
│   ├── services/              # 业务层（不依赖界面）：精修流程、导入、批量、聊天、图谱、上下文检索
│   ├── llm/                   # 统一 LLM 客户端（OpenAI 兼容接口）与提示词组装
│   ├── ai/                    # RAG 向量记忆
│   ├── core/                  # 数据库读写、设置、知识图谱存储、酒馆角色卡解析
│   ├── ui/                    # NiceGUI 界面：main_layout.py 组装页面，components/ 为各组件；session.py 为每个标签页的会话
│   ├── utils/logger.py        # 彩色控制台日志
│   └── paths.py               # 数据目录（开发 / exe / RENOVEL_DATA_DIR）
├── tests/                     # 单元测试 + 冒烟测试（假 LLM + 浏览器）
├── docs/ROADMAP.md            # 重构路线图与进度
├── FirstTime.py               # 初始化数据目录
└── main.py                    # 启动入口
```

## 🔧 开发 (Development)

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium   # 冒烟测试需要的浏览器

pytest                # 全部测试
pytest tests/unit     # 只跑单元测试（几秒）
pytest -m e2e         # 只跑冒烟测试：用假 LLM 启动真实应用，浏览器走一遍核心流程
```

标记为 `xfail` 的用例记录的是已知问题，修复后需要移除对应标记。

## 🤝 贡献 (Contributing)

欢迎提交 Issue 或 Pull Request！如果你有新的脑洞，请随时告诉我。这是我首次通过git上传仓库

有任何建议请不要吝啬。

Please Star！！！！

## 📄 License

本项目采用 GPL-3.0 License 开源
