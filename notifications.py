from flask import Blueprint, render_template
from flask_login import login_required, current_user

from extensions import db
from models import Notification, User

notifications_bp = Blueprint("notifications", __name__)


def notify(user_id: int, message: str, push_title: str = "EMBERPLAY"):
    db.session.add(Notification(user_id=user_id, message=message))
    try:
        from push_notifications import send_push
        send_push(user_id, push_title, message, url="/notifications")
    except Exception:
        pass  # プッシュ通知が使えない・失敗しても、通常のお知らせ機能には影響させない


def notify_all(message: str):
    """全ユーザーに通知を送る(あわせて、Google連携済みのユーザーにはメールでも送る)"""
    user_ids = [u.id for u in User.query.with_entities(User.id).all()]
    for uid in user_ids:
        db.session.add(Notification(user_id=uid, message=message))
    try:
        from push_notifications import send_push
        for uid in user_ids:
            send_push(uid, "EMBERPLAY", message, url="/notifications")
    except Exception:
        pass
    try:
        from mail_notifications import send_campaign_mail_all
        send_campaign_mail_all("【EMBERPLAY】お知らせ", message)
    except Exception:
        pass


def notify_vips(message: str):
    """VIPユーザーにのみ通知を送る"""
    user_ids = [u.id for u in User.query.filter_by(is_vip=True).with_entities(User.id).all()]
    for uid in user_ids:
        db.session.add(Notification(user_id=uid, message=message))
    try:
        from push_notifications import send_push
        for uid in user_ids:
            send_push(uid, "EMBERPLAY", message, url="/notifications")
    except Exception:
        pass


@notifications_bp.route("/notifications")
@login_required
def list_notifications():
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_ids = [n.id for n in items if not n.is_read]
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {"is_read": True}, synchronize_session=False
        )
        db.session.commit()
    return render_template("notifications.html", items=items)
