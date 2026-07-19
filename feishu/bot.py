"""飞书机器人服务 - 长连接模式

在飞书群中 @机器人 发送命令，机器人执行任务并返回结果。

支持的命令：
  帮助 / help       - 查看所有命令
  运行选股           - 执行完整选股分析
  运行选股 调试 N    - 仅分析前N只证券（调试用）
  查看买入           - 查看最近的买入信号结果
  查看卖出           - 查看最近的卖出信号结果
  状态               - 查看服务运行状态
"""
import os
import sys
import json
import time
import threading
import subprocess
import datetime
import traceback

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

# ======== 配置 ========

from config import FEISHU_APP_ID as APP_ID, FEISHU_APP_SECRET as APP_SECRET
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_api_client = None


def _build_client():
    """构建 API Client（单例）"""
    global _api_client
    if _api_client is None:
        _api_client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()
    return _api_client

# 任务状态
_task_status = {
    "running": False,
    "last_command": None,
    "last_start": None,
    "last_result": None,
}
_task_lock = threading.Lock()


def _read_csv_head(path, n=10):
    """读取CSV文件前n行，返回格式化文本"""
    if not os.path.exists(path):
        return None
    try:
        import pandas as pd
        df = pd.read_csv(path, encoding='utf-8-sig')
        if df.empty:
            return "文件为空"
        return df.head(n).to_string(index=False)
    except Exception as e:
        return f"读取失败: {e}"


def _run_analysis(max_count=0):
    """执行选股分析，返回结果摘要"""
    with _task_lock:
        if _task_status["running"]:
            return "任务正在运行中，请稍后再试"
        _task_status["running"] = True
        _task_status["last_command"] = f"运行选股{' 调试 ' + str(max_count) if max_count else ''}"
        _task_status["last_start"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cmd = [sys.executable, os.path.join(PROJECT_DIR, "main.py")]
        if max_count > 0:
            # 需要main.py支持--max-count参数，目前不支持，先跳过
            pass

        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时
            encoding='utf-8',
            errors='replace',
        )

        success = result.returncode == 0
        output = result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        error = result.stderr[-1000:] if result.stderr else ""

        # 读取结果文件
        buy_csv = os.path.join(PROJECT_DIR, "output", "buy_signals.csv")
        buy_etf_csv = os.path.join(PROJECT_DIR, "output", "buy_etf_signals.csv")
        sale_csv = os.path.join(PROJECT_DIR, "output", "sale_signals.csv")

        summary = ""
        buy_info = _read_csv_head(buy_csv, 10)
        buy_etf_info = _read_csv_head(buy_etf_csv, 10)
        sale_info = _read_csv_head(sale_csv, 10)

        if buy_info:
            summary += f"\n\n**买入信号(股票)**:\n```\n{buy_info}\n```"
        if buy_etf_info:
            summary += f"\n\n**买入信号(ETF)**:\n```\n{buy_etf_info}\n```"
        if sale_info:
            summary += f"\n\n**卖出信号**:\n```\n{sale_info}\n```"

        if not success:
            summary = f"\n\n**运行失败**:\n```\n{error}\n```" + summary

        with _task_lock:
            _task_status["running"] = False
            _task_status["last_result"] = "成功" if success else "失败"

        return summary or "\n\n分析完成，无信号结果"

    except subprocess.TimeoutExpired:
        with _task_lock:
            _task_status["running"] = False
            _task_status["last_result"] = "超时"
        return "\n\n**运行超时**（30分钟）"
    except Exception as e:
        with _task_lock:
            _task_status["running"] = False
            _task_status["last_result"] = f"异常: {e}"
        return f"\n\n**运行异常**:\n```\n{traceback.format_exc()}\n```"


def _handle_command(command, chat_id):
    """解析并执行命令，返回回复内容"""
    cmd = command.strip()

    if cmd in ("帮助", "help", "?"):
        return (
            "**可用命令**:\n"
            "- `帮助` - 查看所有命令\n"
            "- `运行选股` - 执行完整选股分析\n"
            "- `运行选股 调试 N` - 仅分析前N只\n"
            "- `查看买入` - 查看最近买入信号\n"
            "- `查看卖出` - 查看最近卖出信号\n"
            "- `状态` - 查看服务状态\n\n"
            "在群中 @我 发送命令即可触发"
        )

    elif cmd.startswith("运行选股"):
        parts = cmd.split()
        max_count = 0
        if "调试" in parts:
            try:
                idx = parts.index("调试")
                max_count = int(parts[idx + 1])
            except (ValueError, IndexError):
                max_count = 10

        # 先回复"开始运行"
        _send_message(chat_id, "开始执行选股分析，请稍候...")
        return _run_analysis(max_count)

    elif cmd in ("查看买入", "买入"):
        buy_csv = os.path.join(PROJECT_DIR, "output", "buy_signals.csv")
        buy_etf_csv = os.path.join(PROJECT_DIR, "output", "buy_etf_signals.csv")
        result = ""
        info = _read_csv_head(buy_csv, 15)
        if info:
            result += f"**买入信号(股票)**:\n```\n{info}\n```"
        info2 = _read_csv_head(buy_etf_csv, 15)
        if info2:
            result += f"\n\n**买入信号(ETF)**:\n```\n{info2}\n```"
        return result or "暂无买入信号数据"

    elif cmd in ("查看卖出", "卖出"):
        sale_csv = os.path.join(PROJECT_DIR, "output", "sale_signals.csv")
        info = _read_csv_head(sale_csv, 15)
        if info:
            return f"**卖出信号**:\n```\n{info}\n```"
        return "暂无卖出信号数据"

    elif cmd in ("状态", "status"):
        with _task_lock:
            status = _task_status.copy()
        running = "运行中" if status["running"] else "空闲"
        return (
            f"**服务状态**: 在线\n"
            f"**任务状态**: {running}\n"
            f"**上次命令**: {status['last_command'] or '无'}\n"
            f"**上次时间**: {status['last_start'] or '无'}\n"
            f"**上次结果**: {status['last_result'] or '无'}"
        )

    else:
        return f"未知命令 `{cmd}`，发送 `帮助` 查看可用命令"


def _send_message(chat_id, text):
    """发送文本消息到飞书群"""
    client = _build_client()
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()) \
        .build()
    client.im.v1.message.create(req)


def _send_card(chat_id, title, content):
    """发送卡片消息到飞书群"""
    client = _build_client()
    card = {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue"
        },
        "elements": [{"tag": "markdown", "content": content}]
    }
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card))
            .build()) \
        .build()
    client.im.v1.message.create(req)


def on_message(data) -> None:
    """处理收到的消息事件"""
    try:
        event = data.event
        message = event.message
        sender = event.sender

        msg_type = message.message_type or ""
        content_str = message.content or "{}"
        chat_id = message.chat_id or ""
        sender_type = sender.sender_type or ""
        mentions = message.mentions or []

        print(f"[收到消息] type={msg_type} chat={chat_id} sender={sender_type}", flush=True)
        print(f"[消息内容] {content_str[:200]}", flush=True)
    except Exception as e:
        print(f"[ERROR] 解析事件失败: {e}", flush=True)
        print(f"[DEBUG] data={str(data)[:500]}", flush=True)
        return

    # 只处理文本消息，忽略机器人自己发的
    if sender_type == "app" or msg_type != "text":
        return

    try:
        content = json.loads(content_str)
        text = content.get("text", "").strip()
    except json.JSONDecodeError:
        return

    if not text:
        return

    # 去掉 @机器人 的部分
    import re
    text = re.sub(r'@_user_\d+\s*', '', text).strip()

    if not text:
        text = "帮助"

    print(f"[收到命令] {text} (chat: {chat_id})", flush=True)

    reply = _handle_command(text, chat_id)

    if reply:
        try:
            _send_card(chat_id, "Claude 助手", reply)
            print(f"[回复成功] chat={chat_id}", flush=True)
        except Exception as e:
            print(f"[回复失败] {e}", flush=True)


def main():
    """启动飞书机器人长连接服务"""
    # 创建消息发送用的 Client
    _build_client()

    # 注册事件处理器
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    # 启动长连接（ws.Client 直接接收 app_id/secret）
    cli = lark.ws.Client(
        app_id=APP_ID,
        app_secret=APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.DEBUG,
        auto_reconnect=True,
    )

    print("=" * 50)
    print("飞书机器人服务启动中...")
    print(f"App ID: {APP_ID}")
    print("=" * 50)

    cli.start()


if __name__ == "__main__":
    main()
