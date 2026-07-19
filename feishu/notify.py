import json
import requests
import datetime


def send_text(webhook_url, content, mentioned_list=None, mentioned_mobile_list=None):
    """发送文本消息到飞书群"""
    body = {
        "msg_type": "text",
        "content": {
            "text": content
        }
    }
    if mentioned_list or mentioned_mobile_list:
        body["content"]["mentioned_list"] = mentioned_list or []
        body["content"]["mentioned_mobile_list"] = mentioned_mobile_list or []

    return _post(webhook_url, body)


def send_post(webhook_url, title, content_lines):
    """发送富文本帖子到飞书群"""
    body = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content_lines
                }
            }
        }
    }
    return _post(webhook_url, body)


def send_interactive(webhook_url, title, content, button_text=None, button_url=None):
    """发送交互式卡片消息到飞书群"""
    elements = [{"tag": "markdown", "content": content}]
    if button_text and button_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": button_text},
                "url": button_url,
                "type": "primary"
            }]
        })

    body = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue"
            },
            "elements": elements
        }
    }
    return _post(webhook_url, body)


def notify_task_complete(webhook_url, task_summary, detail=""):
    """发送任务完成通知 (卡片格式)"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"**时间**: {now}\n\n**摘要**: {task_summary}"
    if detail:
        content += f"\n\n**详情**:\n{detail}"
    return send_interactive(webhook_url, "Claude Code 任务完成", content)


def _post(webhook_url, body):
    """发送 POST 请求到飞书 Webhook"""
    try:
        resp = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(body),
            timeout=10
        )
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            return True, "发送成功"
        return False, f"飞书返回错误: {result}"
    except Exception as e:
        return False, f"发送失败: {e}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python feishu_notify.py <webhook_url> <message> [--card]")
        print("  --card: 使用卡片格式发送")
        sys.exit(1)

    url = sys.argv[1]
    msg = sys.argv[2]
    use_card = "--card" in sys.argv

    if use_card:
        ok, info = notify_task_complete(url, msg)
    else:
        ok, info = send_text(url, msg)

    print(f"{'OK' if ok else 'FAIL'} {info}")
