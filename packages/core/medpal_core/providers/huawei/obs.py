"""OBS：原件与报告落对象存储。SDK 缺失或未配 AK/SK 时明确报缺什么。"""

from __future__ import annotations

from pathlib import Path

from .config import ProviderNotConfigured, load_config


class OBSStore:
    name = "huawei-obs"

    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        self._client = None

    def available(self) -> bool:
        return self.cfg.readiness()["obs"]

    def _c(self):
        if self._client is None:
            if not self.available():
                raise ProviderNotConfigured("缺少 HUAWEI_AK / HUAWEI_SK / HUAWEI_OBS_BUCKET")
            try:
                from obs import ObsClient  # type: ignore
            except ImportError as exc:
                raise ProviderNotConfigured("未安装华为云 OBS SDK：pip install esdk-obs-python") from exc
            self._client = ObsClient(access_key_id=self.cfg.ak, secret_access_key=self.cfg.sk,
                                     server="https://obs." + self.cfg.region + ".myhuaweicloud.com")
        return self._client

    def put(self, local_path: str | Path, key: str) -> str:
        client = self._c()
        resp = client.putFile(self.cfg.obs_bucket, key, str(local_path))
        if getattr(resp, "status", 0) >= 300:
            raise ProviderNotConfigured("OBS 上传失败: {}".format(getattr(resp, "reason", resp)))
        return "obs://" + self.cfg.obs_bucket + "/" + key

    def get(self, key: str) -> bytes:
        client = self._c()
        resp = client.getObject(self.cfg.obs_bucket, key)
        return resp.body.buffer if hasattr(resp.body, "buffer") else resp.body
