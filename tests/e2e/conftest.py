"""冒烟测试夹具：启动假 LLM 服务和真实应用，用 Playwright 驱动浏览器。"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = Path(__file__).resolve().parent
ROLES = ["writer", "reviewer", "analyzer", "chat", "graph"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, proc: subprocess.Popen, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"进程提前退出 (code {proc.returncode}): {url}")
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"等待超时: {url}")


def _env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)  # 否则 NiceGUI 认为自己跑在 pytest 里而拒绝启动
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    env.update(extra or {})
    return env


def _start(args: list[str], cwd: Path, log: Path, env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, *args], cwd=cwd, env=_env(env),
        stdout=log.open("w"), stderr=subprocess.STDOUT, start_new_session=True,
    )


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)


@pytest.fixture(scope="session")
def fake_llm(tmp_path_factory):
    port = _free_port()
    workdir = tmp_path_factory.mktemp("fake_llm")
    proc = _start([str(HERE / "fake_llm.py"), str(port)], workdir, workdir / "fake_llm.log")
    url = f"http://127.0.0.1:{port}"
    _wait_http(f"{url}/v1/models", proc, timeout=30)
    yield url
    _stop(proc)


@dataclass
class App:
    url: str
    data_dir: Path
    log: Path

    def log_tail(self, lines: int = 40) -> str:
        return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])


@pytest.fixture(scope="module")
def app(fake_llm, tmp_path_factory):
    root = tmp_path_factory.mktemp("app")
    data = root / "data"
    for sub in ("projects", "models", "presets"):
        (data / sub).mkdir(parents=True)

    role = {"provider": "openai", "api_key": "sk-test", "base_url": f"{fake_llm}/v1",
            "model": "fake-model", "temperature": 0.7, "proxy": ""}
    config = {r: dict(role) for r in ROLES}
    config.update(enable_reviewer=True, review_threshold=8, review_mode="manual",
                  embedding={"provider": "api", "api_key": "sk-test", "base_url": f"{fake_llm}/v1",
                             "model": "fake-embedding"})
    (data / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    port = _free_port()
    log = root / "app.log"
    proc = _start([str(HERE / "run_app.py"), str(port)], root, log, env={"RENOVEL_DATA_DIR": str(data)})
    app = App(url=f"http://127.0.0.1:{port}/", data_dir=data, log=log)
    try:
        _wait_http(app.url, proc)
    except Exception:
        _stop(proc)
        raise RuntimeError(f"应用启动失败:\n{app.log_tail()}")
    yield app
    _stop(proc)


@pytest.fixture(scope="module")
def browser():
    # 按模块启停：sync_playwright 运行期间占用事件循环，会让其他测试里的 asyncio.run 报错
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, args=["--no-proxy-server"])
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(app, browser):
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.set_default_timeout(30_000)
    page.goto(app.url)
    page.wait_for_timeout(2000)
    yield page
    page.close()
