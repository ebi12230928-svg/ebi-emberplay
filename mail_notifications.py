"""
キャンペーン・お知らせなどを、Google連携済みのメールアドレスに送信する機能。

【重要な注意点】
- 送信には、GmailのSMTP(smtp.gmail.com)を使う。管理者ご自身のGoogleアカウントで
  「アプリパスワード」(https://myaccount.google.com/apppasswords)を発行し、
  MAIL_SENDER_EMAIL・MAIL_SENDER_APP_PASSWORDとして設定する必要がある。
- PythonAnywhereの無料プランは、外部への通信先が許可リスト方式になっている。
  smtp.gmail.comが許可リストに入っていない場合、無料プランでは送信できない可能性がある。
  その場合は、PythonAnywhereのサポートへの許可リスト追加申請、または有料プランへの
  アップグレードが必要になることがある。
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import Config


def mail_configured():
    return bool(Config.MAIL_SENDER_EMAIL and Config.MAIL_SENDER_APP_PASSWORD)


def send_mail(to_email: str, subject: str, body: str):
    """
    1件のメールを送信する。設定が済んでいない場合や、送信に失敗した場合は、
    何も起きない(サイト本体の動作には影響させない)。
    """
    if not mail_configured() or not to_email:
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = Config.MAIL_SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(Config.MAIL_SENDER_EMAIL, Config.MAIL_SENDER_APP_PASSWORD)
            server.sendmail(Config.MAIL_SENDER_EMAIL, [to_email], msg.as_string())
        return True
    except Exception:
        return False


def send_mail_to_user(user, subject: str, body: str):
    """指定したユーザーが、Google連携済みであればメールを送る"""
    if not user or not user.google_email:
        return False
    return send_mail(user.google_email, subject, body)


def send_campaign_mail_all(subject: str, body: str):
    """
    Google連携済みの全ユーザーに、キャンペーン・お知らせメールを送る。
    管理画面の「お知らせを配信」機能などから呼び出すことを想定している。
    """
    from models import User

    linked_users = User.query.filter(User.google_email.isnot(None)).all()
    sent_count = 0
    for user in linked_users:
        if send_mail(user.google_email, subject, body):
            sent_count += 1
    return sent_count
