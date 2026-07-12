import random
import time
import logging
import threading
from typing import Any, Optional
import httpx

logger = logging.getLogger(__name__)


class RPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"RPC {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class RateLimiter:
    def __init__(self, requests_per_sec: float = 10.0):
        self.interval = 1.0 / requests_per_sec if requests_per_sec > 0 else 0.0
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        if self.interval <= 0:
            return
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self.last_call = time.monotonic()


class RPCClient:
    """Resilient JSON-RPC client with batch support and backoff."""

    def __init__(
        self,
        endpoint_url: str,
        timeout: float = 25.0,
        max_retries: int = 4,
        rate_limit: float = 12.0,
        headers: Optional[dict[str, str]] = None,
    ):
        self.endpoint_url = endpoint_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = RateLimiter(rate_limit)
        self._headers = headers or {}
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Content-Type": "application/json", **self._headers}
        )
        self._req_counter = 0
        self._lock = threading.Lock()

    def _next_id(self) -> int:
        with self._lock:
            self._req_counter += 1
            return self._req_counter

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def call(self, method: str, params: Optional[list[Any] | dict[str, Any]] = None) -> Any:
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params if params is not None else [],
        }
        return self._post_with_retry(payload, is_batch=False)

    def batch_call(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        if not calls:
            return []

        # Keep map of request ID to original position because nodes can return responses out of order
        id_map = {}
        payload = []
        for idx, (method, params) in enumerate(calls):
            req_id = self._next_id()
            id_map[req_id] = idx
            payload.append({
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            })

        raw_results = self._post_with_retry(payload, is_batch=True)
        if not isinstance(raw_results, list):
            raise RuntimeError(f"Expected batch response list from {self.endpoint_url}, got {type(raw_results)}")

        ordered: list[Any] = [None] * len(calls)
        for item in raw_results:
            item_id = item.get("id")
            if item_id in id_map:
                if "error" in item:
                    err = item["error"]
                    ordered[id_map[item_id]] = RPCError(err.get("code", -1), err.get("message", ""), err.get("data"))
                else:
                    ordered[id_map[item_id]] = item.get("result")
        return ordered

    def _post_with_retry(self, payload: Any, is_batch: bool) -> Any:
        base_delay = 0.75
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            try:
                # print(f"DEBUG: sending rpc req to {self.endpoint_url}")
                resp = self._client.post(self.endpoint_url, json=payload)

                # public rpc nodes return 429 or 503 during load spikes
                if resp.status_code in (429, 502, 503, 504):
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_time = float(retry_after)
                    else:
                        sleep_time = base_delay * (2 ** attempt) + random.uniform(0.1, 0.4)
                    logger.warning(f"HTTP {resp.status_code} from {self.endpoint_url}, backing off for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if is_batch:
                    return data

                if isinstance(data, dict) and "error" in data:
                    err = data["error"]
                    code = err.get("code", -32000)
                    # Alchemy/Infura rate limit error code
                    if code in (-32005, 429):
                        sleep_time = base_delay * (2 ** attempt) + random.uniform(0.2, 0.5)
                        time.sleep(sleep_time)
                        continue
                    raise RPCError(code, err.get("message", "Unknown RPC error"), err.get("data"))

                return data.get("result") if isinstance(data, dict) else data

            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt == self.max_retries:
                    raise
                sleep_time = base_delay * (2 ** attempt) + random.uniform(0.1, 0.3)
                logger.debug(f"Network issue on {self.endpoint_url}: {exc}, retry #{attempt + 1}")
                time.sleep(sleep_time)

        raise RuntimeError(f"Exceeded max retries ({self.max_retries}) for {self.endpoint_url}")
