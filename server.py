import os
import re
import sys
from datetime import datetime, timedelta
from enum import Enum

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from asyncio import Event
from asyncio.subprocess import Process
import asyncio
from pydantic import BaseModel, Field
from typing import List, Optional

app = FastAPI(title="CoW（chatgpt-on-wechat）管理服务")

# 模拟数据库
cows: dict[int, "CoW"] = {}


class Model404(BaseModel):
    msg: str = Field(default="Not Found")
    code: int = Field(default=404)


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content=Model404().model_dump()
    )


class CoW:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

    @classmethod
    async def create_cow(cls, envs: None | dict = None) -> "CoW":
        """在异步环境创建一个新实例，禁止直接调用类来创建"""
        cow = CoW()
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
        self.auto_clear_datetime = \
            self.auto_clear_datetime or datetime.now().astimezone() + timedelta(seconds=delay_seconds)

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

    @staticmethod
    async def _read_stream(stream, q: None | asyncio.Queue[str] = None):
        while True:
            line = await stream.readline()
            if not line:
                break
            if q:
                await q.put(line.decode().strip())

    async def _run(self, envs: dict | None = None, *, wait_login_event: Event | None = None):
        """实例化进程"""
        # 将 None 替换为空字符串，并确保所有值都是字符串
        envs_cleaned = {k: str(v) if v is not None else "" for k, v in envs.items()}

        # 确保布尔值和整数值也被转换为字符串
        envs_cleaned = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in envs_cleaned.items()}
        envs_cleaned = {k: str(v) if isinstance(v, int) else v for k, v in envs_cleaned.items()}

        # 列表类型的值需要转换为逗号分隔的字符串
        envs_cleaned = {k: ",".join(v) if isinstance(v, list) else v for k, v in envs_cleaned.items()}

        process = await asyncio.create_subprocess_exec(
            sys.executable, 'app.py',
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
                if line == 'You can also scan QRCode in any website below:':
                    # 待登录
                    self._status_code = StatusCodeEnum.TO_LOGIN
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
                    pattern = (
                        r"\[INFO\]\["  # 固定部分 [INFO][
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\["  # 时间部分
                        r"wechat_channel\.py:\d+\] - "  # 文件名和行号
                        r"Wechat login success, user_id: @"  # 固定文本
                        r"[a-f0-9]+, nickname: .+"  # 用户ID和昵称部分
                    )
                    if re.fullmatch(pattern, line):
                        # 工作中
                        self._status_code = StatusCodeEnum.WORKING
                        self.qrcodes.clear()
                    # elif "Please press confirm on your phone." ==line:
                    #     self._status_code = -1

                # 已死亡
                if self._status_code == StatusCodeEnum.WORKING and '''Unexpected sync check result: window.synccheck''' in line:
                    pattern = r'Unexpected sync check result: window\.synccheck=\{retcode:"(\d+)",selector:"(\d+)"\}'
                    match = re.search(pattern, line)
                    if match:
                        self._status_code = StatusCodeEnum.DEAD
                        break
        finally:
            await self.close()


# 使用 Enum 定义 status_code 的合法值
class StatusCodeEnum(int, Enum):
    DEAD = -1  # 已死亡
    TO_LOGIN = 0  # 待登录
    WORKING = 1  # 工作中


class CowItem(BaseModel):
    cow_id: int = Field(..., description="CoW id")
    status_code: StatusCodeEnum = Field(..., description="CoW实例状态码：-1 已死亡，0 待登录，1 工作中")
    qrcodes: List[str] = Field(default_factory=list, description="二维码链接列表，用于手机微信扫码登录")
    log: str = Field("", description="日志")
    auto_clear_datetime: datetime | None = Field(None, description="已死亡CoW实例的自动清理时间")


class CoWConfig(BaseModel):
    # openai api配置
    open_ai_api_key: str = Field("", description="OpenAI API兼容的LLM服务的Api Key")
    open_ai_api_base: str = Field("https://api.openai.com/v1",
                                  description="OpenAI API兼容的LLM服务的base URL，以“/v1”结尾")
    proxy: Optional[str] = Field(None, description="Proxy for OpenAI requests")

    # chatgpt模型
    model: str = Field("", description="ChatGPT model")
    bot_type: Optional[str] = Field("chatGPT", description="Bot type if using a compatible service")
    use_azure_chatgpt: bool = Field(False, description="Whether to use Azure ChatGPT")
    azure_deployment_id: Optional[str] = Field(None, description="Azure deployment ID")
    azure_api_version: Optional[str] = Field(None, description="Azure API version")

    # Bot触发配置
    single_chat_prefix: List[str] = Field([""], description="Prefixes in private chats to trigger the bot")
    single_chat_reply_prefix: str = Field("", description="Prefix in private replies")
    single_chat_reply_suffix: str = Field("", description="Suffix in private replies")
    group_chat_prefix: List[str] = Field(["@bot"], description="Prefixes in group chats to trigger the bot")
    no_need_at: bool = Field(False, description="Whether to not @ the bot in group replies")
    group_chat_reply_prefix: str = Field("", description="Prefix in group replies")
    group_chat_reply_suffix: str = Field("", description="Suffix in group replies")
    group_chat_keyword: List[str] = Field([], description="Keywords in group chats to trigger the bot")
    group_at_off: bool = Field(False, description="Whether to disable triggering by @bot in groups")
    group_name_white_list: List[str] = Field(["ALL_GROUP"],
                                             description="List of group names where auto-reply is enabled")
    group_name_keyword_white_list: List[str] = Field([],
                                                     description="Keyword list of group names where auto-reply is enabled")
    group_chat_in_one_session: List[str] = Field(["ChatGPT测试群"],
                                                 description="Groups supporting session context sharing")
    nick_name_black_list: List[str] = Field([], description="Blacklist of user nicknames")
    group_welcome_msg: Optional[str] = Field(None, description="Fixed welcome message for new members")
    trigger_by_self: bool = Field(False, description="Whether the bot can trigger itself")
    text_to_image: str = Field("dall-e-2", description="Image generation model")

    # Azure OpenAI dall-e-3 配置
    dalle3_image_style: str = Field("vivid", description="Style for DALL-E 3 images")
    dalle3_image_quality: str = Field("hd", description="Quality for DALL-E 3 images")

    # Azure OpenAI DALL-E API 配置
    azure_openai_dalle_api_base: Optional[str] = Field(None, description="Endpoint for Azure OpenAI DALL-E API")
    azure_openai_dalle_api_key: Optional[str] = Field(None, description="Key for Azure OpenAI DALL-E API")
    azure_openai_dalle_deployment_id: Optional[str] = Field(None,
                                                            description="Deployment ID for Azure OpenAI DALL-E API")

    image_proxy: bool = Field(True, description="Whether to use image proxy")
    image_create_prefix: List[str] = Field([], description="Prefixes to enable image creation")
    concurrency_in_session: int = Field(1, description="Max concurrent messages per session")
    image_create_size: str = Field("256x256", description="Size of generated images")

    group_chat_exit_group: bool = Field(False, description="Whether to exit group on certain conditions")

    # chatgpt会话参数
    expires_in_seconds: int = Field(3600, description="Session expiration time without activity")

    # 人格描述
    character_desc: str = Field(
        "",
        description="Character description for the bot")

    conversation_max_tokens: int = Field(1000, description="Max tokens for conversation history")

    # chatgpt限流配置
    rate_limit_chatgpt: int = Field(20, description="Rate limit for ChatGPT calls")
    rate_limit_dalle: int = Field(50, description="Rate limit for DALL-E calls")

    # chatgpt api参数
    temperature: float = Field(0.9, description="Temperature parameter for ChatGPT")
    top_p: float = Field(1, description="Top-p parameter for ChatGPT")
    frequency_penalty: float = Field(0, description="Frequency penalty for ChatGPT")
    presence_penalty: float = Field(0, description="Presence penalty for ChatGPT")
    request_timeout: int = Field(180, description="Request timeout for ChatGPT")
    timeout: int = Field(120, description="Retry timeout for ChatGPT")

    # Baidu 文心一言参数
    baidu_wenxin_model: str = Field("eb-instant", description="Baidu Wenxin model")
    baidu_wenxin_api_key: Optional[str] = Field(None, description="Baidu API key")
    baidu_wenxin_secret_key: Optional[str] = Field(None, description="Baidu secret key")
    baidu_wenxin_prompt_enabled: bool = Field(False, description="Enable prompt for ERNIE models")

    # 讯飞星火API
    xunfei_app_id: Optional[str] = Field(None, description="Xunfei app ID")
    xunfei_api_key: Optional[str] = Field(None, description="Xunfei API key")
    xunfei_api_secret: Optional[str] = Field(None, description="Xunfei API secret")
    xunfei_domain: Optional[str] = Field(None, description="Xunfei domain")
    xunfei_spark_url: Optional[str] = Field(None, description="Xunfei Spark URL")

    # claude 配置
    claude_api_cookie: Optional[str] = Field(None, description="Claude API cookie")
    claude_uuid: Optional[str] = Field(None, description="Claude UUID")
    claude_api_key: Optional[str] = Field(None, description="Claude API key")

    # 通义千问API
    qwen_access_key_id: Optional[str] = Field(None, description="Qwen access key ID")
    qwen_access_key_secret: Optional[str] = Field(None, description="Qwen access key secret")
    qwen_agent_key: Optional[str] = Field(None, description="Qwen agent key")
    qwen_app_id: Optional[str] = Field(None, description="Qwen app ID")
    qwen_node_id: Optional[str] = Field("", description="Qwen node ID")

    # 阿里灵积(通义新版sdk)模型api key
    dashscope_api_key: Optional[str] = Field(None, description="DashScope API key")

    # Google Gemini Api Key
    gemini_api_key: Optional[str] = Field(None, description="Gemini API key")

    # wework的通用配置
    wework_smart: bool = Field(True, description="Whether to use logged-in WeWork account")

    # 语音设置
    speech_recognition: bool = Field(False, description="Whether to enable speech recognition")
    group_speech_recognition: bool = Field(False, description="Whether to enable group speech recognition")
    voice_reply_voice: bool = Field(False, description="Whether to reply with voice")
    always_reply_voice: bool = Field(False, description="Whether to always reply with voice")
    voice_to_text: str = Field("openai", description="Voice-to-text engine")
    text_to_voice: str = Field("openai", description="Text-to-voice engine")
    text_to_voice_model: str = Field("tts-1", description="Text-to-voice model")
    tts_voice_id: str = Field("alloy", description="TTS voice ID")

    # baidu 语音api配置
    baidu_app_id: Optional[str] = Field(None, description="Baidu app ID")
    baidu_api_key: Optional[str] = Field(None, description="Baidu API key")
    baidu_secret_key: Optional[str] = Field(None, description="Baidu secret key")
    baidu_dev_pid: int = Field(1536, description="Baidu device PID")

    # azure 语音api配置
    azure_voice_api_key: Optional[str] = Field(None, description="Azure voice API key")
    azure_voice_region: str = Field("japaneast", description="Azure voice region")

    # elevenlabs 语音api配置
    xi_api_key: Optional[str] = Field(None, description="ElevenLabs API key")
    xi_voice_id: Optional[str] = Field(None, description="ElevenLabs voice ID")

    # 服务时间限制
    chat_time_module: bool = Field(False, description="Whether to enable service time restrictions")
    chat_start_time: str = Field("00:00", description="Service start time")
    chat_stop_time: str = Field("24:00", description="Service end time")

    # 翻译api
    translate: str = Field("baidu", description="Translation API")
    baidu_translate_app_id: Optional[str] = Field(None, description="Baidu translation app ID")
    baidu_translate_app_key: Optional[str] = Field(None, description="Baidu translation app key")

    # itchat的配置
    hot_reload: bool = Field(False, description="Whether to enable hot reload")

    # wechaty的配置
    wechaty_puppet_service_token: Optional[str] = Field(None, description="Wechaty token")

    # wechatmp的配置
    wechatmp_token: Optional[str] = Field(None, description="WeChat MP token")
    wechatmp_port: int = Field(8080, description="WeChat MP port")
    wechatmp_app_id: Optional[str] = Field(None, description="WeChat MP app ID")
    wechatmp_app_secret: Optional[str] = Field(None, description="WeChat MP app secret")
    wechatmp_aes_key: Optional[str] = Field(None, description="WeChat MP AES key")

    # wechatcom的通用配置
    wechatcom_corp_id: Optional[str] = Field(None, description="WeCom corp ID")

    # wechatcomapp的配置
    wechatcomapp_token: Optional[str] = Field(None, description="WeCom app token")
    wechatcomapp_port: int = Field(9898, description="WeCom app port")
    wechatcomapp_secret: Optional[str] = Field(None, description="WeCom app secret")
    wechatcomapp_agent_id: Optional[str] = Field(None, description="WeCom app agent ID")
    wechatcomapp_aes_key: Optional[str] = Field(None, description="WeCom app AES key")

    # 飞书配置
    feishu_port: int = Field(80, description="Feishu bot port")
    feishu_app_id: Optional[str] = Field(None, description="Feishu app ID")
    feishu_app_secret: Optional[str] = Field(None, description="Feishu app secret")
    feishu_token: Optional[str] = Field(None, description="Feishu verification token")
    feishu_bot_name: Optional[str] = Field(None, description="Feishu bot name")

    # 钉钉配置
    dingtalk_client_id: Optional[str] = Field(None, description="DingTalk client ID")
    dingtalk_client_secret: Optional[str] = Field(None, description="DingTalk client secret")
    dingtalk_card_enabled: bool = Field(False, description="Whether to enable DingTalk card")

    # chatgpt指令自定义触发词
    clear_memory_commands: List[str] = Field(["#清除记忆"], description="Commands to clear memory")

    # channel配置
    channel_type: Optional[str] = Field("wx", description="Channel type")
    subscribe_msg: Optional[str] = Field(None, description="Subscription message")
    debug: bool = Field(False, description="Whether to enable debug mode")
    appdata_dir: Optional[str] = Field(None, description="App data directory")

    # 插件配置
    plugin_trigger_prefix: str = Field("$", description="Plugin command prefix")
    use_global_plugin_config: bool = Field(False, description="Whether to use global plugin config")
    max_media_send_count: int = Field(3, description="Max number of media resources sent at once")
    media_send_interval: int = Field(1, description="Interval between sending media resources")

    # 智谱AI 平台配置
    zhipu_ai_api_key: Optional[str] = Field(None, description="Zhipu AI API key")
    zhipu_ai_api_base: str = Field("https://open.bigmodel.cn/api/paas/v4", description="Zhipu AI API base URL")
    moonshot_api_key: Optional[str] = Field(None, description="Moonshot API key")
    moonshot_base_url: str = Field("https://api.moonshot.cn/v1/chat/completions", description="Moonshot base URL")

    # LinkAI平台配置
    use_linkai: bool = Field(False, description="Whether to use LinkAI")
    linkai_api_key: Optional[str] = Field(None, description="LinkAI API key")
    linkai_app_code: Optional[str] = Field(None, description="LinkAI app code")
    linkai_api_base: str = Field("https://api.link-ai.tech", description="LinkAI API base URL")

    Minimax_api_key: Optional[str] = Field(None, description="Minimax API key")
    Minimax_group_id: Optional[str] = Field(None, description="Minimax group ID")
    Minimax_base_url: Optional[str] = Field(None, description="Minimax base URL")

    web_port: int = Field(9899, description="Web server port")


class ResponseItem(BaseModel):
    code: int = Field(200, description="Response code")
    msg: str = Field("success", description="Response message")
    data: CowItem | List[CowItem] | None = Field(None, description="Response data")


@app.post("/cows/", summary="创建一个新的CoW", response_model=ResponseItem)
async def create_cow(cow_config: CoWConfig):
    """
    创建一个新的CoW进程实例。通常只需要传**open_ai_api_key**、**open_ai_api_base**和**model**。对于智能体平台如fastgpt则不需要**model**。
    各参数解释详见请求体Schema各字段解释，或者查看[chatgpt-on-wechat config.py文件](https://github.com/zhayujie/chatgpt-on-wechat/blob/16324e72837b9898dfaca76897cdcdb27044dc06/config.py#L13)。
    """
    cow = await CoW.create_cow(cow_config.model_dump())
    cows[cow.pid] = cow
    return ResponseItem(code=200,
                        msg="success",
                        data=CowItem(cow_id=cow.pid,
                                     status_code=cow.status_code,
                                     qrcodes=cow.qrcodes,
                                     log=cow.log,
                                     auto_clear_datetime=cow.auto_clear_datetime))


@app.get("/cows/{cow_id}/", summary="获取CoW实例",
         responses={
             "200": {"description": "取得目标CoW", "model": ResponseItem},
             "404": {"description": "未找到目标CoW", "model": Model404}
         })
def get_cow_status(cow_id: int):
    """
    获取指定CoW的运行信息。
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
    """
    响应格式详看响应体Schema。
    """
    return ResponseItem(code=200,
                        msg="success",
                        data=[CowItem(cow_id=cow.pid,
                                      status_code=cow.status_code,
                                      qrcodes=cow.qrcodes,
                                      log=cow.log,
                                      auto_clear_datetime=cow.auto_clear_datetime) for cow in cows.values()])


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
