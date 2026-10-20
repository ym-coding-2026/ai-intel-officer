"""推送模块（v4）：把日报主动送到你面前。

v1~v3.5 的日报只是"提交回仓库"，得你自己打开 GitHub 才看得到。
v4 让它主动找你：企业微信群 / 邮箱，哪个配了走哪个。

沿用本项目一贯的**可降级**哲学：
- 配了企业微信机器人 webhook → 推企业微信
- 配了邮箱 SMTP → 推邮件
- 两个都没配 / 推送失败 → 打印一句提示，流水线照常结束，绝不因为推送失败而崩

全部用标准库实现（smtplib / urllib），不新增任何依赖，云端跑也不拖慢。
"""
import json
import os
import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from urllib import request

# 企业微信机器人单条消息上限约 4096 字节，留点余量
WECOM_LIMIT = 3800


def _cfg(key):
    return (os.getenv(key) or "").strip()


def email_ready():
    """邮箱配置是否齐全（缺一样就不推）。"""
    return all(_cfg(k) for k in ("SMTP_USER", "SMTP_PASS"))


def wecom_ready():
    return bool(_cfg("WECOM_WEBHOOK"))


def send_wecom(markdown):
    """推到企业微信群机器人。返回 True/False。"""
    hook = _cfg("WECOM_WEBHOOK")
    body = markdown[:WECOM_LIMIT]
    payload = {"msgtype": "markdown", "markdown": {"content": body}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        hook, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=15) as resp:
        resp.read()
    return True


def send_email(subject, body):
    """通过 SMTP 发送邮件（QQ/163/Gmail 都行）。返回 True/False。"""
    host = _cfg("SMTP_HOST") or "smtp.qq.com"
    port = int(_cfg("SMTP_PORT") or 465)
    user = _cfg("SMTP_USER")
    pwd = _cfg("SMTP_PASS")
    to = _cfg("MAIL_TO") or user

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("AI 情报官", user))
    msg["To"] = to

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(user, pwd)
            server.sendmail(user, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls(context=context)
            server.login(user, pwd)
            server.sendmail(user, [to], msg.as_string())
    return True


def notify(markdown, title="AI 情报官 · 日报"):
    """按配置把日报推送出去。返回实际送达的渠道名列表（可能为空）。"""
    sent = []

    if wecom_ready():
        try:
            send_wecom(markdown)
            sent.append("企业微信")
            print("[推送] 企业微信：已送达")
        except Exception as ex:
            print(f"[推送] 企业微信失败（{ex.__class__.__name__}: {ex}），日报仍存于仓库")

    if email_ready():
        try:
            send_email(title, markdown)
            sent.append("邮箱")
            print(f"[推送] 邮箱：已送达 {_cfg('MAIL_TO') or _cfg('SMTP_USER')}")
        except Exception as ex:
            print(f"[推送] 邮箱失败（{ex.__class__.__name__}: {ex}），日报仍存于仓库")

    if not wecom_ready() and not email_ready():
        print("[推送] 未配置任何渠道（WECOM_WEBHOOK 或 邮箱 SMTP），本次只存档到 reports/")

    return sent
