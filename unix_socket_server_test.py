import asyncio
import os


async def handle_client(reader, writer):
    data = await reader.read(100)
    message = data.decode()
    addr = writer.get_extra_info('peername')
    print(f"Received {message} from {addr}")

    print("Send: %r" % message)
    writer.write(data)
    await writer.drain()

    print("Close the client socket")
    writer.close()
    await writer.wait_closed()


async def main():
    server_path = './mysocket'
    try:
        # 如果旧的套接字文件存在，先移除它
        try:
            os.unlink(server_path)
        except OSError:
            if os.path.exists(server_path):
                raise

        # 创建新的 Unix 域套接字服务器
        server = await asyncio.start_unix_server(
            handle_client, server_path)

        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")


if __name__ == '__main__':
    # 运行事件循环
    asyncio.run(main())
