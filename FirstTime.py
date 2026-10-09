from src import paths

print("正在初始化数据目录...")
try:
    root = paths.ensure_dirs()
    print(f"✅ 数据目录已就绪: {root}")
except Exception as e:
    print(f"❌ 创建失败: {e}")

print("\n完成！现在可以运行 main.py 了。")
