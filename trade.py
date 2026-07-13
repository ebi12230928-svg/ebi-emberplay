"""
フレンド間トレード機能。所持キャラクターを、同じレアリティのキャラクターとのみ交換できる。
(レアリティが変わってしまう交換は不可にすることで、価値のバランスを保つ)
"""
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import TradeOffer, UserCharacter, User, Friendship
import characters as ch

trade_bp = Blueprint("trade", __name__)


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


@trade_bp.route("/trade")
@login_required
def index():
    friends = _my_friends()
    incoming = TradeOffer.query.filter_by(to_user_id=current_user.id, status="pending").all()
    outgoing = TradeOffer.query.filter_by(from_user_id=current_user.id, status="pending").all()

    def enrich(offer):
        return {
            "id": offer.id,
            "other": offer.from_user if offer.to_user_id == current_user.id else offer.to_user,
            "offered": ch.character_info(offer.offered_character_key),
            "requested": ch.character_info(offer.requested_character_key),
        }

    return render_template(
        "trade.html", friends=friends,
        incoming=[enrich(o) for o in incoming], outgoing=[enrich(o) for o in outgoing],
    )


@trade_bp.route("/trade/with/<int:friend_id>")
@login_required
def with_friend(friend_id):
    friend = User.query.get(friend_id)
    if not friend or not _are_friends(current_user.id, friend_id):
        flash("フレンドが見つかりません。", "error")
        return redirect(url_for("trade.index"))

    def roster_for(user_id):
        rows = UserCharacter.query.filter_by(user_id=user_id).all()
        roster = []
        for row in rows:
            info = ch.character_info(row.character_key)
            if info:
                info["count"] = row.count
                roster.append(info)
        roster.sort(key=lambda c: (ch.RARITY_ORDER.index(c["rarity"]), c["name"]))
        return roster

    return render_template(
        "trade_with_friend.html", friend=friend,
        my_roster=roster_for(current_user.id), their_roster=roster_for(friend_id),
    )


@trade_bp.route("/trade/propose", methods=["POST"])
@login_required
def propose():
    data = request.get_json(force=True)
    to_user_id = data.get("to_user_id")
    offered_key = data.get("offered_key")
    requested_key = data.get("requested_key")

    if not _are_friends(current_user.id, to_user_id):
        return jsonify({"error": "フレンドとのみトレードできます。"}), 400

    my_char = UserCharacter.query.filter_by(user_id=current_user.id, character_key=offered_key).first()
    if not my_char or my_char.count < 1:
        return jsonify({"error": "そのキャラクターを持っていません。"}), 400
    their_char = UserCharacter.query.filter_by(user_id=to_user_id, character_key=requested_key).first()
    if not their_char or their_char.count < 1:
        return jsonify({"error": "相手はそのキャラクターを持っていません。"}), 400

    offered_info = ch.character_info(offered_key)
    requested_info = ch.character_info(requested_key)
    if not offered_info or not requested_info:
        return jsonify({"error": "キャラクター情報が見つかりません。"}), 400
    if offered_info["rarity"] != requested_info["rarity"]:
        return jsonify({"error": "トレードは同じレアリティのキャラクター同士でのみ行えます。"}), 400

    db.session.add(TradeOffer(
        from_user_id=current_user.id, to_user_id=to_user_id,
        offered_character_key=offered_key, requested_character_key=requested_key,
    ))
    db.session.commit()

    try:
        from notifications import notify
        notify(to_user_id, f"🔄 {current_user.username} から交換の申し出が届きました。")
        db.session.commit()
    except Exception:
        pass

    return jsonify({"ok": True})


@trade_bp.route("/trade/<int:offer_id>/respond", methods=["POST"])
@login_required
def respond(offer_id):
    offer = TradeOffer.query.get(offer_id)
    if not offer or offer.to_user_id != current_user.id or offer.status != "pending":
        return jsonify({"error": "この申し出は操作できません。"}), 400

    action = request.get_json(force=True).get("action")
    if action == "decline":
        offer.status = "declined"
        db.session.commit()
        return jsonify({"ok": True})

    if action != "accept":
        return jsonify({"error": "不正な操作です。"}), 400

    my_char = UserCharacter.query.filter_by(user_id=offer.to_user_id, character_key=offer.requested_character_key).first()
    their_char = UserCharacter.query.filter_by(user_id=offer.from_user_id, character_key=offer.offered_character_key).first()
    if not my_char or my_char.count < 1 or not their_char or their_char.count < 1:
        offer.status = "declined"
        db.session.commit()
        return jsonify({"error": "どちらかがすでにそのキャラクターを手放しています。"}), 400

    my_char.count -= 1
    their_char.count -= 1

    my_new = UserCharacter.query.filter_by(user_id=offer.to_user_id, character_key=offer.offered_character_key).first()
    if my_new:
        my_new.count += 1
    else:
        db.session.add(UserCharacter(user_id=offer.to_user_id, character_key=offer.offered_character_key, count=1))

    their_new = UserCharacter.query.filter_by(user_id=offer.from_user_id, character_key=offer.requested_character_key).first()
    if their_new:
        their_new.count += 1
    else:
        db.session.add(UserCharacter(user_id=offer.from_user_id, character_key=offer.requested_character_key, count=1))

    offer.status = "accepted"
    db.session.commit()

    try:
        from notifications import notify
        notify(offer.from_user_id, f"✅ {current_user.username} があなたの交換の申し出を承諾しました。")
        db.session.commit()
    except Exception:
        pass

    return jsonify({"ok": True})


@trade_bp.route("/trade/<int:offer_id>/cancel", methods=["POST"])
@login_required
def cancel(offer_id):
    offer = TradeOffer.query.get(offer_id)
    if offer and offer.from_user_id == current_user.id and offer.status == "pending":
        offer.status = "cancelled"
        db.session.commit()
    return jsonify({"ok": True})
