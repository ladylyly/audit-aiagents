import os
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from backend.paths import BACKEND_ENV_PATH


@dataclass(frozen=True)
class IpfsFetchConfig:
    gateways: List[str]
    timeout_s: float = 10.0
    retries: int = 2
    backoff_s: float = 0.6
    jitter_s: float = 0.2


class IpfsFetcher:
    
    #Fetch VC JSON documents by CID from IPFS HTTP gateways.
    def __init__(self, config: IpfsFetchConfig):
        if not config.gateways:
            raise ValueError("IpfsFetchConfig.gateways must be non-empty")
        self.config = config

    def _candidate_urls(self, cid: str) -> List[str]:
        gateways = list(self.config.gateways)
        random.shuffle(gateways)
        return [f"{g.rstrip('/')}/{cid}" for g in gateways]

    def _fetch_from_url(self, url: str) -> Dict[str, Any]:
        res = requests.get(url, timeout=self.config.timeout_s)
        res.raise_for_status()
        return res.json()

    def fetch_json(self, cid: str) -> Dict[str, Any]:
        if not cid or not isinstance(cid, str):
            raise ValueError("cid must be a non-empty string")

        urls = self._candidate_urls(cid)
        last_err: Optional[Exception] = None

        for attempt in range(self.config.retries + 1):
            executor = ThreadPoolExecutor(max_workers=len(urls))
            try:
                future_to_url = {
                    executor.submit(self._fetch_from_url, url): url
                    for url in urls
                }
                pending = set(future_to_url.keys())
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            result = future.result()
                            for other in pending:
                                other.cancel()
                            return result
                        except Exception as e:
                            last_err = e
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            if attempt < self.config.retries:
                sleep_s = self.config.backoff_s * (2**attempt) + random.random() * self.config.jitter_s
                time.sleep(sleep_s)

        raise RuntimeError(f"Failed to fetch CID {cid} from all configured IPFS gateways") from last_err


def default_ipfs_config() -> IpfsFetchConfig:
    pinata_gateway = os.getenv("PINATA_GATEWAY", "").strip()
    if not pinata_gateway and BACKEND_ENV_PATH.exists():
        for raw in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "PINATA_GATEWAY":
                pinata_gateway = value.strip()
                break

    first_gateway = f"{pinata_gateway.rstrip('/')}/ipfs" if pinata_gateway else "https://gateway.pinata.cloud/ipfs"

    return IpfsFetchConfig(
        gateways=[
            first_gateway,
            "https://gateway.pinata.cloud/ipfs",
            "https://ipfs.io/ipfs",
            "https://cloudflare-ipfs.com/ipfs",
        ],
        timeout_s=12.0,
        retries=2,
    )
