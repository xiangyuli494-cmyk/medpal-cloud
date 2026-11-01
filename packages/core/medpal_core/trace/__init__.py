"""决策链：trace 落库、报告生成、溯源完整率。"""

from .writer import get_trace, write_trace

__all__ = ["write_trace", "get_trace"]
