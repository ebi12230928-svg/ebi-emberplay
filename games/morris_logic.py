"""
ナインメンズモリス(9人の男)。24の交点に駒を置き、3つ並べる(ミル)と相手の駒を1つ取れる。
配置フェーズ(各9個)→移動フェーズ(隣接点へ移動、駒が3個になったら好きな場所へ「フライ」可)。
"""

ADJACENCY = {
    0: [1, 9], 1: [0, 2, 4], 2: [1, 14],
    3: [4, 10], 4: [1, 3, 5, 7], 5: [4, 13],
    6: [7, 11], 7: [4, 6, 8], 8: [7, 12],
    9: [0, 10, 21], 10: [3, 9, 11, 18], 11: [6, 10, 15],
    12: [8, 13, 17], 13: [5, 12, 14, 20], 14: [2, 13, 23],
    15: [11, 16], 16: [15, 17, 19], 17: [12, 16],
    18: [10, 19], 19: [16, 18, 20, 22], 20: [13, 19],
    21: [9, 22], 22: [19, 21, 23], 23: [14, 22],
}

MILLS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11), (12, 13, 14), (15, 16, 17), (18, 19, 20), (21, 22, 23),
    (0, 9, 21), (3, 10, 18), (6, 11, 15), (1, 4, 7), (16, 19, 22), (8, 12, 17), (5, 13, 20), (2, 14, 23),
]

PIECES_PER_PLAYER = 9


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("ナインメンズモリスは2人でのみプレイできます")
    return {
        "board": [None] * 24, "turn_order": list(player_ids), "turn_index": 0,
        "phase": "placing", "placed_count": [0, 0], "captured_count": [0, 0],
        "must_remove": False, "winner": None,
        "rules": rules, "log": ["ゲーム開始!交点に駒を置いて3つ並べよう(ミル)。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _mills_through(point):
    return [m for m in MILLS if point in m]


def _forms_mill(board, point, owner):
    for mill in _mills_through(point):
        if all(board[p] == owner for p in mill):
            return True
    return False


def _owner_piece_count(board, owner):
    return sum(1 for p in board if p == owner)


def apply_place(state, user_id, point):
    if state["must_remove"]:
        return "先に相手の駒を1つ取ってください。"
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if state["phase"] != "placing":
        return "配置フェーズは終わっています。"
    if not (0 <= point < 24) or state["board"][point] is not None:
        return "そこには置けません。"

    owner = state["turn_order"].index(user_id)
    state["board"][point] = owner
    state["placed_count"][owner] += 1
    state["log"].append(f"{{name}}が{point}番に駒を置いた。")

    if _forms_mill(state["board"], point, owner):
        state["must_remove"] = True
        state["log"].append("ミル成立!相手の駒を1つ取れます。")
        return None

    if state["placed_count"][0] >= PIECES_PER_PLAYER and state["placed_count"][1] >= PIECES_PER_PLAYER:
        state["phase"] = "moving"
        state["log"].append("配置フェーズ終了。移動フェーズに入ります。")

    state["turn_index"] += 1
    return None


def apply_remove(state, user_id, point):
    if not state["must_remove"]:
        return "今は駒を取る場面ではありません。"
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    owner = state["turn_order"].index(user_id)
    opp = 1 - owner
    if state["board"][point] != opp:
        return "相手の駒を選んでください。"

    opp_mill_points = set()
    for mill in MILLS:
        if all(state["board"][p] == opp for p in mill):
            opp_mill_points.update(mill)
    all_opp_points = [i for i, v in enumerate(state["board"]) if v == opp]
    if point in opp_mill_points and not all(p in opp_mill_points for p in all_opp_points):
        return "相手の駒がミルを形成していない場所から取ってください。"

    state["board"][point] = None
    state["captured_count"][owner] += 1
    state["log"].append("{name}が相手の駒を取った!")
    state["must_remove"] = False

    if state["phase"] == "moving" and _owner_piece_count(state["board"], opp) < 3:
        state["winner"] = user_id
        state["log"].append("{name}の勝利!(相手の駒が3個未満になった)")
        return None

    state["turn_index"] += 1
    return None


def apply_move(state, user_id, from_point, to_point):
    if state["must_remove"]:
        return "先に相手の駒を1つ取ってください。"
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if state["phase"] != "moving":
        return "まだ配置フェーズです。"

    owner = state["turn_order"].index(user_id)
    if state["board"][from_point] != owner:
        return "自分の駒を選んでください。"
    if state["board"][to_point] is not None:
        return "移動先に駒があります。"

    flying = _owner_piece_count(state["board"], owner) == 3
    if not flying and to_point not in ADJACENCY[from_point]:
        return "隣接する交点にしか移動できません(駒が3個になるとどこへでも移動できます)。"

    state["board"][from_point] = None
    state["board"][to_point] = owner
    state["log"].append(f"{{name}}が{from_point}番から{to_point}番へ移動した。")

    if _forms_mill(state["board"], to_point, owner):
        state["must_remove"] = True
        state["log"].append("ミル成立!相手の駒を1つ取れます。")
        return None

    state["turn_index"] += 1
    return None
