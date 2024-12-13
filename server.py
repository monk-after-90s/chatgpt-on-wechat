import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import subprocess
import threading

app = FastAPI(title="CoW管理服务")

# 模拟数据库
cows = {}


class CoW(BaseModel):
    """
    Represents a CoW (Cow) with specific attributes.

    Attributes:
        pid (int): Process ID of the CoW. Default is -1.
        status_code (int): Status code indicating the state of the CoW.
            0 - 待登录
            1 - 工作中
            -1 - 已死亡
        qrcodes (List[str]): List of URLs for login QR codes. Default is an empty list.
    """
    pid: int = -1
    # status_code: int = -1
    qrcodes: List[str] = Field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._status_code = -1
        # 在子线程启动子进程初始化
        self._p: subprocess.Popen | None = None
        self._t = threading.Thread(target=self._run)
        # 是否关闭状态
        self._is_closed = False

    def close(self):
        "优雅关闭"
        self._is_closed = True
        self._p.kill()

    @property
    def status_code(self) -> int:
        # 无效进程
        if self.pid == -1:
            return -1
        # 已死进程
        if self._p.poll() is not None:
            return -1
        return self._status_code

    def _run(self):
        """实例化进程"""
        assert self.pid == -1
        assert self._status_code == -1
        assert self.qrcodes == []

        if self._is_closed: return
        # 使用Popen启动子进程，并设置stdout为PIPE以捕获输出
        with subprocess.Popen(["python", "app.py"],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              cwd="./",
                              text=True) as process:
            self.pid = process.pid
            self._p = process
            # 实时读取标准输出
            meet_qrcode = False
            while True:
                stdout = process.stdout.readline()
                stdout = stdout.strip()
                stderr = process.stderr.readline()
                stderr = stderr.strip()
                assert not (stdout and stderr)
                output = stdout or stderr

                if process.poll() is not None:
                    break
                if output:
                    output = output.strip()
                    print(output)
                    ################状态更新区################
                    if output == 'You can also scan QRCode in any website below:':
                        # 待登录
                        self._status_code = 0
                        # 捕获连续的二维码链接
                        meet_qrcode = True
                        self.qrcodes.clear()
                    elif meet_qrcode and output.startswith('https://'):
                        # 捕获连续的二维码链接
                        self.qrcodes.append(output)
                    else:
                        # 连续的二维码链接结束
                        meet_qrcode = False
                    # 工作中
                    if self._status_code == 0:
                        pattern = (
                            r"\[INFO\]\["  # 固定部分 [INFO][
                            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\["  # 时间部分
                            r"wechat_channel\.py:\d+\] - "  # 文件名和行号
                            r"Wechat login success, user_id: @"  # 固定文本
                            r"[a-f0-9]+, nickname: .+"  # 用户ID和昵称部分
                        )
                        if re.fullmatch(pattern, output):
                            self._status_code = 1
                    # 已死亡
                    if self._status_code == 0 and '''Unexpected sync check result: window.synccheck={retcode:"1102",selector:"0"}''' in output:
                        self._status_code = -1
                        process.kill()
                        break
            # 捕获任何可能的标准错误输出
            stderr = process.stderr.read()
            if stderr:
                print("标准错误:", stderr)


@app.post("/cows/", response_model=CoW, summary="创建一个新的CoW")
def create_cow():
    """
    创建一个新的CoW进程实例。

    返回值:
        CoW: 创建的CoW对象。
    """

    return cow


@app.get("/cows/{pid}", response_model=CoW, summary="通过PID获取CoW信息")
def read_cow(pid: int):
    """
    通过进程ID获取CoW条目。

    参数:
        pid (int): CoW的进程ID。

    返回值:
        CoW: 对应的CoW对象。
    """
    if pid not in cows:
        raise HTTPException(status_code=404, detail="CoW未找到")
    return cows[pid]


@app.put("/cows/{pid}", response_model=CoW, summary="通过PID更新CoW信息")
def update_cow(pid: int, cow: CoW):
    """
    通过进程ID更新现有的CoW条目。

    参数:
        pid (int): CoW的进程ID。
        cow (CoW): 更新后的CoW对象。

    返回值:
        CoW: 更新后的CoW对象。
    """
    if pid not in cows:
        raise HTTPException(status_code=404, detail="CoW未找到")
    cows[pid] = cow
    return cow


@app.delete("/cows/{pid}", summary="通过PID删除CoW")
def delete_cow(pid: int):
    """
    通过进程ID删除CoW条目。

    参数:
        pid (int): CoW的进程ID。

    返回值:
        dict: 成功删除的消息。
    """
    if pid not in cows:
        raise HTTPException(status_code=404, detail="CoW未找到")
    del cows[pid]
    return {"detail": "CoW已删除"}


@app.get("/cows/", response_model=List[CoW], summary="列出所有CoW")
def list_cows():
    """
    列出数据库中的所有CoW条目。

    返回值:
        List[CoW]: 所有CoW对象的列表。
    """
    return list(cows.values())
