import asyncio


async def unix_domain_socket_client(message, path):
    reader, writer = await asyncio.open_unix_connection(path)

    print(f'Send: {message}')
    writer.write(message.encode())
    await writer.drain()

    data = await reader.read(32768)
    print(f'Received: {data.decode()}')

    print('Close the socket')
    writer.close()
    await writer.wait_closed()


async def main():
    server_path = './mysocket'  # 这应该与服务器端的路径一致
    message = 'SWITCH ON'

    try:
        await unix_domain_socket_client(message, server_path)
    except Exception as e:
        print(f"Client error: {e}")


if __name__ == '__main__':
    # 运行事件循环
    asyncio.run(main())
