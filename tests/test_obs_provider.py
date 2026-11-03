"""OBS 取对象的字节读取：ObjectStream 的几种形态都要兜住。"""

from __future__ import annotations

from medpal_core.providers.huawei.obs import read_body


class _MemStream:
    """loadStreamInMemory=True 时的形态：buffer 直接有值。"""

    def __init__(self, data):
        self.buffer = data


class _OldStream:
    """老形态：只有 callable 的 read()。"""

    def __init__(self, data):
        self.buffer = None
        self._data = data

    def read(self):
        return self._data


class _BrokenStream:
    """真实踩到的坑：buffer 为 None，read 属性存在但是 None。"""

    buffer = None
    read = None


def test_memory_stream_reads_buffer():
    assert read_body(_MemStream(b"hello")) == b"hello"


def test_old_stream_falls_back_to_read():
    assert read_body(_OldStream(b"abc")) == b"abc"


def test_broken_stream_degrades_to_empty():
    assert read_body(_BrokenStream()) == b""
