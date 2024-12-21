import asyncio
import json
import os
from app import run
from lib import itchat
from plugins import PluginManager

# from plugins.switch import Switch

server_path = os.environ.get("UNIX_SOCKET_PATH")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    msg = await reader.read(100)
    # addr = writer.get_extra_info('peername')
    # print(f"Received {message} from {addr}")

    data: bytes = b'{}'
    if msg == b"GET FRIENDS":
        friends = await asyncio.get_running_loop().run_in_executor(None, itchat.instance.get_friends)
        data = json.dumps(friends).encode()
    elif msg == b"SWITCH ON":
        plugins = PluginManager().list_plugins()
        plugins["SWITCH"].switch = True
    elif msg == b"SWITCH OFF":
        plugins = PluginManager().list_plugins()
        plugins["SWITCH"].switch = False
    # ToDo 聊天记录 ChatGPT bot实例.session.messages
    writer.write(data)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main():
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
        os.unlink(server_path)


if __name__ == '__main__':
    # 运行事件循环
    asyncio.run(main())
