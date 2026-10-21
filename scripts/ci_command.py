"""Run a CI check and expose its failure details in the public run annotations."""
from collections import deque
import subprocess
import sys


def main():
    process = subprocess.Popen(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace')
    tail = deque(maxlen=160)
    for line in process.stdout:
        print(line, end='', flush=True)
        tail.append(line)
    result = process.wait()
    if result:
        message = ''.join(tail)[-12000:]
        message = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Compiler validation failed::' + message, flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
