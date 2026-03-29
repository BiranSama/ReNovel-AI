import logging
import sys
from colorama import init, Fore, Style
from datetime import datetime
from typing import Optional

init(autoreset=True)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


class ConsoleLogger:
    _logger: Optional[logging.Logger] = None
    
    @classmethod
    def _get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = get_logger("ReNovel")
        return cls._logger

    @staticmethod
    def _time() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @classmethod
    def writer(cls, msg: str) -> None:
        print(f"{Fore.CYAN}[{cls._time()} WRITER] {Style.RESET_ALL}{msg}")
        cls._get_logger().info(f"[WRITER] {msg}")

    @classmethod
    def reviewer(cls, msg: str, passed: bool) -> None:
        color = Fore.GREEN if passed else Fore.RED
        status = "PASS" if passed else "FAIL"
        print(f"{color}[{cls._time()} REVIEW {status}] {Style.RESET_ALL}{msg}")
        cls._get_logger().info(f"[REVIEW {status}] {msg}")

    @classmethod
    def system(cls, msg: str) -> None:
        print(f"{Fore.YELLOW}[{cls._time()} SYSTEM] {Style.RESET_ALL}{msg}")
        cls._get_logger().info(f"[SYSTEM] {msg}")

    @classmethod
    def rag(cls, msg: str) -> None:
        print(f"{Fore.MAGENTA}[{cls._time()} MEMORY] {Style.RESET_ALL}{msg}")
        cls._get_logger().debug(f"[MEMORY] {msg}")

    @classmethod
    def block(cls, title: str, content: str) -> None:
        print(f"{Fore.WHITE}{'-'*20} {title} {'-'*20}")
        print(f"{Fore.LIGHTBLACK_EX}{content.strip()}")
        print(f"{Fore.WHITE}{'-'*50}")

    @classmethod
    def error(cls, msg: str, exc: Optional[Exception] = None) -> None:
        print(f"{Fore.RED}[{cls._time()} ERROR] {Style.RESET_ALL}{msg}")
        if exc:
            cls._get_logger().error(f"{msg}: {exc}", exc_info=True)
        else:
            cls._get_logger().error(msg)

    @classmethod
    def warning(cls, msg: str) -> None:
        print(f"{Fore.YELLOW}[{cls._time()} WARNING] {Style.RESET_ALL}{msg}")
        cls._get_logger().warning(msg)

    @classmethod
    def debug(cls, msg: str) -> None:
        cls._get_logger().debug(msg)

    @classmethod
    def info(cls, msg: str) -> None:
        cls._get_logger().info(msg)


Log = ConsoleLogger
