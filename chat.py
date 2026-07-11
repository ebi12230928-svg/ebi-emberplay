from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import ChatMessage, ChatReaction, utcnow

chat_bp = Blueprint("chat", __name__)

MAX_MESSAGE_LENGTH = 500
MIN_POST_INTERVAL_SECONDS = 1.5
REACTION_EMOJIS = ["👍", "😂", "🔥", "😢", "🎉"]


@chat_bp.route("/chat")
@login_required
def index():
    return render_template("chat.html", reaction_emojis=REACTION_EMOJIS)


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

    message_ids = [m.id for m in items]
    reactions_by_message = {}
    if message_ids:
        rows = ChatReaction.query.filter(ChatReaction.message_id.in_(message_ids)).all()
        for r in rows:
            reactions_by_message.setdefault(r.message_id, {})
            reactions_by_message[r.message_id][r.emoji] = reactions_by_message[r.message_id].get(r.emoji, 0) + 1

    return jsonify({
        "messages": [
            {
                "id": m.id,
                "username": m.user.username,
                "avatar": m.user.avatar,
                "message": m.message,
                "time": m.created_at.strftime("%H:%M"),
                "is_admin": m.user.is_admin,
                "is_vip": m.user.is_vip,
                "reactions": reactions_by_message.get(m.id, {}),
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


@chat_bp.route("/chat/react", methods=["POST"])
@login_required
def react():
    data = request.get_json(force=True)
    message_id = data.get("message_id")
    emoji = data.get("emoji")

    if emoji not in REACTION_EMOJIS:
        return jsonify({"error": "使用できない絵文字です。"}), 400

    message = ChatMessage.query.get(message_id)
    if not message:
        return jsonify({"error": "メッセージが見つかりません。"}), 400

    existing = ChatReaction.query.filter_by(message_id=message_id, user_id=current_user.id).first()
    if existing and existing.emoji == emoji:
        db.session.delete(existing)  # 同じ絵文字をもう一度押したら取り消し
    elif existing:
        existing.emoji = emoji  # 別の絵文字に変更
    else:
        db.session.add(ChatReaction(message_id=message_id, user_id=current_user.id, emoji=emoji))
    db.session.commit()

    rows = ChatReaction.query.filter_by(message_id=message_id).all()
    counts = {}
    for r in rows:
        counts[r.emoji] = counts.get(r.emoji, 0) + 1

    return jsonify({"ok": True, "reactions": counts})
