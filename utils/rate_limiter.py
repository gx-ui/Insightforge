import asyncio
import time
from typing import Optional


class RateLimiter:
    """
    速率限制器，用于控制 API 请求频率。

    确保每分钟请求数不超过 max_requests_per_minute，
    每天请求数不超过 max_requests_per_day。
    """

    def __init__(
        self,
        max_requests_per_minute: Optional[int] = None,
        max_requests_per_day: Optional[int] = None
    ):
        """
        初始化速率限制器。

        Args:
            max_requests_per_minute: 每分钟允许的最大请求数。
                                     若为 None，则不启用每分钟限制。
            max_requests_per_day: 每天允许的最大请求数。
                                  若为 None，则不启用每日限制。
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.max_requests_per_day = max_requests_per_day
        self.request_times = []
        self.lock = asyncio.Lock()

        # 若启用了每分钟速率限制，计算请求之间的最小间隔
        if max_requests_per_minute and max_requests_per_minute > 0:
            self.min_delay = 60.0 / max_requests_per_minute
        else:
            self.min_delay = 0

    async def acquire(self):
        """
        获取发起请求的许可。

        该方法会阻塞，直到根据速率限制可以安全地发起请求。

        锁仅在检查和记录时持有，在休眠期间从不持有：
        调用方在等待一个窗口期（每日限制最长可达 24 小时）时不得
        阻塞其他所有调用方的检查。每次休眠后会重新检查限制，
        因为其他调用方可能已经占用了释放出的配额。
        """
        if not self.max_requests_per_minute and not self.max_requests_per_day:
            # 速率限制已禁用
            return

        while True:
            message = None
            async with self.lock:
                current_time = time.time()

                # 清理过期的请求记录（为计算每日限制，保留最近 24 小时的请求）
                if self.max_requests_per_day:
                    self.request_times = [t for t in self.request_times if current_time - t < 86400]
                elif self.max_requests_per_minute:
                    self.request_times = [t for t in self.request_times if current_time - t < 60]

                wait_time = 0.0

                # 优先检查每日限制
                if self.max_requests_per_day and self.max_requests_per_day > 0:
                    daily_requests = [t for t in self.request_times if current_time - t < 86400]
                    if len(daily_requests) >= self.max_requests_per_day:
                        wait_time = 86400 - (current_time - daily_requests[0])
                        hours = wait_time / 3600
                        message = f"已达每日速率上限（{self.max_requests_per_day} 次/天）。等待 {hours:.1f} 小时..."

                # 检查每分钟限制
                if wait_time <= 0 and self.max_requests_per_minute and self.max_requests_per_minute > 0:
                    minute_requests = [t for t in self.request_times if current_time - t < 60]
                    if len(minute_requests) >= self.max_requests_per_minute:
                        wait_time = 60 - (current_time - minute_requests[0])
                        message = f"已达速率上限（{self.max_requests_per_minute} 次/分钟）。等待 {wait_time:.1f} 秒..."
                    elif self.request_times and self.min_delay > 0:
                        # 同时确保连续请求之间的最小间隔
                        time_since_last = current_time - self.request_times[-1]
                        if time_since_last < self.min_delay:
                            wait_time = self.min_delay - time_since_last

                if wait_time <= 0:
                    # 记录本次请求
                    self.request_times.append(current_time)
                    return

            if message:
                print(message)
            await asyncio.sleep(wait_time)