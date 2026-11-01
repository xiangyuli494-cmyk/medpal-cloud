"""华为云适配：OBS / GaussDB / ModelArts / KooSearch。

全部懒加载 SDK：没装 SDK、没配 AK/SK 时，available() 返回 False 并给出人话原因，
主流程自动回落本地实现，不会因为「没上云」而跑不起来。
"""

from .config import HuaweiConfig, load_config

__all__ = ["HuaweiConfig", "load_config"]
