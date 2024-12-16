import re
from fastapi import FastAPI, HTTPException
from typing import List
import subprocess
import threading
from threading import Event

app = FastAPI(title="CoW管理服务")

# 模拟数据库
cows = {}


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
        # 启动
        self._p: subprocess.Popen | None = None  # 子进程
        self._pid_event = Event()
        self._t: None | threading.Thread = threading.Thread(target=self._run)  # 子线程
        self._t.start()
        # 等待子线程中的子进程启动
        self._pid_event.wait()
        assert self._p

    def close(self):
        "优雅关闭"
        self._is_closed = True
        cows.pop(self.pid)
        self._p.kill()

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
            return -1
        # 已死进程
        if self._p.poll() is not None:
            return -1
        return self._status_code

    def _run(self):
        """实例化进程"""
        assert self._status_code == -1
        assert self.qrcodes == []

        if self._is_closed: return
        # 使用Popen启动子进程，并设置stdout为PIPE以捕获输出
        with subprocess.Popen(["python", "app.py"],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              cwd="./",
                              text=True) as process:
            self._p = process
            self._pid_event.set()
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
                    # 已死亡 todo 延时自动关闭
                    if self._status_code == 0 and '''Unexpected sync check result: window.synccheck={retcode:"1102",selector:"0"}''' in output:
                        self._status_code = -1
                        process.kill()
                        break


@app.post("/cow/", summary="创建一个新的CoW")
def create_cow():
    """
    创建一个新的CoW进程实例。

    返回值: CoW id。
    """
    cow = CoW()
    cows[cow.pid] = cow
    return cow.pid
