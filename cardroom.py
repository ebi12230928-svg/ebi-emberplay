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
from models import CardRoom, CardRoomPlayer, CardGameState, User, RoomChatMessage
from games import (
    daifugo_logic, babanuki_logic, speed_logic, uno_logic, sevens_logic,
    gomoku_logic, othello_logic, checkers_logic, morris_logic, shogi_logic,
    tictactoe_logic, connect4_logic, chess_logic, concentration_logic,
    bot_ai, cards_common as cc,
)

cardroom_bp = Blueprint("cardroom", __name__)

CARD_GAMES = {"daifugo", "babanuki", "speed", "uno", "sevens", "concentration"}
BOARD_GAMES = {"gomoku", "othello", "checkers", "morris", "shogi", "tictactoe", "connect4", "chess"}

GAME_LABELS = {
    "daifugo": "大富豪", "babanuki": "ババ抜き", "speed": "スピード", "uno": "UNO",
    "sevens": "七並べ", "concentration": "神経衰弱",
    "gomoku": "五目並べ", "othello": "オセロ", "checkers": "チェッカー",
    "morris": "ナインメンズモリス", "shogi": "将棋", "tictactoe": "三目並べ",
    "connect4": "コネクトフォー", "chess": "チェス",
}
GAME_MODULES = {
    "daifugo": daifugo_logic, "babanuki": babanuki_logic, "speed": speed_logic, "uno": uno_logic,
    "sevens": sevens_logic, "concentration": concentration_logic,
    "gomoku": gomoku_logic, "othello": othello_logic, "checkers": checkers_logic,
    "morris": morris_logic, "shogi": shogi_logic, "tictactoe": tictactoe_logic,
    "connect4": connect4_logic, "chess": chess_logic,
}
MIN_PLAYERS = {
    "daifugo": 2, "babanuki": 2, "speed": 2, "uno": 2, "sevens": 2, "concentration": 2,
    "gomoku": 2, "othello": 2, "checkers": 2, "morris": 2, "shogi": 2,
    "tictactoe": 2, "connect4": 2, "chess": 2,
}
MAX_PLAYERS = {
    "daifugo": 6, "babanuki": 6, "speed": 2, "uno": 6, "sevens": 6, "concentration": 4,
    "gomoku": 2, "othello": 2, "checkers": 2, "morris": 2, "shogi": 2,
    "tictactoe": 2, "connect4": 2, "chess": 2,
}

HOW_TO_PLAY = {
    "daifugo": "場に出ているカードと同じ枚数・同じランクのカードを、より強いランクで出していきます。出せない、または出したくない時はパスできます。全員パスすると場が流れ、最後に出した人から再スタート。手札を先に無くした人から1位・2位…と順位が決まります。オーナーは「8切り」(8を出すと場が流れる)・「革命」(4枚同時出しで強さが逆転)のルールをオン/オフできます。",
    "babanuki": "配られた手札から、最初にペア(同じランク2枚)を全て捨てます。自分の番になったら、左隣のプレイヤーの手札から見ずに1枚引きます。引いた札が手元とペアになれば自動で捨てられます。手札が無くなった人から上がり。最後までジョーカーを持っていた人の負けです。",
    "speed": "2人専用。場に2つの札があり、そこに手札から「1つ大きい」か「1つ小さい」ランクのカードをどんどん出していきます(手番なし、早い者勝ち)。手札を出すたびに補充札から1枚補充されます。お互い出せなくなったら、両者の補充札から場を作り直します。先に手札と補充札を全部出し切った方の勝ちです。",
    "uno": "場のカードと同じ色・同じ数字・同じ記号、またはワイルドカードを出せます。出せる札がなければ山札から1枚引きます。スキップ(次の人を飛ばす)・リバース(順番を逆に)・ドロー2/ワイルドドロー4(次の人が引いて休み)などの効果札もあります。手札を先に出し切った人の勝ちです。",
    "sevens": "各スートの7から始めて、その両隣の数字を順番に出していきます(例: 7の次に6か8)。出せるカードがなければパス。手札を先に出し切った人の勝ちです。",
    "concentration": "52枚を裏向きに並べ、自分の番に2枚めくります。同じランクならペア成立でもう一度めくれます。外れたら次の人の番です。全て揃った時点で、一番多くペアを取った人の勝ちです。",
    "gomoku": "15×15の盤面に交互に石を置きます。縦・横・斜めのいずれかに自分の石を5つ連続で並べたら勝ちです。",
    "othello": "8×8の盤面で、相手の石を自分の石で挟むとひっくり返せます。挟める場所がない時はパスになります。両者とも置ける場所がなくなったら終了し、石の数が多い方の勝ちです。",
    "checkers": "8×8盤面の暗い升目だけを使います。駒は斜め前方にのみ進めます(相手の陣地に到達するとキングになり、斜め全方向に動けます)。相手の駒に隣接していて、その先が空いていれば飛び越えて相手の駒を取れます。取れる時は取らなければなりません。相手の駒を全て取ったら勝ちです。",
    "morris": "24個の交点を持つ盤面を使います。前半は交互に持ち駒(各9個)を置いていき(配置フェーズ)、縦か横に3つ並べる「ミル」を作ると相手の駒を1つ取れます。全部置き終わったら、隣接する交点へ駒を動かす「移動フェーズ」になります(駒が3個になると、どこへでも動ける「フライ」が可能に)。相手の駒が3個未満になったら勝ちです。",
    "shogi": "9×9の盤面を使う日本の伝統的なボードゲームです。歩・香車・桂馬・銀・金・角・飛車・王将(玉将)を、それぞれ決まった動き方で進めます。敵陣(奥の3段)に入ると「成る」ことができ、多くの駒がより強い動きに変化します。取った相手の駒は自分の持ち駒になり、盤上の空いているマスに「打つ」ことができます。相手の王を取ったら勝ちです(※このアプリでは実装を簡略化しており、王手放置の禁止・詰みの厳密な判定・二歩や打ち歩詰めなどの細かい反則は判定していません)。",
    "tictactoe": "3×3の盤面に交互に印を置きます。縦・横・斜めのいずれかに3つ並べたら勝ちです。",
    "connect4": "7列6行の盤面に、交互にコマを列の一番下から落としていきます。縦・横・斜めのいずれかに4つ並べたら勝ちです。",
    "chess": "8×8の盤面を使う西洋のチェスです。ポーン・ナイト・ビショップ・ルーク・クイーン・キングをそれぞれ決まった動き方で進めます。ポーンは最終段に到達すると自動でクイーンに昇格します。相手のキングを取ったら勝ちです(※このアプリでは実装を簡略化しており、詰みの厳密な判定・キャスリング・アンパッサンは判定していません)。",
}


def _generate_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not CardRoom.query.filter_by(code=code).first():
            return code


def _room_players(room_id):
    return CardRoomPlayer.query.filter_by(room_id=room_id).order_by(CardRoomPlayer.seat_index).all()


BOT_NAMES = {"easy": "CPU(弱い)", "normal": "CPU(普通)", "hard": "CPU(強い)"}


def _create_bot_user(difficulty):
    import uuid
    username = f"{BOT_NAMES.get(difficulty, 'CPU')}-{uuid.uuid4().hex[:4]}"
    bot = User(username=username, password_hash="", balance=0, is_bot=True, bot_difficulty=difficulty)
    db.session.add(bot)
    db.session.flush()
    return bot


def _resolve_new_log_lines(state, actor_id, start_idx, names_by_id):
    log_list = state.get("log", [])
    for i in range(start_idx, len(log_list)):
        line = log_list[i]
        if "{name}" in line:
            line = line.replace("{name}", names_by_id.get(actor_id, "??"))
        if "{loser_name}" in line and state.get("loser") is not None:
            line = line.replace("{loser_name}", names_by_id.get(state["loser"], "??"))
        if "{target_name}" in line:
            others = [n for uid, n in names_by_id.items() if uid != actor_id]
            line = line.replace("{target_name}", others[0] if others else "相手")
        log_list[i] = line


def _process_bot_turns(room_obj, state, names_by_id=None):
    """ボットの手番が続く限り自動で打ち続け、それぞれの行動ログも名前解決する"""
    module = GAME_MODULES[room_obj.game_type]
    players = _room_players(room_obj.id)
    if names_by_id is None:
        names_by_id = {p.user_id: p.user.username for p in players}
    bot_ids = {p.user_id: p.user.bot_difficulty for p in players if p.user.is_bot}
    if not bot_ids:
        return

    if room_obj.game_type == "speed":
        # スピードには手番の概念が無いため、出せるボットがいなくなるまで順番に打たせる
        safety = 0
        while safety < 200:
            safety += 1
            if state.get("winner") is not None:
                break
            any_moved = False
            for bot_id, diff in bot_ids.items():
                before_len = len(state.get("log", []))
                if bot_ai.bot_move("speed", module, state, bot_id, diff):
                    _resolve_new_log_lines(state, bot_id, before_len, names_by_id)
                    any_moved = True
                if state.get("winner") is not None:
                    break
            if not any_moved:
                if module.both_stuck(state):
                    module.refill_center(state)
                else:
                    break
        return

    safety = 0
    while safety < 200:
        safety += 1
        if state.get("winner") is not None or state.get("is_draw"):
            break
        cur = module.current_turn_player(state)
        if cur is None or cur not in bot_ids:
            break
        before_len = len(state.get("log", []))
        ok = bot_ai.bot_move(room_obj.game_type, module, state, cur, bot_ids.get(cur, "normal"))
        if not ok:
            break
        _resolve_new_log_lines(state, cur, before_len, names_by_id)


@cardroom_bp.route("/cards/room/<code>/add-bot", methods=["POST"])
@login_required
def add_bot(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj or room_obj.owner_id != current_user.id:
        return jsonify({"error": "オーナーのみボットを追加できます。"}), 403
    if room_obj.status != "waiting":
        return jsonify({"error": "すでにゲームが始まっています。"}), 400

    difficulty = request.get_json(force=True).get("difficulty", "normal")
    if difficulty not in ("easy", "normal", "hard"):
        difficulty = "normal"

    players = _room_players(room_obj.id)
    if len(players) >= MAX_PLAYERS.get(room_obj.game_type, 6):
        return jsonify({"error": "この部屋は満員です。"}), 400

    bot = _create_bot_user(difficulty)
    db.session.add(CardRoomPlayer(room_id=room_obj.id, user_id=bot.id, seat_index=len(players)))
    db.session.commit()
    return jsonify({"ok": True})


@cardroom_bp.route("/cards/room/<code>/remove-player", methods=["POST"])
@login_required
def remove_player(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj or room_obj.owner_id != current_user.id:
        return jsonify({"error": "オーナーのみ操作できます。"}), 403
    if room_obj.status != "waiting":
        return jsonify({"error": "すでにゲームが始まっています。"}), 400

    target_id = request.get_json(force=True).get("user_id")
    member = CardRoomPlayer.query.filter_by(room_id=room_obj.id, user_id=target_id).first()
    if member and member.user_id != room_obj.owner_id:
        db.session.delete(member)
        db.session.commit()
    return jsonify({"ok": True})


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
        "players": [
            {"user_id": p.user_id, "username": p.user.username, "is_bot": p.user.is_bot}
            for p in players
        ],
        "owner_id": room_obj.owner_id,
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
    _process_bot_turns(room_obj, state)

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
    """自分の手札は見せて、他人の手札は枚数だけ見せる形に整形する。ボードゲームは盤面をそのまま見せる"""
    game_type = room_obj.game_type
    module = GAME_MODULES[game_type]
    public = {
        "game_type": game_type,
        "names": {str(k): v for k, v in names_by_id.items()}, "log": state.get("log", [])[-15:],
        "turn_order": state.get("turn_order", []),
    }

    if game_type in CARD_GAMES:
        hands_public = {}
        for uid_str, hand in state.get("hands", {}).items():
            if int(uid_str) == viewer_id:
                hands_public[uid_str] = hand
            else:
                hands_public[uid_str] = ["?"] * len(hand)
        public["hands"] = hands_public

        if game_type == "daifugo":
            public.update({
                "pile": state.get("pile", []), "finished_order": state.get("finished_order", []),
                "current_turn": module.current_turn_player(state), "revolution": state.get("revolution", False),
            })
        elif game_type == "babanuki":
            public.update({
                "out": state.get("out", []), "loser": state.get("loser"),
                "current_turn": module.current_turn_player(state),
            })
        elif game_type == "speed":
            public.update({
                "center": state.get("center", []), "winner": state.get("winner"), "is_draw": state.get("is_draw", False),
                "stock_counts": {k: len(v) for k, v in state.get("stocks", {}).items()},
            })
        elif game_type == "uno":
            public.update({
                "discard_top": state["discard"][-1] if state.get("discard") else None,
                "current_color": state.get("current_color"), "winner": state.get("winner"),
                "current_turn": module.current_turn_player(state),
                "hand_counts": {k: len(v) for k, v in state.get("hands", {}).items()},
            })
        elif game_type == "sevens":
            public.update({
                "table": state.get("table", {}), "winner": state.get("winner"),
                "current_turn": module.current_turn_player(state),
            })
        elif game_type == "concentration":
            # 神経衰弱は手札の概念が無いため、hands情報は不要
            public["hands"] = {}
            public.update({
                "revealed_cards": {str(p): state["board"][p] for p in state.get("revealed", [])},
                "revealed_positions": state.get("revealed", []),
                "matched": state.get("matched", []),
                "scores": state.get("scores", {}), "winner": state.get("winner"),
                "is_draw": state.get("is_draw", False), "last_pair_result": state.get("last_pair_result"),
                "current_turn": module.current_turn_player(state),
            })
    else:
        # ボードゲーム(盤面はどちらのプレイヤーからも同じように見える)
        public.update({
            "board": state.get("board"), "winner": state.get("winner"), "is_draw": state.get("is_draw", False),
            "current_turn": module.current_turn_player(state),
        })
        if game_type == "morris":
            public.update({
                "phase": state.get("phase"), "must_remove": state.get("must_remove"),
                "placed_count": state.get("placed_count"),
            })
        elif game_type == "shogi":
            public["hands"] = state.get("hands", {})
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
    elif room_obj.game_type == "uno":
        if action_type == "play":
            err = module.apply_play(state, current_user.id, data.get("card_index"), data.get("color"))
        elif action_type == "draw":
            err = module.apply_draw(state, current_user.id)
        else:
            err = "不正な操作です。"
    elif room_obj.game_type in ("gomoku", "othello", "tictactoe"):
        if action_type == "place":
            err = module.apply_place(state, current_user.id, data.get("row"), data.get("col"))
        elif action_type == "pass" and room_obj.game_type == "othello":
            err = module.apply_pass(state, current_user.id)
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "connect4":
        if action_type == "place":
            err = module.apply_place(state, current_user.id, data.get("col"))
        else:
            err = "不正な操作です。"
    elif room_obj.game_type in ("checkers", "chess"):
        if action_type == "move":
            err = module.apply_move(
                state, current_user.id, data.get("from_r"), data.get("from_c"), data.get("to_r"), data.get("to_c")
            )
        elif action_type == "resign" and room_obj.game_type == "chess":
            opp = next((p for p in state.get("turn_order", []) if p != current_user.id), None)
            state["winner"] = opp
            state.setdefault("log", []).append("{name}が投了した。")
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "morris":
        if action_type == "place":
            err = module.apply_place(state, current_user.id, data.get("point"))
        elif action_type == "move":
            err = module.apply_move(state, current_user.id, data.get("from_point"), data.get("to_point"))
        elif action_type == "remove":
            err = module.apply_remove(state, current_user.id, data.get("point"))
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "shogi":
        if action_type == "move":
            err = module.apply_move(
                state, current_user.id, data.get("from_r"), data.get("from_c"),
                data.get("to_r"), data.get("to_c"), bool(data.get("promote"))
            )
        elif action_type == "drop":
            err = module.apply_drop(state, current_user.id, data.get("piece_type"), data.get("row"), data.get("col"))
        elif action_type == "resign":
            opp = next((p for p in state.get("turn_order", []) if p != current_user.id), None)
            state["winner"] = opp
            state.setdefault("log", []).append("{name}が投了した。")
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "sevens":
        if action_type == "play":
            err = module.apply_play(state, current_user.id, data.get("card"))
        elif action_type == "pass":
            err = module.apply_pass(state, current_user.id)
        else:
            err = "不正な操作です。"
    elif room_obj.game_type == "concentration":
        if action_type == "flip":
            err = module.apply_flip(state, current_user.id, data.get("position"))
        else:
            err = "不正な操作です。"

    if err:
        return jsonify({"error": err}), 400

    players = _room_players(room_obj.id)
    names_by_id = {p.user_id: p.user.username for p in players}

    # 今回の人間の操作によって追加されたログを置換する
    _resolve_new_log_lines(state, current_user.id, max(0, len(state.get("log", [])) - 1), names_by_id)

    # ボットの手番を自動で処理する(それぞれの行動ログもそのボットの名前で置換される)
    _process_bot_turns(room_obj, state, names_by_id)

    state_row.state_json = json.dumps(state)

    finished = False
    if room_obj.game_type == "daifugo" and len(state.get("finished_order", [])) >= len(state.get("turn_order", [])) - 1:
        finished = True
    elif room_obj.game_type == "babanuki" and state.get("loser") is not None:
        finished = True
    elif room_obj.game_type == "sevens" and state.get("winner") is not None:
        finished = True
    elif room_obj.game_type in (
        "speed", "uno", "checkers", "morris", "shogi", "gomoku", "othello",
        "tictactoe", "connect4", "chess", "concentration",
    ) and (state.get("winner") is not None or state.get("is_draw")):
        finished = True

    if finished:
        room_obj.status = "finished"

    db.session.commit()
    return jsonify({"ok": True})


@cardroom_bp.route("/cards/room/<code>/chat")
@login_required
def chat_poll(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        return jsonify({"error": "部屋が見つかりません。"}), 404
    messages = (
        RoomChatMessage.query.filter_by(room_id=room_obj.id)
        .order_by(RoomChatMessage.created_at.desc()).limit(50).all()
    )
    messages.reverse()
    return jsonify({
        "messages": [
            {"username": m.user.username, "message": m.message, "is_me": m.user_id == current_user.id}
            for m in messages
        ]
    })


@cardroom_bp.route("/cards/room/<code>/chat/send", methods=["POST"])
@login_required
def chat_send(code):
    room_obj = CardRoom.query.filter_by(code=code.upper()).first()
    if not room_obj:
        return jsonify({"error": "部屋が見つかりません。"}), 404
    member = CardRoomPlayer.query.filter_by(room_id=room_obj.id, user_id=current_user.id).first()
    if not member:
        return jsonify({"error": "この部屋の参加者ではありません。"}), 403

    data = request.get_json(force=True)
    text = (data.get("message") or "").strip()[:300]
    if not text:
        return jsonify({"error": "メッセージを入力してください。"}), 400

    db.session.add(RoomChatMessage(room_id=room_obj.id, user_id=current_user.id, message=text))
    db.session.commit()
    return jsonify({"ok": True})


@cardroom_bp.route("/cards/how-to-play/<game_type>")
@login_required
def how_to_play(game_type):
    text = HOW_TO_PLAY.get(game_type, "説明が見つかりませんでした。")
    return jsonify({"game_type": game_type, "label": GAME_LABELS.get(game_type, game_type), "text": text})
