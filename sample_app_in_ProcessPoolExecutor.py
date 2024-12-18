import asyncio
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import time


def run():
    a = 0
    while True:
        print("hello world")
        time.sleep(1)
        a += 1


def redirect_and_run(pipe):
    # 在函数内部导入 sys 模块，确保子进程环境中有该模块
    import sys

    # 替换标准输出和标准错误
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    class PipeWriter:
        def __init__(self, pipe):
            self.pipe = pipe

        def write(self, message):
            self.pipe.send(message)

        def flush(self):
            pass  # 不需要实现 flush

    try:
        sys.stdout = PipeWriter(pipe)
        sys.stderr = PipeWriter(pipe)
        run()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


async def main():
    loop = asyncio.get_event_loop()
    parent_conn, child_conn = multiprocessing.Pipe()

    with ProcessPoolExecutor() as executor:
        f = loop.run_in_executor(executor, redirect_and_run, child_conn)

        while not f.done():
            await asyncio.sleep(0)  # 防止事件循环阻塞

            while parent_conn.poll():  # 检查是否有数据可读
                message = parent_conn.recv()
                print(message, end='')  # 实时打印子进程的标准输出

        # # 确保获取最后的日志
        # while parent_conn.poll():
        #     message = parent_conn.recv()
        #     print(message, end='')


if __name__ == '__main__':
    asyncio.run(main())
