<div align="center">
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Rocket.png" width="100px" />

  <h1>Re:Novel<br> 
  文境重塑</h1>
  <p>
    以记忆之名，重塑故事之境。
  </p>

  <p>
    <a href="https://github.com/yourname/repo/graphs/contributors">
      <img src="https://img.shields.io/github/contributors/yourname/repo?style=flat-square&color=orange" alt="contributors" />
    </a>
    <a href="https://github.com/yourname/repo/network/members">
      <img src="https://img.shields.io/github/forks/yourname/repo?style=flat-square&color=blue" alt="forks" />
    </a>
    <a href="https://github.com/yourname/repo/stargazers">
      <img src="https://img.shields.io/github/stars/yourname/repo?style=flat-square&color=red" alt="stars" />
    </a>
  </p>
</div>


Your Local, Intelligent, and Privacy-First Novel Rewriting Studio.

🌟 核心特性 (Features)
1. 🧠 全局记忆与一致性 (RAG Memory)
告别“吃书”：内置 ChromaDB 向量数据库。系统会自动记忆你写过的每一章内容。

智能检索：当你改写第 100 章时，AI 会自动检索并参考第 1 章的伏笔、设定和人物关系，确保剧情连贯。

智能联想：即使你只写了“那把剑”，系统也能联想到“生锈的铁剑”并提取相关设定。

2. ✍️ 卡片流式编辑器 (Card-Flow Editor)
平行对比：左侧原文，右侧 AI 改写，段落级绝对对齐。

动态操作：支持在任意位置插入新段落、删除冗余段落。AI 可根据指令进行扩写或无中生有。

沉浸体验：基于 CodeMirror 的美化编辑器，支持全屏写作。

3. 🤖 三模态 AI 协作 (Tri-Model Architecture)
Writer (作家)：负责根据你的指令进行改写、润色、扩写。

Reviewer (总监)：独立的审校 AI。它会像严苛的主编一样评分（0-10分），检查 OOC（角色崩坏）或逻辑漏洞。

Chat (助手)：右侧常驻助手，可随时询问“这一章讲了什么？”或“主角第一次出场是在哪？”。

4. ⚡ 自动化工作流 (Batch Workflow)
全书精修：一键启动，AI 会像流水线一样自动遍历全书，逐章逐段进行改写。

断点续传：随时暂停，下次继续。

数据安全：支持一键创建项目副本（Fork），改坏了随时回滚。

5. 🎭 角色扮演与风格控制
SillyTavern 兼容：支持导入酒馆 (Tavern) 格式的 PNG/JSON 角色卡，AI 自动提取人设。

风格矩阵：精细控制保留度（20%-100%）、扩写欲望（保守/狂野）、内容尺度和文风倾向。

🚀 快速开始 (Quick Start)
环境要求
OS: Windows / macOS / Linux

Python: 3.10 或 3.11 (推荐 3.11)

C++ Build Tools (仅 Windows 用户需要，用于编译向量库)

安装步骤
克隆仓库

Bash

git clone https://github.com/yourusername/NovelForge.git
cd NovelForge
创建虚拟环境 (推荐)

Bash

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
安装依赖

Bash

pip install -r requirements.txt
配置 API Key

启动程序后，点击右上角 ⚙️ 设置 (Settings) 图标。

填入你的 OpenAI 或 Google Gemini API Key。

(可选) 将 .env.example 重命名为 .env 并填入默认 Key。

启动引擎

Bash

python main.py
浏览器将自动打开 http://localhost:8080。

📖 使用指南
第一步：导入与分章
点击右上角 “导入”，拖入 .txt 小说文件。

系统会自动识别“第X章”或纯文本标题，并将小说切分为章节存入数据库。

提示：导入时系统会自动进行一次全书向量化，请耐心等待。

第二步：单章精修
在左侧书架选择一章。

在顶部输入指令（例如：“把这段对话写得更幽默”）。

点击段落中间的 🪄 魔法棒。

AI 会生成改写内容。如果开启了 Reviewer，它会自动进行评分和拦截。

第三步：全书自动化
点击顶部的 “批量任务” 按钮。

选择范围（全书 / 继续进度）。

勾选 “创建副本”（强烈推荐）。

点击启动，观察 AI 自动工作。

🛠️ 技术栈 (Tech Stack)
UI: NiceGUI (基于 Vue/FastAPI)

Database: SQLite (元数据) + ChromaDB (向量记忆)

AI Orchestration: LangChain

Text Processing: RapidFuzz (模糊匹配), Tiktoken

Editor: CodeMirror

📂 目录结构
NovelForge/
├── data/                  # 用户数据 (已在 .gitignore 中忽略)
│   ├── projects/          # SQLite 数据库 (.db)
│   ├── vectordb/          # ChromaDB 向量索引
│   └── presets/           # 角色卡与预设
├── src/
│   ├── ai/                # LLM 交互与 RAG 引擎
│   ├── core/              # 项目管理与文件解析
│   ├── ui/                # 界面布局与组件
│   └── utils/             # 日志与工具类
├── main.py                # 启动入口
└── requirements.txt       # 依赖清单
🤝 贡献 (Contributing)
欢迎提交 Issue 或 Pull Request！如果你有新的脑洞（比如增加 TTS 朗读、导出 EPUB 功能），请随时告诉我。

📄 License
本项目采用 MIT License 开源。
