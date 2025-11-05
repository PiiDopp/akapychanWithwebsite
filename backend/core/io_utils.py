import sys
import itertools
import time
from typing import Optional

class ThinkingDots:
    def __init__(self, message="思考中"):
        self.message = message
        self.done = False
        self.thread = None

    def animate(self):
        for c in itertools.cycle([".", "..", "...", "...."]):
            if self.done:
                break
            sys.stdout.write(f"\r{self.message}{c}   ")
            sys.stdout.flush()
            time.sleep(0.5)

    def start(self):
        import threading
        self.thread = threading.Thread(target=self.animate, daemon=True)
        self.thread.start()

    def stop(self):
        self.done = True
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()


def ask_input(prompt: str, default: Optional[str] = None) -> str:
    reply = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return reply if reply else (default or "")
