# utils.py
import time
import random
from config import MAX_RETRIES, BASE_DELAY, MAX_DELAY

def retry_with_backoff(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """
    带指数退避的重试装饰器
    :param func: 要执行的函数
    :param args: 位置参数
    :param max_retries: 最大重试次数
    :param kwargs: 关键字参数
    :return: 函数返回值
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise e
            delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
            jitter = random.uniform(0, 0.5 * delay)
            total_delay = delay + jitter
            print(f"第 {attempt+1} 次失败: {e}，{total_delay:.1f}秒后重试...")
            time.sleep(total_delay)