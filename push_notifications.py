"""
PWA(アプリとして追加した場合)でのプッシュ通知機能。

仕組み:
1. ユーザーがアプリで通知を許可すると、ブラウザから「購読情報」(endpoint・鍵)が発行される
2. その購読情報をサーバー(PushSubscriptionテーブル)に保存しておく
3. DM・お知らせなどが届いた際に、保存しておいた購読情報を使ってプッシュ通知を送信する
   (送信には pywebpush ライブラリを使う。VAPID鍵という、送信元を証明するための鍵ペアが必要)

【重要な注意点】
PythonAnywhereの無料プランは、外部への通信先が許可リスト(ホワイトリスト)方式になっている。
プッシュ通知の送信先(Googleのfcm.googleapis.com、Mozillaのpush.services.mozilla.com、
Appleのweb.push.apple.comなど、ブラウザによって異なる)が許可リストに入っていない場合、
無料プランでは実際にプッシュ通知を送信できない可能性がある。その場合は、PythonAnywhereの
サポートに許可リストへの追加を申請するか、有料プランへのアップグレードが必要になる。
"""
import json

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from config import Config
from models import PushSubscription

push_bp = Blueprint("push", __name__)


def push_configured():
    """管理者がVAPID鍵の設定を済ませているかどうか"""
    return bool(Config.VAPID_PUBLIC_KEY and Config.VAPID_PRIVATE_KEY)


@push_bp.route("/push/subscribe", methods=["POST"])
@login_required
def subscribe():
    """ブラウザから発行された購読情報を保存する"""
    data = request.get_json(force=True)
    endpoint = data.get("endpoint", "")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    if not endpoint or not p256dh or not auth:
        return jsonify({"ok": False}), 400

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh_key = p256dh
        existing.auth_key = auth
    else:
        db.session.add(PushSubscription(
            user_id=current_user.id, endpoint=endpoint, p256dh_key=p256dh, auth_key=auth,
        ))
    db.session.commit()
    return jsonify({"ok": True})


@push_bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    data = request.get_json(force=True)
    endpoint = data.get("endpoint", "")
    PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


def send_push(user_id: int, title: str, body: str, url: str = "/"):
    """
    指定したユーザーの、登録済みの全端末にプッシュ通知を送る。
    VAPID鍵が未設定の場合や、送信に失敗した場合は、何も起きない(サイトの動作は止めない)。
    """
    if not push_configured():
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return  # pywebpushがインストールされていない環境では、何もしない

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    payload = json.dumps({"title": title, "body": body, "url": url})

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
                },
                data=payload,
                vapid_private_key=Config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": Config.VAPID_CONTACT_EMAIL},
            )
        except WebPushException as e:
            # 購読が無効になっている(端末側で通知をオフにした等)場合は、登録を削除しておく
            if "410" in str(e) or "404" in str(e):
                db.session.delete(sub)
                db.session.commit()
        except Exception:
            pass  # プッシュ通知の送信失敗が、サイト本体の動作に影響しないようにする
