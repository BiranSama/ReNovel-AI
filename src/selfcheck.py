"""打包产物的自检（ReNovel.exe --self-check）：依赖能导入、本地向量模型的推理组件可用、数据目录与数据库能创建。

页面能打开并不代表所有依赖都打进了包里（如 onnxruntime 只在首次使用本地向量模型时才导入），所以单独检查。
"""
import asyncio
import importlib

MODULES = ("numpy", "onnxruntime", "tokenizers", "openai", "aiosqlite", "networkx", "charset_normalizer", "nicegui")


def run() -> int:
    for name in MODULES:
        importlib.import_module(name)
    import onnxruntime

    if "CPUExecutionProvider" not in onnxruntime.get_available_providers():
        print("self-check failed: onnxruntime 没有 CPUExecutionProvider")
        return 1

    from src import paths
    from src.core.managers import Services

    services = Services()
    asyncio.run(services.init_db())
    print(f"self-check ok: 依赖 {len(MODULES)} 个均可导入，数据目录 {paths.data_dir()}")
    return 0
