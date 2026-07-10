from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import ChatMessage, utcnow

chat_bp = Blueprint("chat", __name__)

MAX_MESSAGE_LENGTH = 500
MIN_POST_INTERVAL_SECONDS = 1.5


@chat_bp.route("/chat")
@login_required
def index():
    return render_template("chat.html")


@chat_bp.route("/chat/messages")
@login_required
def messages():
    since_id = request.args.get("since_id", type=int, default=0)

    if since_id:
        items = (
            ChatMessage.query.filter(ChatMessage.id > since_id)
            .order_by(ChatMessage.id.asc()).limit(200).all()
        )
    else:
        items = (
            ChatMessage.query.order_by(ChatMessage.id.desc()).limit(50).all()
        )
        items = list(reversed(items))

    return jsonify({
        "messages": [
            {
                "id": m.id,
                "username": m.user.username,
                "message": m.message,
                "time": m.created_at.strftime("%H:%M"),
                "is_admin": m.user.is_admin,
                "is_vip": m.user.is_vip,
            }
            for m in items
        ]
    })


@chat_bp.route("/chat/send", methods=["POST"])
@login_required
def send():
    data = request.get_json(force=True)
    text = (data.get("message") or "").strip()

    if not text:
        return jsonify({"error": "メッセージを入力してください。"}), 400
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]

    last = (
        ChatMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatMessage.created_at.desc()).first()
    )
    if last and (utcnow() - last.created_at).total_seconds() < MIN_POST_INTERVAL_SECONDS:
        return jsonify({"error": "投稿が早すぎます。少し待ってください。"}), 429

    msg = ChatMessage(user_id=current_user.id, message=text)
    db.session.add(msg)
    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({"ok": True, "id": msg.id})
