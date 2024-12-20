import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import aiohttp
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from asyncio import Event
from asyncio.subprocess import Process
import asyncio
from typing import List

from common.models import Model404, Model400, StatusCodeEnum, CowItem, CoWConfig, ResponseItem, WX, ContactInfo


# todo 用户久不回的主动提醒，插件？
@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        shutil.rmtree("./sockets")
    except OSError:
        pass
    yield
    # 删除文件夹sockets
    print("Try to delete sockets folder...")
    try:
        shutil.rmtree("./sockets")
    except OSError:
        pass


app = FastAPI(title="CoW（chatgpt-on-wechat）管理服务", lifespan=lifespan)

# 模拟数据库
cows: dict[int, "CoW"] = {}


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content=Model404().model_dump()
    )


@app.exception_handler(400)
async def custom_400_handler(request: Request, exc):
    return JSONResponse(
        status_code=400,
        content=Model400().model_dump()
    )


class CoW:
    def __init__(self, ai_name):
        # Status code indicating the state of the CoW.
        # 0 - 待登录
        # 1 - 工作中
        # -1 - 已死亡
        self._status_code: StatusCodeEnum = StatusCodeEnum.DEAD
        # List of URLs for login QR codes. Default is an empty list.
        self.qrcodes: List[str] = []
        # 是否关闭状态
        self._is_closed = False
        self._p: None | Process = None  # 子进程
        ## 日志
        self.log: str = ""
        # 自动清理发生时间
        self.auto_clear_datetime: datetime | None = None
        # 套接字服务路径
        self._unix_socket_path: str | Path = ''
        # unix请求环境
        # async with aiohttp.UnixConnector(path=server_path) as connector:
        #     async with aiohttp.ClientSession(connector=connector) as session:
        self._unix_connector: None | aiohttp.UnixConnector = None
        self._client_session: None | aiohttp.ClientSession = None
        # 微信昵称
        self.wx_nickname: str = ""
        # 智能体/大语言模型名称
        self.ai_name: str = ai_name

    async def wx_friends(self) -> List[dict]:
        """获取微信好友列表"""
        if self._client_session.closed: return []
        async with self._client_session.get('http://unix/friends/') as response:
            fs = await response.json()
            return fs

    @classmethod
    async def create_cow(cls, ai_name: str, envs: None | dict = None) -> "CoW":
        """在异步环境创建一个新实例，禁止直接调用类来创建"""
        cow = CoW(ai_name=ai_name)
        # 等待子进程创建完毕
        wait_login_event = Event()
        asyncio.create_task(cow._run(envs, wait_login_event=wait_login_event))
        await wait_login_event.wait()
        return cow

    def _ensure_cow_popped(self):
        """清理字典"""
        if self.pid in cows: cows.pop(self.pid)
        print("cow popped", self.pid)

    async def close(self):
        """优雅关闭"""

        # unix连接清理
        async def clear_unix_socket():
            if self._client_session: await self._client_session.close()
            if self._unix_connector: await self._unix_connector.close()
            if os.path.exists(self._unix_socket_path): os.unlink(self._unix_socket_path)

        unix_clear_task = asyncio.create_task(clear_unix_socket())
        # 进程清理
        self._is_closed = True
        self._p and self._p.returncode is None and self._p.terminate()
        await asyncio.sleep(1)
        self._p and self._p.returncode is None and self._p.kill()  # todo 检查子进程死亡情况
        try:
            self._p and self._p.returncode is None and await self._p.wait()
        except Exception as e:
            print(f"Error while waiting for process to terminate or kill: {e}")

        # 延迟清理字典
        delay_seconds = 300 if not os.environ.get("PYTHONUNBUFFERED") else 30
        asyncio.get_running_loop().call_later(delay_seconds, self._ensure_cow_popped)
        # 自动清发生的datetime
        self.auto_clear_datetime = \
            self.auto_clear_datetime or datetime.now().astimezone() + timedelta(seconds=delay_seconds)

        # 调试
        if os.environ.get("PYTHONUNBUFFERED") == "1":
            await unix_clear_task
            return

    @property
    def pid(self):
        if self._p:
            return self._p.pid
        else:
            return -1

    @property
    def status_code(self) -> "StatusCodeEnum":
        # 无效进程
        if not self._p:
            return StatusCodeEnum.DEAD
        # 已死进程
        if self._p.returncode is not None:
            return StatusCodeEnum.DEAD
        return self._status_code

    @status_code.setter
    def status_code(self, status_code: "StatusCodeEnum"):
        self._status_code = status_code
        if status_code == StatusCodeEnum.DEAD:
            asyncio.create_task(self.close())
        elif status_code == StatusCodeEnum.WORKING:  # 切换到工作中
            asyncio.create_task(self._switch_cow_in_process(True))
        elif status_code == StatusCodeEnum.WORKING_BUT_PAUSE:  # 切换到工作中的暂停
            asyncio.create_task(self._switch_cow_in_process(False))

    async def _switch_cow_in_process(self, switch: bool):
        if self._client_session.closed: return
        async with self._client_session.post('http://unix/switch/', json={"switch": switch}) as response:
            await response.json()

    @staticmethod
    async def _read_stream(stream, q: None | asyncio.Queue[str] = None):
        while True:
            line = await stream.readline()
            if not line:
                break
            if q:
                await q.put(line.decode().strip())

    async def _close_when_wait_login_too_long(self):
        await asyncio.sleep(600 if os.environ.get("PYTHONUNBUFFERED") == "" else 60)
        # 状态检查
        if self.status_code == StatusCodeEnum.TO_LOGIN:
            await self.close()

    async def _run(self, envs: dict | None = None, *, wait_login_event: Event | None = None):
        """实例化进程"""
        # 将 None 替换为空字符串，并确保所有值都是字符串
        envs_cleaned = {k: str(v) if v is not None else "" for k, v in envs.items()}

        # 确保布尔值和整数值也被转换为字符串
        envs_cleaned = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in envs_cleaned.items()}
        envs_cleaned = {k: str(v) if isinstance(v, int) else v for k, v in envs_cleaned.items()}

        # 列表类型的值需要转换为逗号分隔的字符串
        envs_cleaned = {k: ",".join(v) if isinstance(v, list) else v for k, v in envs_cleaned.items()}
        # 套接字路径
        path = Path("./sockets")
        path.mkdir(parents=True, exist_ok=True)
        self._unix_socket_path = path / str(uuid.uuid4())
        envs_cleaned["UNIX_SOCKET_PATH"] = str(self._unix_socket_path)
        # unix socket 客户端初始化
        self._unix_connector = aiohttp.UnixConnector(path=str(self._unix_socket_path))
        self._client_session = aiohttp.ClientSession(connector=self._unix_connector)
        process = await asyncio.create_subprocess_exec(
            sys.executable, 'sub_unix_socket_server.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=envs_cleaned,
            cwd="./"
        )
        try:
            self._p = process

            q = asyncio.Queue()
            asyncio.create_task(self._read_stream(self._p.stdout, q))
            asyncio.create_task(self._read_stream(self._p.stderr, q))
            # 实时读取标准输出
            meet_qrcode = False
            while True:
                line = await q.get()
                # 更新日志
                self.log += line + "\n"
                self.log = self.log[-10000:]
                ################状态更新区################
                if os.getenv("PYTHONUNBUFFERED") == "1":
                    print(line.strip())
                if line == 'You can also scan QRCode in any website below:':
                    # 待登录
                    self._status_code = StatusCodeEnum.TO_LOGIN
                    # 久不登录就关闭
                    asyncio.create_task(self._close_when_wait_login_too_long())

                    # 捕获连续的二维码链接
                    meet_qrcode = True
                    self.qrcodes.clear()

                    if wait_login_event:
                        wait_login_event.set()
                elif meet_qrcode and line.startswith('https://'):
                    # 捕获连续的二维码链接
                    self.qrcodes.append(line)
                else:
                    # 连续的二维码链接结束
                    meet_qrcode = False

                if self._status_code == StatusCodeEnum.TO_LOGIN:
                    # Define the regex pattern to match the entire log entry and capture the nickname
                    pattern = (
                        r"\[INFO\]\["  # 固定部分 [INFO][
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\["  # 时间部分
                        r"wechat_channel\.py:\d+\] - "  # 文件名和行号
                        r"Wechat login success, user_id: @"  # 固定文本
                        r"[a-f0-9]+, nickname: (.+)"  # 用户ID和昵称部分，捕获昵称
                    )

                    # Search for the pattern in the log string
                    match = re.search(pattern, line)

                    if match:
                        # print(f"{line=}")
                        self.wx_nickname = match.group(1)
                        # 工作中
                        self._status_code = StatusCodeEnum.WORKING
                        self.qrcodes.clear()
                # 已死亡
                if self._status_code == StatusCodeEnum.WORKING and '''Unexpected sync check result: window.synccheck''' in line:
                    pattern = r'Unexpected sync check result: window\.synccheck=\{retcode:"(\d+)",selector:"(\d+)"\}'
                    match = re.search(pattern, line)
                    if match:
                        self._status_code = StatusCodeEnum.DEAD
                        break
        finally:
            await self.close()


@app.post("/cows/", summary="创建一个新的CoW", response_model=ResponseItem)
async def create_cow(cow_config: CoWConfig,
                     ai_name: str = Query("", title="AI Name", description="对接的智能体或者大语言模型名字")):
    """
    创建一个新的CoW进程实例。通常只需要传**open_ai_api_key**、**open_ai_api_base**和**model**。对于智能体平台如fastgpt则不需要**model**。
    各参数解释详见请求体Schema各字段解释，或者查看[chatgpt-on-wechat config.py文件](https://github.com/zhayujie/chatgpt-on-wechat/blob/16324e72837b9898dfaca76897cdcdb27044dc06/config.py#L13)。
    """
    # /v1结尾确认
    cow_config.open_ai_api_base = cow_config.open_ai_api_base.rstrip('/')  # 去掉尾部的斜杠
    if not cow_config.open_ai_api_base.endswith('/v1'):
        cow_config.open_ai_api_base = cow_config.open_ai_api_base + '/v1'  # 确保以 /api/v1 结尾

    cow = await CoW.create_cow(ai_name, cow_config.model_dump())
    cows[cow.pid] = cow
    friends = await cow.wx_friends()
    fs: List[ContactInfo] = [ContactInfo(**f) for f in friends]
    return ResponseItem(code=200,
                        msg="success",
                        data=CowItem(cow_id=cow.pid,
                                     status_code=cow.status_code,
                                     wx=WX(wx_nickname=cow.wx_nickname,
                                           head_img_url=fs[0].HeadImgUrl if fs else "",
                                           friends=fs),
                                     qrcodes=cow.qrcodes,
                                     log=cow.log,
                                     ai_name=ai_name,
                                     auto_clear_datetime=cow.auto_clear_datetime))


@app.get("/cows/{cow_id}/", summary="获取CoW实例",
         responses={
             "200": {"description": "取得目标CoW", "model": ResponseItem},
             "404": {"description": "未找到目标CoW", "model": Model404}
         })
async def get_cow_status(cow_id: int):
    """
    获取指定CoW的运行信息。
    """
    if cow_id not in cows:
        raise HTTPException(status_code=404)

    friends = await cows[cow_id].wx_friends()
    fs: List[ContactInfo] = [ContactInfo(**f) for f in friends]
    return ResponseItem(code=200,
                        msg="success",
                        data=CowItem(cow_id=cows[cow_id].pid,
                                     status_code=cows[cow_id].status_code,
                                     wx=WX(wx_nickname=cows[cow_id].wx_nickname,
                                           head_img_url=fs[0].HeadImgUrl if fs else "",
                                           friends=fs),
                                     qrcodes=cows[cow_id].qrcodes,
                                     log=cows[cow_id].log,
                                     ai_name=cows[cow_id].ai_name,
                                     auto_clear_datetime=cows[cow_id].auto_clear_datetime))


@app.get("/cows/", summary="获取所有CoW实例", response_model=ResponseItem)
async def get_cows():
    """
    响应格式详看响应体Schema。
    """

    async def generate_cow_item(_cow):
        friends = await _cow.wx_friends()
        fs: List[ContactInfo] = [ContactInfo(**f) for f in friends]
        return CowItem(cow_id=_cow.pid,
                       status_code=_cow.status_code,
                       wx=WX(wx_nickname=_cow.wx_nickname,
                             head_img_url=fs[0].HeadImgUrl if fs else "",
                             friends=fs),
                       qrcodes=_cow.qrcodes,
                       log=_cow.log,
                       ai_name=_cow.ai_name,
                       auto_clear_datetime=_cow.auto_clear_datetime)

    return ResponseItem(code=200,
                        msg="success",
                        data=[await task for task in
                              [asyncio.create_task(generate_cow_item(cow)) for cow in cows.values()]])


@app.delete("/cows/{cow_id}/", summary="删除一个CoW实例", responses={
    "200": {"description": "取得目标CoW", "model": ResponseItem},
    "404": {"description": "未找到目标CoW", "model": Model404}
})
async def delete_cow(cow_id: int):
    """
    立即删除并清理一个CoW实例。
    """
    if cow_id not in cows:
        raise HTTPException(status_code=404)

    cow = cows[cow_id]
    await cow.close()
    del cows[cow_id]
    return ResponseItem(code=200, msg="success", data=None)


# todo 聊天记录列表和实时聊天推送

# PATCH：部分更新资源
@app.patch("/cows/{cow_id}/", summary="更新一个CoW实例", responses={
    "200": {"description": "取得目标CoW", "model": ResponseItem},
    "404": {"description": "未找到目标CoW", "model": Model404}
})
async def update_cow(cow_id: int, cow_item: CowItem):
    """
    更新一个CoW实例的配置。
    目前只实现了更新属性status_code在1和2之间的切换。todo 实际对聊天的影响
    """
    # 目前只支持更新属性status_code在WORKING_BUT_PAUSE和WORKING之间切换
    status_code = cow_item.status_code
    if status_code in [StatusCodeEnum.WORKING_BUT_PAUSE, StatusCodeEnum.WORKING]:
        if cows[cow_id].status_code != status_code: cows[cow_id].status_code = status_code
        friends = await cows[cow_id].wx_friends()
        fs: List[ContactInfo] = [ContactInfo(**f) for f in friends]
        return ResponseItem(code=200,
                            msg="success",
                            data=CowItem(cow_id=cows[cow_id].pid,
                                         status_code=cows[cow_id].status_code,
                                         wx=WX(wx_nickname=cows[cow_id].wx_nickname,
                                               head_img_url=fs[0].HeadImgUrl if fs else "",
                                               friends=fs),
                                         qrcodes=cows[cow_id].qrcodes,
                                         log=cows[cow_id].log,
                                         ai_name=cows[cow_id].ai_name,
                                         auto_clear_datetime=cows[cow_id].auto_clear_datetime))
    else:
        raise HTTPException(status_code=400)
