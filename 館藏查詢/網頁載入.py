"""圖書館頁面遇到連線逾時時，最多重新載入三次。"""

from selenium.common.exceptions import TimeoutException, WebDriverException


MAX_RELOADS = 3


class ConnectionTimeout(RuntimeError):
    """重新載入後仍無法連上圖書館網站。"""


def get_with_retries(driver, url: str, max_reloads: int = MAX_RELOADS) -> None:
    for reload_count in range(max_reloads + 1):
        try:
            driver.get(url)
            return
        except (TimeoutException, WebDriverException) as exc:
            message = str(exc).upper()
            timed_out = isinstance(exc, TimeoutException) or "ERR_CONNECTION_TIMED_OUT" in message or "ERR_TIMED_OUT" in message
            if not timed_out:
                raise
            if reload_count == max_reloads:
                raise ConnectionTimeout(
                    f"圖書館網站連線逾時，已重新載入 {max_reloads} 次仍無法連線"
                ) from None
            print(f"[!] 圖書館網站連線逾時，重新載入 {reload_count + 1}/{max_reloads}...", flush=True)
