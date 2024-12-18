import asyncio
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from app import run

from common.utils import redirect_and_run


async def main():
    loop = asyncio.get_event_loop()
    parent_conn, child_conn = multiprocessing.Pipe()

    with ProcessPoolExecutor() as executor:
        f = loop.run_in_executor(executor, redirect_and_run, child_conn, run)

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
