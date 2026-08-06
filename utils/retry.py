import tenacity
import traceback
import logging

import requests

def after_func(retry_state: tenacity.RetryCallState) -> None:
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        logging.warning(f"正在重试 {retry_state.fn.__name__}，原因: {repr(exc)}（第 {retry_state.attempt_number} 次尝试）")
        logging.debug(traceback.format_exception(type(exc), exc, exc.__traceback__))


def is_retryable_download_error(exc: BaseException) -> bool:
    """网络错误和 5xx 响应可重试；其他 HTTP 错误（URL 过期或无效、鉴权失败）
    永远不会成功，必须立即失败。"""
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        return response is None or response.status_code >= 500
    return isinstance(exc, requests.RequestException)


download_retry = tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, max=10),
    retry=tenacity.retry_if_exception(is_retryable_download_error),
    after=after_func,
    reraise=True,
)