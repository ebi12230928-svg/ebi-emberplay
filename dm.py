"""フレンド間のプライベートDM機能。既読管理・新着通知(ポーリング)に対応。"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import DirectMessage, Friendship, User

dm_bp = Blueprint("dm", __name__)


def _are_friends(user_id_a, user_id_b):
    return Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(
            db.and_(Friendship.requester_id == user_id_a, Friendship.addressee_id == user_id_b),
            db.and_(Friendship.requester_id == user_id_b, Friendship.addressee_id == user_id_a),
        )
    ).first() is not None


def _my_friends():
    rows = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(Friendship.requester_id == current_user.id, Friendship.addressee_id == current_user.id)
    ).all()
    friend_ids = [r.addressee_id if r.requester_id == current_user.id else r.requester_id for r in rows]
    return User.query.filter(User.id.in_(friend_ids)).all() if friend_ids else []


@dm_bp.route("/dm")
@login_required
def index():
    friends = _my_friends()
    conversations = []
    for f in friends:
        last = (
            DirectMessage.query.filter(
                db.or_(
                    db.and_(DirectMessage.from_user_id == current_user.id, DirectMessage.to_user_id == f.id),
                    db.and_(DirectMessage.from_user_id == f.id, DirectMessage.to_user_id == current_user.id),
                )
            ).order_by(DirectMessage.created_at.desc()).first()
        )
        unread = DirectMessage.query.filter_by(from_user_id=f.id, to_user_id=current_user.id, is_read=False).count()
        conversations.append({"friend": f, "last": last, "unread": unread})

    conversations.sort(key=lambda c: c["last"].created_at if c["last"] else "", reverse=True)
    return render_template("dm_list.html", conversations=conversations)


@dm_bp.route("/dm/<int:friend_id>")
@login_required
def conversation(friend_id):
    friend = User.query.get(friend_id)
    if not friend or not _are_friends(current_user.id, friend_id):
        return render_template("dm_list.html", conversations=[], error="フレンドとのみDMできます。")

    messages = (
        DirectMessage.query.filter(
            db.or_(
                db.and_(DirectMessage.from_user_id == current_user.id, DirectMessage.to_user_id == friend_id),
                db.and_(DirectMessage.from_user_id == friend_id, DirectMessage.to_user_id == current_user.id),
            )
        ).order_by(DirectMessage.created_at.asc()).limit(200).all()
    )

    unread = DirectMessage.query.filter_by(from_user_id=friend_id, to_user_id=current_user.id, is_read=False).all()
    for m in unread:
        m.is_read = True
    if unread:
        db.session.commit()

    return render_template("dm_conversation.html", friend=friend, messages=messages)


@dm_bp.route("/dm/<int:friend_id>/send", methods=["POST"])
@login_required
def send(friend_id):
    if not _are_friends(current_user.id, friend_id):
        return jsonify({"error": "フレンドとのみDMできます。"}), 400

    text = request.get_json(force=True).get("message", "").strip()[:500]
    if not text:
        return jsonify({"error": "メッセージを入力してください。"}), 400

    msg = DirectMessage(from_user_id=current_user.id, to_user_id=friend_id, message=text)
    db.session.add(msg)
    db.session.commit()
    return jsonify({"ok": True, "id": msg.id, "created_at": msg.created_at.isoformat()})


@dm_bp.route("/dm/<int:friend_id>/poll")
@login_required
def poll_conversation(friend_id):
    after_id = request.args.get("after_id", 0, type=int)
    messages = (
        DirectMessage.query.filter(
            DirectMessage.id > after_id,
            db.or_(
                db.and_(DirectMessage.from_user_id == current_user.id, DirectMessage.to_user_id == friend_id),
                db.and_(DirectMessage.from_user_id == friend_id, DirectMessage.to_user_id == current_user.id),
            )
        ).order_by(DirectMessage.created_at.asc()).all()
    )
    unread = [m for m in messages if m.to_user_id == current_user.id and not m.is_read]
    for m in unread:
        m.is_read = True
    if unread:
        db.session.commit()

    return jsonify({
        "messages": [
            {"id": m.id, "from_me": m.from_user_id == current_user.id, "message": m.message,
             "is_read": m.is_read, "created_at": m.created_at.strftime("%H:%M")}
            for m in messages
        ]
    })


@dm_bp.route("/dm/global-poll")
@login_required
def global_poll():
    """
    全ページ共通で使うポーリング。未読DMがあれば、直近のプレビューと合計未読数を返す。
    サイトを開いている間、上部バーに通知を出すために使う。
    """
    after_id = request.args.get("after_id", 0, type=int)
    new_messages = (
        DirectMessage.query.filter(
            DirectMessage.to_user_id == current_user.id, DirectMessage.id > after_id
        ).order_by(DirectMessage.created_at.asc()).all()
    )
    total_unread = DirectMessage.query.filter_by(to_user_id=current_user.id, is_read=False).count()

    return jsonify({
        "total_unread": total_unread,
        "new_messages": [
            {"id": m.id, "from_username": m.from_user.username, "from_user_id": m.from_user_id, "message": m.message}
            for m in new_messages
        ],
        "latest_id": new_messages[-1].id if new_messages else after_id,
    })
