import plugins
from plugins import *


@plugins.register(
    name="Switch",
    desire_priority=999,
    desc="A simple plugin that switchs CoW between ON and OFF",
    version="0.1",
    author="907333918@qq.com"
)
class Switch(Plugin):
    switch: bool = True

    def __init__(self):
        super().__init__()
        try:
            logger.info("[Switch] inited")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[Switch]初始化异常：{e}")
            raise "[Switch] init failed, ignore "

    def on_handle_context(self, e_context: EventContext):
        if os.environ.get("PYTHONUNBUFFERED") == "1": print(f"{self.switch=}")
        if not self.switch:
            e_context.action = EventAction.BREAK_PASS
