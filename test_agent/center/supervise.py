"""worker 意外消失时清理本进程组，避免留下一直写副本的测试/浏览器。"""

import os
import signal
import subprocess
import sys
import time


def main():
    parent_pid = int(sys.argv[1])
    child = subprocess.Popen(sys.argv[2:])
    while child.poll() is None:
        if os.getppid() != parent_pid:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(0.1)
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
