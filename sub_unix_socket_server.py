import asyncio
import json
import os
from app import run
from common.models import SwitchItem
from lib import itchat
from plugins import PluginManager
from fastapi import FastAPI
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    f: asyncio.Future | None = None
    try:
        # 如果旧的套接字文件存在，先移除它
        try:
            os.unlink(server_path)
        except OSError:
            if os.path.exists(server_path):
                raise
        # 运行CoW在子线程
        f: asyncio.Future = asyncio.get_running_loop().run_in_executor(None, run)
    except Exception as e:
        print(f"Server error: {e}")
        os.unlink(server_path)
    yield
    if f: f.set_exception(Exception("Server stopped"))


app = FastAPI(lifespan=lifespan)

server_path = os.environ.get("UNIX_SOCKET_PATH")


@app.get("/friends/")
async def friends():
    """
    Get friends list
    """
    fs = await asyncio.get_running_loop().run_in_executor(None, itchat.instance.get_friends)
    return fs


@app.post("/switch/")
async def switch(switch_item: SwitchItem):
    """
    Switch CoW between ON and OFF
    """
    plugins = PluginManager().list_plugins()
    plugins["SWITCH"].switch = switch_item.switch
    return plugins["SWITCH"].switch


# ToDo 聊天记录 ChatGPT bot实例.session.messages

if __name__ == '__main__':
    # 运行事件循环
    # asyncio.run(main())
    import uvicorn

    uvicorn.run(app, uds=server_path)
