import asyncio
import json
import os
from app import run
from lib import itchat

server_path = './mysocket'


async def handle_client(reader, writer):
    data = await reader.read(100)
    message = data.decode()
    addr = writer.get_extra_info('peername')
    print(f"Received {message} from {addr}")

    friends = await asyncio.get_running_loop().run_in_executor(None, itchat.instance.get_friends)
    fs = json.dumps(friends)
    print("Send: %r" % fs)
    writer.write(fs.encode())
    await writer.drain()

    print("Close the client socket")
    writer.close()
    await writer.wait_closed()


async def server():
    try:
        # 如果旧的套接字文件存在，先移除它
        try:
            os.unlink(server_path)
        except OSError:
            if os.path.exists(server_path):
                raise
        # 运行CoW在子线程
        f: asyncio.Future = asyncio.get_running_loop().run_in_executor(None, run)

        # 创建新的 Unix 域套接字服务器
        server = await asyncio.start_unix_server(
            handle_client, server_path)

        async with server:
            await server.serve_forever()
            await f
    except Exception as e:
        print(f"Server error: {e}")


async def main():
    await server()


if __name__ == '__main__':
    # 运行事件循环
    asyncio.run(main())
