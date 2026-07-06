from flask import Blueprint, render_template
from flask_login import login_required, current_user

from extensions import db
from models import Notification, User

notifications_bp = Blueprint("notifications", __name__)


def notify(user_id: int, message: str):
    db.session.add(Notification(user_id=user_id, message=message))


def notify_all(message: str):
    """全ユーザーに通知を送る"""
    user_ids = [u.id for u in User.query.with_entities(User.id).all()]
    for uid in user_ids:
        db.session.add(Notification(user_id=uid, message=message))


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
