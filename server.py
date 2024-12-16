import os
import re
import sys
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import List
from asyncio import Event
from asyncio.subprocess import Process
import asyncio
from pydantic import BaseModel

app = FastAPI(title="CoW管理服务")

# 模拟数据库
cows: dict[int, "CoW"] = {}


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"code": 404, "msg": "Not Found"}
    )


class CoW:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Status code indicating the state of the CoW.
        # 0 - 待登录
        # 1 - 工作中
        # -1 - 已死亡
        self._status_code = -1
        # List of URLs for login QR codes. Default is an empty list.
        self.qrcodes: List[str] = []
        # 是否关闭状态
        self._is_closed = False
        self._p: None | Process = None  # 子进程
        ## 日志
        self.log: str = ""
        # 自动清理发生时间
        self.auto_clear_datetime: datetime | None = None

    @classmethod
    async def create_cow(cls) -> "CoW":
        """在异步环境创建一个新实例，禁止直接调用类来创建"""
        cow = CoW()
        # 等待子进程创建完毕
        wait_login_event = Event()
        asyncio.create_task(cow._run(wait_login_event=wait_login_event))
        await wait_login_event.wait()
        return cow

    def _ensure_cow_popped(self):
        """清理字典"""
        if self.pid in cows: cows.pop(self.pid)
        print("cow popped", self.pid)

    async def close(self):
        """优雅关闭"""
        self._is_closed = True
        self._p and self._p.returncode is None and self._p.terminate()
        await asyncio.sleep(1)
        self._p and self._p.returncode is None and self._p.kill()
        try:
            self._p and self._p.returncode is None and await self._p.wait()
        except Exception as e:
            print(f"Error while waiting for process to terminate or kill: {e}")

        # 延迟清理字典
        delay_seconds = 300 if not os.environ.get("PYTHONUNBUFFERED") else 30
        asyncio.get_running_loop().call_later(delay_seconds, self._ensure_cow_popped)
        # 自动清发生的datetime
        self.auto_clear_datetime = self.auto_clear_datetime or datetime.now() + timedelta(seconds=delay_seconds)

    @property
    def pid(self):
        if self._p:
            return self._p.pid
        else:
            return -1

    @property
    def status_code(self) -> int:
        # 无效进程
        if not self._p:
            code = -1
        # 已死进程
        if self._p.returncode is not None:
            code = -1
        code = self._status_code
        return code

    @staticmethod
    async def _read_stream(stream, q: None | asyncio.Queue[str] = None):
        while True:
            line = await stream.readline()
            if not line:
                break
            if q:
                await q.put(line.decode().strip())

    async def _run(self, *, wait_login_event: Event | None = None):
        """实例化进程"""
        process = await asyncio.create_subprocess_exec(
            sys.executable, 'app.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # env={},
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
                if line == 'You can also scan QRCode in any website below:':
                    # 待登录
                    self._status_code = 0
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

                if self._status_code == 0:
                    pattern = (
                        r"\[INFO\]\["  # 固定部分 [INFO][
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\["  # 时间部分
                        r"wechat_channel\.py:\d+\] - "  # 文件名和行号
                        r"Wechat login success, user_id: @"  # 固定文本
                        r"[a-f0-9]+, nickname: .+"  # 用户ID和昵称部分
                    )
                    if re.fullmatch(pattern, line):
                        # 工作中
                        self._status_code = 1
                        self.qrcodes.clear()
                    # elif "Please press confirm on your phone." ==line:
                    #     self._status_code = -1

                # 已死亡
                if self._status_code == 1 and '''Unexpected sync check result: window.synccheck''' in line:
                    self._status_code = -1
                    break
        finally:
            await self.close()


class CowItem(BaseModel):
    cow_id: int
    status_code: int
    qrcodes: List[str]
    log: str
    auto_clear_datetime: datetime | None = None


class ResponseItem(BaseModel):
    code: int
    msg: str
    data: CowItem | List[CowItem] | None = None


@app.post("/cows/", summary="创建一个新的CoW", response_model=ResponseItem)
async def create_cow():  # ToDo 从config.json拿出一些参数作为请求参数
    """
    创建一个新的CoW进程实例。

    返回值: CoW id。
    """
    cow = await CoW.create_cow()
    cows[cow.pid] = cow
    return ResponseItem(code=200,
                        msg="success",
                        data=CowItem(cow_id=cow.pid,
                                     status_code=cow.status_code,
                                     qrcodes=cow.qrcodes,
                                     log=cow.log,
                                     auto_clear_datetime=cow.auto_clear_datetime))


@app.get("/cows/{cow_id}/", summary="获取CoW实例", response_model=ResponseItem)
def get_cow_status(cow_id: int):
    """
    获取指定CoW的运行状态。
    """
    if cow_id not in cows:
        raise HTTPException(status_code=404)

    return ResponseItem(code=200,
                        msg="success",
                        data=CowItem(cow_id=cows[cow_id].pid,
                                     status_code=cows[cow_id].status_code,
                                     qrcodes=cows[cow_id].qrcodes,
                                     log=cows[cow_id].log,
                                     auto_clear_datetime=cows[cow_id].auto_clear_datetime))


@app.get("/cows/", summary="获取所有CoW实例", response_model=ResponseItem)
async def get_cows():
    return ResponseItem(code=200,
                        msg="success",
                        data=[CowItem(cow_id=cow.pid,
                                      status_code=cow.status_code,
                                      qrcodes=cow.qrcodes,
                                      log=cow.log,
                                      auto_clear_datetime=cow.auto_clear_datetime) for cow in cows.values()])


@app.delete("/cows/{cow_id}/", summary="删除一个CoW实例")
async def delete_cow(cow_id: int):
    """
    删除一个CoW实例。
    """
    if cow_id not in cows:
        raise HTTPException(status_code=404)

    cow = cows[cow_id]
    await cow.close()
    del cows[cow_id]
    return ResponseItem(code=200, msg="success", data=None)
