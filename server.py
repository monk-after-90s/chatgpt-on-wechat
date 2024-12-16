import re
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import List
from asyncio import Event
from asyncio.subprocess import Process
import asyncio

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

    @classmethod
    async def create_cow(cls) -> "CoW":
        """在异步环境创建一个新实例，禁止直接调用类来创建"""
        cow = CoW()
        # 等待子进程创建完毕
        process = await asyncio.create_subprocess_exec(
            sys.executable, 'app.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # env={},
            cwd="./"
        )
        cow._p = process
        asyncio.create_task(cow._run())
        return cow

    def close(self):
        "优雅关闭"
        self._is_closed = True
        cows.pop(self.pid)
        self._p.terminate()

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

    async def _run(self):
        """实例化进程"""
        try:
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

                # 已死亡 todo 延时自动关闭
                if self._status_code == 1 and '''Unexpected sync check result: window.synccheck={retcode:"1102",selector:"0"}''' in line:
                    self._status_code = -1
                    break
        finally:
            if self._p.returncode is None:  # If the process is still running
                self._p.terminate()  # You can also use kill() for a more forceful termination
                try:
                    await self._p.wait()
                except Exception as e:
                    print(f"Error while waiting for process to terminate: {e}")


@app.post("/cow/", summary="创建一个新的CoW")
async def create_cow():  # ToDo 从config.json拿出一些参数作为请求参数
    """
    创建一个新的CoW进程实例。

    返回值: CoW id。
    """
    cow = await CoW.create_cow()
    cows[cow.pid] = cow
    return {"code": 200, "msg": "success", "data": {"cow_id": cow.pid}}


@app.get("/cow/status/", summary="获取CoW的状态")
def get_cow_status(cow_id: int):
    """
    获取指定CoW的运行状态。
    """
    if cow_id not in cows:
        raise HTTPException(status_code=404)

    return {"code": 200,
            "msg": "success",
            "data": {"status": cows[cow_id].status_code, "qrcodes": cows[cow_id].qrcodes, "log": cows[cow_id].log}}
