from colorama import init, Fore, Style
import datetime

# 初始化颜色引擎 (自动重置)
init(autoreset=True)

class ConsoleLogger:
    @staticmethod
    def _time():
        return datetime.datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def writer(msg: str):
        print(f"{Fore.CYAN}[{ConsoleLogger._time()} WRITER] {Style.RESET_ALL}{msg}")

    @staticmethod
    def reviewer(msg: str, passed: bool):
        color = Fore.GREEN if passed else Fore.RED
        status = "PASS" if passed else "FAIL"
        print(f"{color}[{ConsoleLogger._time()} REVIEW {status}] {Style.RESET_ALL}{msg}")

    @staticmethod
    def system(msg: str):
        print(f"{Fore.YELLOW}[{ConsoleLogger._time()} SYSTEM] {Style.RESET_ALL}{msg}")

    @staticmethod
    def rag(msg: str):
        print(f"{Fore.MAGENTA}[{ConsoleLogger._time()} MEMORY] {Style.RESET_ALL}{msg}")

    @staticmethod
    def block(title: str, content: str):
        print(f"{Fore.WHITE}{'-'*20} {title} {'-'*20}")
        print(f"{Fore.LIGHTBLACK_EX}{content.strip()}")
        print(f"{Fore.WHITE}{'-'*50}")