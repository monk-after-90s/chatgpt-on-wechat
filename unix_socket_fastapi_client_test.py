import aiohttp
import asyncio
import os

# 获取环境变量
server_path = os.environ.get("UNIX_SOCKET_PATH", "mysocket")


async def fetch_friends():
    async with aiohttp.UnixConnector(path=server_path) as connector:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get('http://unix/friends/') as response:
                fs = await response.json()
                print(fs)


async def switch_cow(switch: bool):
    async with aiohttp.UnixConnector(path=server_path) as connector:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post('http://unix/switch/', json={"switch": switch}) as response:
                # print(await response.text())
                switch = await response.json()
                print(switch)


async def main():
    await fetch_friends()
    await switch_cow(True)
    await switch_cow(False)


if __name__ == '__main__':
    asyncio.run(main())
