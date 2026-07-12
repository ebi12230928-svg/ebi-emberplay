"""
トランプ(大富豪・ババ抜き・スピード)をフレンドと遊ぶための部屋機能。
参加コードで入室し、オーナーがゲーム種類・ルールを決めて開始する。
実際の対局ロジックは games/daifugo_logic.py・babanuki_logic.py・speed_logic.py が担う。
"""
import json
import random
import string

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import CardRoom, CardRoomPlayer, CardGameState, User
from games import daifugo_logic, babanuki_logic, speed_logic, cards_common as cc

cardroom_bp = Blueprint("cardroom", __name__)

GAME_LABELS = {"daifugo": "大富豪", "babanuki": "ババ抜き", "speed": "スピード"}
GAME_MODULES = {"daifugo": daifugo_logic, "babanuki": babanuki_logic, "speed": speed_logic}
MIN_PLAYERS = {"daifugo": 2, "babanuki": 2, "speed": 2}
MAX_PLAYERS = {"daifugo": 6, "babanuki": 6, "speed": 2}


def _generate_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not CardRoom.query.filter_by(code=code).first():
            return code


def _room_players(room_id):
    return CardRoomPlayer.query.filter_by(room_id=room_id).order_by(CardRoomPlayer.seat_index).all()


@cardroom_bp.route("/cards")
@login_required
def index():
    my_rooms = (
        db.session.query(CardRoom)
        .join(CardRoomPlayer, CardRoomPlayer.room_id == CardRoom.id)
        .filter(CardRoomPlayer.user_id == current_user.id, CardRoom.status != "finished")
        .all()
    )
    return render_template("cardroom_lobby.html", game_labels=GAME_LABELS, my_rooms=my_rooms)


@cardroom_bp.route("/cards/create", methods=["POST"])
@login_required
def create():
    game_type = request.form.get("game_type", "daifugo")
    if game_type not in GAME_LABELS:
        flash("ゲームの種類が不正です。", "error")
        return redirect(url_for("cardroom.index"))

    room = CardRoom(code=_generate_code(), owner_id=current_user.id, game_type=game_type)
    db.session.add(room)
    db.session.flush()
    db.session.add(CardRoomPlayer(room_id=room.id, user_id=current_user.id, seat_index=0))
    db.session.commit()
    return redirect(url_for("cardroom.room", code=room.code))


@cardroom_bp.route("/cards/join", methods=["POST"])
@login_required
def join():
    code = request.form.get("code", "").strip().upper()
    room = CardRoom.query.filter_by(code=code).first()
    if not room:
        flash("その参加コードの部屋が見つかりません。", "error")
        return redirect(url_for("cardroom.index"))
    if room.status != "waiting":
        flash("この部屋はすでにゲームが始まっています。", "error")
        return redirect(url_for("cardroom.index"))

    existing = CardRoomPlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    if not existing:
        players = _room_players(room.id)
        if len(players) >= MAX_PLAYERS.get(room.game_type, 6):
            flash("この部屋は満員です。", "error")
            return redirect(url_for("cardroom.index"))
        db.session.add(CardRoomPlayer(room_id=room.id, user_id=current_user.id, seat_index=len(players)))
        db.session.commit()
    return redirect(url_for("cardroom.room", code=room.code))


@cardroom_bp.route("/cards/room/<code>")
@login_required
def room(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        flash("部屋が見つかりません。", "error")
        return redirect(url_for("cardroom.index"))

    is_member = CardRoomPlayer.query.filter_by(room_id=room_obj.id, user_id=current_user.id).first()
    if not is_member:
        if room_obj.status != "waiting":
            flash("この部屋はすでにゲームが始まっています。", "error")
            return redirect(url_for("cardroom.index"))
        players = _room_players(room_obj.id)
        if len(players) >= MAX_PLAYERS.get(room_obj.game_type, 6):
            flash("この部屋は満員です。", "error")
            return redirect(url_for("cardroom.index"))
        db.session.add(CardRoomPlayer(room_id=room_obj.id, user_id=current_user.id, seat_index=len(players)))
        db.session.commit()

    if room_obj.status == "playing":
        return redirect(url_for("cardroom.play", code=room_obj.code))

    return render_template(
        "cardroom_room.html", room=room_obj, game_labels=GAME_LABELS,
        is_owner=(room_obj.owner_id == current_user.id),
        min_players=MIN_PLAYERS, max_players=MAX_PLAYERS,
    )


@cardroom_bp.route("/cards/room/<code>/poll")
@login_required
def room_poll(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        return jsonify({"error": "部屋が見つかりません。"}), 404
    players = _room_players(room_obj.id)
    return jsonify({
        "status": room_obj.status, "game_type": room_obj.game_type,
        "rules": json.loads(room_obj.rules_json),
        "players": [{"user_id": p.user_id, "username": p.user.username} for p in players],
    })


@cardroom_bp.route("/cards/room/<code>/set-game", methods=["POST"])
@login_required
def set_game(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj or room_obj.owner_id != current_user.id:
        return jsonify({"error": "オーナーのみ設定できます。"}), 403
    if room_obj.status != "waiting":
        return jsonify({"error": "すでにゲームが始まっています。"}), 400

    data = request.get_json(force=True)
    game_type = data.get("game_type")
    if game_type not in GAME_LABELS:
        return jsonify({"error": "ゲームの種類が不正です。"}), 400

    rules = data.get("rules") or {}
    room_obj.game_type = game_type
    room_obj.rules_json = json.dumps({
        "eight_giri": bool(rules.get("eight_giri")),
        "revolution": bool(rules.get("revolution")),
    })
    db.session.commit()
    return jsonify({"ok": True})


@cardroom_bp.route("/cards/room/<code>/start", methods=["POST"])
@login_required
def start(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj or room_obj.owner_id != current_user.id:
        return jsonify({"error": "オーナーのみ開始できます。"}), 403
    if room_obj.status != "waiting":
        return jsonify({"error": "すでにゲームが始まっています。"}), 400

    players = _room_players(room_obj.id)
    min_p, max_p = MIN_PLAYERS[room_obj.game_type], MAX_PLAYERS[room_obj.game_type]
    if not (min_p <= len(players) <= max_p):
        return jsonify({"error": f"{room_obj.game_type}は{min_p}〜{max_p}人で遊べます(現在{len(players)}人)。"}), 400

    module = GAME_MODULES[room_obj.game_type]
    rules = json.loads(room_obj.rules_json)
    player_ids = [p.user_id for p in players]
    state = module.new_game(player_ids, rules)

    existing_state = CardGameState.query.get(room_obj.id)
    if existing_state:
        existing_state.state_json = json.dumps(state)
    else:
        db.session.add(CardGameState(room_id=room_obj.id, state_json=json.dumps(state)))
    room_obj.status = "playing"
    db.session.commit()
    return jsonify({"ok": True})


@cardroom_bp.route("/cards/room/<code>/leave", methods=["POST"])
@login_required
def leave(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if room_obj:
        member = CardRoomPlayer.query.filter_by(room_id=room_obj.id, user_id=current_user.id).first()
        if member:
            db.session.delete(member)
            db.session.commit()
        if room_obj.owner_id == current_user.id and room_obj.status == "waiting":
            CardRoomPlayer.query.filter_by(room_id=room_obj.id).delete()
            state = CardGameState.query.get(room_obj.id)
            if state:
                db.session.delete(state)
            db.session.delete(room_obj)
            db.session.commit()
    return redirect(url_for("cardroom.index"))


def _build_public_state(room_obj, state, viewer_id, names_by_id):
    """自分の手札は見せて、他人の手札は枚数だけ見せる形に整形する"""
    hands_public = {}
    for uid_str, hand in state.get("hands", {}).items():
        if int(uid_str) == viewer_id:
            hands_public[uid_str] = hand
        else:
            hands_public[uid_str] = ["?"] * len(hand)

    public = {
        "game_type": room_obj.game_type, "hands": hands_public,
        "turn_order": state.get("turn_order", []),
        "names": {str(k): v for k, v in names_by_id.items()}, "log": state.get("log", [])[-15:],
    }

    module = GAME_MODULES[room_obj.game_type]
    if room_obj.game_type == "daifugo":
        public.update({
            "pile": state.get("pile", []), "finished_order": state.get("finished_order", []),
            "current_turn": module.current_turn_player(state), "revolution": state.get("revolution", False),
        })
    elif room_obj.game_type == "babanuki":
        public.update({
            "out": state.get("out", []), "loser": state.get("loser"),
            "current_turn": module.current_turn_player(state),
        })
    elif room_obj.game_type == "speed":
        public.update({
            "center": state.get("center", []), "winner": state.get("winner"),
            "stock_counts": {k: len(v) for k, v in state.get("stocks", {}).items()},
        })
    return public


@cardroom_bp.route("/cards/room/<code>/play")
@login_required
def play(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        flash("部屋が見つかりません。", "error")
        return redirect(url_for("cardroom.index"))
    member = CardRoomPlayer.query.filter_by(room_id=room_obj.id, user_id=current_user.id).first()
    if not member:
        flash("この部屋の参加者ではありません。", "error")
        return redirect(url_for("cardroom.index"))
    return render_template("cardroom_play.html", room=room_obj, game_labels=GAME_LABELS)


@cardroom_bp.route("/cards/room/<code>/state")
@login_required
def game_state(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        return jsonify({"error": "部屋が見つかりません。"}), 404
    state_row = CardGameState.query.get(room_obj.id)
    if not state_row:
        return jsonify({"error": "ゲームがまだ始まっていません。"}), 400

    state = json.loads(state_row.state_json)
    players = _room_players(room_obj.id)
    names_by_id = {p.user_id: p.user.username for p in players}
    public = _build_public_state(room_obj, state, current_user.id, names_by_id)
    public["status"] = room_obj.status
    public["my_id"] = current_user.id
    return jsonify(public)


@cardroom_bp.route("/cards/room/<code>/action", methods=["POST"])
@login_required
def action(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj or room_obj.status != "playing":
        return jsonify({"error": "プレイ中の部屋ではありません。"}), 400
    state_row = CardGameState.query.get(room_obj.id)
    if not state_row:
        return jsonify({"error": "ゲーム状態が見つかりません。"}), 400

    state = json.loads(state_row.state_json)
    module = GAME_MODULES[room_obj.game_type]
    data = request.get_json(force=True)
    action_type = data.get("type")
    err = None

    if room_obj.game_type == "daifugo":
        if action_type == "play":
            cards = data.get("cards") or []
            err = module.apply_play(state, current_user.id, cards)
        elif action_type == "pass":
            err = module.apply_pass(state, current_user.id)
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "babanuki":
        if action_type == "draw":
            err = module.apply_draw(state, current_user.id)
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "speed":
        if action_type == "play":
            card = data.get("card")
            pile_idx = data.get("pile_idx")
            err = module.apply_play(state, current_user.id, card, pile_idx)
        elif action_type == "refill_check":
            if module.both_stuck(state):
                module.refill_center(state)
        else:
            err = "不正な操作です。"

    if err:
        return jsonify({"error": err}), 400

    state_row.state_json = json.dumps(state)

    finished = False
    if room_obj.game_type == "daifugo" and len(state.get("finished_order", [])) >= len(state.get("turn_order", [])) - 1:
        finished = True
    elif room_obj.game_type == "babanuki" and state.get("loser") is not None:
        finished = True
    elif room_obj.game_type == "speed" and state.get("winner") is not None:
        finished = True

    if finished:
        room_obj.status = "finished"

    db.session.commit()
    return jsonify({"ok": True})
