"""报告上云：本地 reports/TR-xxx.md 传到对象存储，回读时给出 obs:// 地址。

为什么单独一层而不是塞进 core：
- core 的 OBSStore 只管「一个对象怎么进出桶」，不知道「报告」这回事；
- 评测与前端读的是 trace，报告位置属于应用语义，放 apps 更合边界（BND2 也要求云 SDK 只出现在 providers）。

没有配 OBS 时全部安静降级：/v1/ask 照常返回 200，只是 report_uri 为 null。
这是 B7 的验收口径——配了就真传，没配就真降级，两条路都不许抛异常。
"""

from __future__ import annotations

from pathlib import Path

from medpal_core.storage.db import report_dir

REPORT_PREFIX = "reports"


def report_key(trace_id: str) -> str:
    """桶内路径：reports/TR-xxx.md，与本地 reports/ 同名，便于人工对照。"""
    return f"{REPORT_PREFIX}/{trace_id}.md"


def local_report_path(trace_id: str) -> Path:
    return report_dir() / (trace_id + ".md")


class ReportStore:
    """把决策链报告放上对象存储；未配置时所有方法安静降级。"""

    name = "report-store"

    def __init__(self, store=None, cache_size: int = 256):
        self._store = store
        self._cache: dict[str, str] = {}
        self._cache_size = cache_size

    @property
    def store(self):
        """延迟创建：只读端点不该为了一个属性去 import 云 SDK。"""
        if self._store is None:
            from medpal_core.providers.huawei.obs import OBSStore

            self._store = OBSStore()
        return self._store

    def available(self) -> bool:
        """配置齐了没有。SDK 缺失也算没配：导入异常在这里吃掉，别让端点 500。"""
        try:
            return bool(self.store.available())
        except Exception:
            return False

    def upload(self, trace_id: str, path: str | Path | None = None) -> dict:
        """上传一条报告，返回 {uri, key, reason}。永不抛异常。"""
        if not trace_id:
            return {"uri": None, "key": None, "reason": "no_trace_id"}
        if not self.available():
            return {"uri": None, "key": None, "reason": "obs_not_configured"}
        local = Path(path) if path else local_report_path(trace_id)
        if not local.exists():
            return {"uri": None, "key": None, "reason": "report_not_found"}
        key = report_key(trace_id)
        try:
            uri = self.store.put(local, key)
        except Exception as exc:  # 上传失败不该让一次已经算完的推理作废
            return {"uri": None, "key": key, "reason": "upload_failed", "error": str(exc)[:200]}
        self._remember(trace_id, uri)
        return {"uri": uri, "key": key}

    def uri(self, trace_id: str) -> str | None:
        """回读：先查本进程缓存，再问一次桶；都没有就 null。"""
        if not trace_id:
            return None
        if trace_id in self._cache:
            return self._cache[trace_id]
        if not self.available():
            return None
        key = report_key(trace_id)
        try:
            if not self.store.exists(key):
                return None
            uri = self.store.uri(key)
        except Exception:
            return None
        self._remember(trace_id, uri)
        return uri

    def _remember(self, trace_id: str, uri: str) -> None:
        """缓存「已确认在桶里」的 trace。满了整体清空——这是加速，不是真相来源。"""
        if len(self._cache) >= self._cache_size:
            self._cache.clear()
        self._cache[trace_id] = uri
