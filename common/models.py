from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class Model404(BaseModel):
    msg: str = Field(default="Not Found")
    code: int = Field(default=404)
    data: dict = Field(default_factory=dict)


class Model400(BaseModel):
    msg: str = Field(default="Bad Request")
    code: int = Field(default=400)
    data: dict = Field(default_factory=dict)


class ContactInfo(BaseModel):
    MemberList: List = Field(default_factory=list)
    UserName: str = Field("", description="单次运行CoW实例时，获取到的好友名，唯一标识")
    City: str = ""
    DisplayName: str = ""
    PYQuanPin: str = ""
    RemarkPYInitial: str = ""
    Province: str = ""
    KeyWord: str = ""
    RemarkName: str = Field("", description="备注名")
    PYInitial: str = ""
    EncryChatRoomId: str = ""
    Alias: str = ""
    Signature: str = Field("", description="个性签名")
    NickName: str = Field("", description="微信名字，在手机微信里在“我——微信号——名字”")
    RemarkPYQuanPin: str = ""
    HeadImgUrl: str = Field("", description="头像链接")
    UniFriend: int = 0
    Sex: int = 0
    AppAccountFlag: int = 0
    VerifyFlag: int = 0
    ChatRoomId: int = 0
    HideInputBarFlag: int = 0
    AttrStatus: int = 0
    SnsFlag: int = 0
    MemberCount: int = 0
    OwnerUin: int = 0
    ContactFlag: int = 0
    Uin: int = 0
    StarFriend: int = 0
    Statues: int = 0
    WebWxPluginSwitch: int = 0
    HeadImgFlag: int = 0


class WX(BaseModel):
    wx_nickname: str = Field("", description="微信昵称")
    head_img_url: str = Field("", description="头像链接")  # todo 完善为完整的链接
    friends: List[ContactInfo] = Field(default_factory=list, description="好友列表")


class CowItem(BaseModel):
    cow_id: int = Field(-1, description="CoW id")
    status_code: "StatusCodeEnum" = Field(..., description="CoW实例状态码：-1 已死亡，0 待登录，1 工作中")
    wx: WX = Field(WX(), description="微信信息")
    qrcodes: List[str] = Field(default_factory=list,
                               description="二维码链接列表，任何一个都可以用于手机微信扫码登录，只在“待登录”状态才会有。注意！“待登录”状态持续太久的话，过几分钟这个列表就会刷新，而老的链接上的二维码会失效，需要重新请求获得最新二维码链接。")
    ai_name: str = Field("", description="对接的智能体或者大语言模型名字")
    log: str = Field("", description="日志")
    auto_clear_datetime: datetime | None = Field(None, description="已死亡CoW实例的自动清理时间")


# 使用 Enum 定义 status_code 的合法值
class StatusCodeEnum(int, Enum):
    DEAD = -1  # 已死亡
    TO_LOGIN = 0  # 待登录
    WORKING = 1  # 工作中
    WORKING_BUT_PAUSE = 2  # 工作中已暂停


class CoWConfig(BaseModel):
    # openai api配置
    open_ai_api_key: str = Field("", description="OpenAI API兼容的LLM服务的Api Key")
    open_ai_api_base: str = Field("https://api.openai.com/v1",
                                  description="OpenAI API兼容的LLM服务的base URL，可以不以“/v1”结尾")
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
