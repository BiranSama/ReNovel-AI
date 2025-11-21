import os

# 需要创建的目录列表
folders = [
    "data/projects",
    "data/vectordb",
    "data/presets",
]

print("正在初始化数据目录...")
for folder in folders:
    try:
        os.makedirs(folder, exist_ok=True)
        print(f"✅ 文件夹已就绪: {folder}")
    except Exception as e:
        print(f"❌ 创建失败 {folder}: {e}")

print("\n完成！现在可以运行 main.py 了。")
