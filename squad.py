"""
フレンドと協力プレイするための「部屋」機能。タワーディフェンス・RPGボス討伐で共通利用する。
参加人数が増えるほど敵が強くなり、報酬は参加者全員に配られる。
"""
import json

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from extensions import db
from models import SquadRoom, SquadMember, Friendship, UserCharacter
import characters as ch

squad_bp = Blueprint("squad", __name__)

MAX_MEMBERS = 4
MAX_CHARACTERS_PER_MEMBER = 4


def difficulty_scale(member_count):
    """参加人数に応じた難易度倍率(敵のHP・数に掛け合わせる)。1人なら1.0倍、増えるごとに緩やかに強化"""
    return round(1 + (member_count - 1) * 0.65, 2)


def _is_friend(user_id_a, user_id_b):
    if user_id_a == user_id_b:
        return True
    return Friendship.query.filter(
        Friendship.status == "accepted",
        or_(
            and_(Friendship.requester_id == user_id_a, Friendship.addressee_id == user_id_b),
            and_(Friendship.requester_id == user_id_b, Friendship.addressee_id == user_id_a),
        )
    ).first() is not None


def _room_view(room):
    members = SquadMember.query.filter_by(room_id=room.id).all()
    return {
        "id": room.id, "mode": room.mode, "status": room.status, "host_id": room.host_id,
        "host_username": room.host.username,
        "members": [
            {
                "user_id": m.user_id, "username": m.user.username, "avatar": m.user.avatar,
                "ready": m.ready, "characters": json.loads(m.character_keys_json),
            }
            for m in members
        ],
        "difficulty_scale": difficulty_scale(len(members)),
        "result": json.loads(room.result_json) if room.result_json else None,
    }


@squad_bp.route("/squad/<mode>")
@login_required
def lobby(mode):
    if mode not in ("towerdefense", "rpgboss"):
        return redirect(url_for("lobby.index"))

    # フレンドが開いている募集中の部屋一覧
    friend_ids = set()
    for f in Friendship.query.filter(
        Friendship.status == "accepted",
        or_(Friendship.requester_id == current_user.id, Friendship.addressee_id == current_user.id),
    ).all():
        friend_ids.add(f.addressee_id if f.requester_id == current_user.id else f.requester_id)

    open_rooms = []
    if friend_ids:
        candidates = SquadRoom.query.filter(
            SquadRoom.mode == mode, SquadRoom.status == "forming", SquadRoom.host_id.in_(friend_ids)
        ).all()
        open_rooms = [_room_view(r) for r in candidates]

    # 自分が既に参加している、進行中の部屋があるか確認
    my_room = None
    my_memberships = SquadMember.query.filter_by(user_id=current_user.id).all()
    for m in my_memberships:
        candidate_room = SquadRoom.query.get(m.room_id)
        if candidate_room and candidate_room.mode == mode and candidate_room.status != "finished":
            my_room = candidate_room
            break

    owned_characters = UserCharacter.query.filter_by(user_id=current_user.id).all()
    roster = []
    for row in owned_characters:
        info = ch.stats_at_level(row.character_key, row.count)
        if info:
            roster.append(info)

    return render_template(
        "squad_lobby.html", mode=mode, open_rooms=open_rooms, my_room=_room_view(my_room) if my_room else None,
        roster=roster, max_members=MAX_MEMBERS, max_chars=MAX_CHARACTERS_PER_MEMBER
    )


@squad_bp.route("/squad/<mode>/create", methods=["POST"])
@login_required
def create(mode):
    if mode not in ("towerdefense", "rpgboss"):
        return redirect(url_for("lobby.index"))

    room = SquadRoom(host_id=current_user.id, mode=mode)
    db.session.add(room)
    db.session.flush()
    db.session.add(SquadMember(room_id=room.id, user_id=current_user.id))
    db.session.commit()

    return redirect(url_for("squad.room", room_id=room.id))


@squad_bp.route("/squad/room/<int:room_id>")
@login_required
def room(room_id):
    room_obj = SquadRoom.query.get(room_id)
    if not room_obj:
        flash("部屋が見つかりません。", "error")
        return redirect(url_for("lobby.index"))

    member = SquadMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member:
        if not _is_friend(current_user.id, room_obj.host_id):
            flash("フレンドの部屋にのみ参加できます。", "error")
            return redirect(url_for("squad.lobby", mode=room_obj.mode))
        if SquadMember.query.filter_by(room_id=room_id).count() >= MAX_MEMBERS:
            flash("この部屋は満員です。", "error")
            return redirect(url_for("squad.lobby", mode=room_obj.mode))
        db.session.add(SquadMember(room_id=room_id, user_id=current_user.id))
        db.session.commit()

    owned_characters = UserCharacter.query.filter_by(user_id=current_user.id).all()
    roster = []
    for row in owned_characters:
        info = ch.stats_at_level(row.character_key, row.count)
        if info:
            roster.append(info)

    return render_template(
        "squad_room.html", room=_room_view(room_obj), roster=roster,
        is_host=(room_obj.host_id == current_user.id), max_chars=MAX_CHARACTERS_PER_MEMBER,
        max_members=MAX_MEMBERS
    )


@squad_bp.route("/squad/room/<int:room_id>/poll")
@login_required
def poll(room_id):
    room_obj = SquadRoom.query.get(room_id)
    if not room_obj:
        return jsonify({"error": "部屋が見つかりません。"}), 404
    return jsonify(_room_view(room_obj))


@squad_bp.route("/squad/room/<int:room_id>/select", methods=["POST"])
@login_required
def select_characters(room_id):
    member = SquadMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member:
        return jsonify({"error": "この部屋の参加者ではありません。"}), 400

    data = request.get_json(force=True)
    keys = data.get("characters") or []
    if not isinstance(keys, list) or len(keys) > MAX_CHARACTERS_PER_MEMBER:
        return jsonify({"error": "選択できるキャラクター数を超えています。"}), 400

    owned_keys = {c.character_key for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    if not all(k in owned_keys for k in keys):
        return jsonify({"error": "所持していないキャラクターが含まれています。"}), 400

    member.character_keys_json = json.dumps(keys)
    db.session.commit()
    return jsonify({"ok": True})


@squad_bp.route("/squad/room/<int:room_id>/ready", methods=["POST"])
@login_required
def toggle_ready(room_id):
    member = SquadMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member:
        return jsonify({"error": "この部屋の参加者ではありません。"}), 400

    member.ready = not member.ready
    db.session.commit()
    return jsonify({"ready": member.ready})


@squad_bp.route("/squad/room/<int:room_id>/leave", methods=["POST"])
@login_required
def leave(room_id):
    room_obj = SquadRoom.query.get(room_id)
    member = SquadMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if member:
        db.session.delete(member)
        db.session.commit()

    if room_obj and room_obj.host_id == current_user.id:
        # ホストが抜けたら部屋ごと解散する
        SquadMember.query.filter_by(room_id=room_id).delete()
        db.session.delete(room_obj)
        db.session.commit()
        return redirect(url_for("lobby.index"))

    return redirect(url_for("squad.lobby", mode=room_obj.mode if room_obj else "towerdefense"))


@squad_bp.route("/squad/room/<int:room_id>/start", methods=["POST"])
@login_required
def start(room_id):
    room_obj = SquadRoom.query.get(room_id)
    if not room_obj or room_obj.host_id != current_user.id:
        return jsonify({"error": "ホストのみ開始できます。"}), 403

    members = SquadMember.query.filter_by(room_id=room_id).all()
    if not all(m.ready for m in members):
        return jsonify({"error": "全員の準備が完了していません。"}), 400
    if not any(json.loads(m.character_keys_json) for m in members):
        return jsonify({"error": "誰もキャラクターを選択していません。"}), 400

    room_obj.status = "battling"
    db.session.commit()
    return jsonify({"ok": True})


@squad_bp.route("/squad/room/<int:room_id>/complete", methods=["POST"])
@login_required
def complete(room_id):
    """
    協力プレイの結果を報告し、参加者全員に報酬を配る(ホストのみ呼び出し可能)。
    タワーディフェンス専用(RPGボス討伐は rpgboss.squad_battle が結果報告・報酬付与を一括で行う)。
    """
    room_obj = SquadRoom.query.get(room_id)
    if not room_obj or room_obj.host_id != current_user.id or room_obj.status != "battling":
        return jsonify({"error": "この部屋では結果を報告できません。"}), 400
    if room_obj.mode != "towerdefense":
        return jsonify({"error": "このモードでは専用のエンドポイントを使ってください。"}), 400

    from towerdefense import TD_MODES, ENDLESS_REWARD_CAP_WAVES

    data = request.get_json(force=True)
    td_mode = data.get("mode", "normal")
    if td_mode not in ("normal", "raid", "lastboss"):
        td_mode = "normal"
    cfg = TD_MODES[td_mode]

    try:
        waves_cleared = int(data.get("waves_cleared", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "結果データが不正です。"}), 400
    waves_cleared = max(0, min(cfg["waves"], waves_cleared))
    victory = waves_cleared >= cfg["waves"]

    reward_waves = min(waves_cleared, ENDLESS_REWARD_CAP_WAVES)
    base_reward = reward_waves * cfg["reward_per_wave"] + (cfg["victory_bonus"] if victory else 0)

    members = SquadMember.query.filter_by(room_id=room_id).all()
    from models import Transaction
    for m in members:
        from games.common import credit_reward
        credit_reward(m.user, base_reward)
        db.session.add(Transaction(
            user_id=m.user_id, amount=base_reward, kind="squad_towerdefense",
            description=f"協力タワーディフェンス({cfg['label']}・{len(members)}人)の報酬"
        ))

    room_obj.status = "finished"
    room_obj.result_json = json.dumps({"waves_cleared": waves_cleared, "victory": victory})
    db.session.commit()

    try:
        from achievements import check_achievements
        for m in members:
            check_achievements(m.user)
    except Exception:
        pass

    return jsonify({
        "ok": True, "reward_each": base_reward, "member_count": len(members), "balance": current_user.balance
    })
