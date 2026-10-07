"""打包产物的启动自检：先运行 --self-check（依赖与数据目录），再启动程序确认页面能打开、数据库已创建，然后退出。

用法：python scripts/self_test.py <程序路径> [--timeout 秒]
不打开浏览器，使用临时数据目录和空闲端口；失败时打印程序输出并以非零退出码结束。
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    port = free_port()
    data = Path(tempfile.mkdtemp(prefix="renovel-selftest-")) / "data"
    log = data.parent / "app.log"
    env = dict(os.environ, RENOVEL_PORT=str(port), RENOVEL_SHOW="0", RENOVEL_DATA_DIR=str(data),
               PYTHONIOENCODING="utf-8")
    url = f"http://127.0.0.1:{port}/"
    check = subprocess.run([args.program, "--self-check"], env=env, capture_output=True, timeout=args.timeout)
    output = (check.stdout + check.stderr).decode("utf-8", "replace")
    print(output.strip())
    if check.returncode != 0 or "self-check ok" not in output:
        print(f"自检失败：--self-check 退出码 {check.returncode}")
        return 1

    print(f"启动 {args.program}（端口 {port}，数据目录 {data}）")
    with open(log, "wb") as out:
        proc = subprocess.Popen([args.program], env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + args.timeout
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"程序提前退出（退出码 {proc.returncode}）")
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        body = response.read().decode("utf-8", "replace")
                    if response.status == 200 and "Re:Novel" in body:
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError(f"{args.timeout:.0f} 秒内页面没有响应")
            database = data / "projects" / "novelforge.db"
            for _ in range(30):  # 数据库在启动回调里创建
                if database.exists():
                    break
                time.sleep(1)
            if not database.exists():
                raise RuntimeError(f"没有创建数据库 {database}")
            print(f"自检通过：{url} 响应正常，已创建 {database.name}")
            return 0
        except RuntimeError as error:
            print(f"自检失败：{error}")
            out.flush()
            print("----- 程序输出 -----")
            print(log.read_text(encoding="utf-8", errors="replace")[-5000:])
            return 1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
