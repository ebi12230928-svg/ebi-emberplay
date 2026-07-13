"""
将棋(簡易版)。9x9盤面。駒の動き・成り・持ち駒(打つ)まで対応。
※実装の簡略化のため、王手放置の禁止・詰みの厳密判定・二歩や打ち歩詰めなど一部の細かい反則は判定していません。
  「相手の王を取ったら勝ち」という分かりやすいルールで決着します。
"""

PIECE_MOVES = {
    "p": [(-1, 0)], "s": [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 1)],
    "g": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)],
    "k": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)],
    "+p": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)],
    "+l": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)],
    "+n": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)],
    "+s": [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0)],
}
PROMOTE = {"p": "+p", "l": "+l", "n": "+n", "s": "+s", "b": "+b", "r": "+r"}
DEMOTE = {v: k for k, v in PROMOTE.items()}
CAN_DROP_NO_PROMOTE_ROW = {"p": (0,), "l": (0,), "n": (0, 1)}  # player0視点(上向き)。player1は反転して判定

INITIAL_ROW0 = ["l", "n", "s", "g", "k", "g", "s", "n", "l"]  # player1(上側)
INITIAL_ROW1 = [None, "b", None, None, None, None, None, "r", None]
INITIAL_ROW7 = [None, "r", None, None, None, None, None, "b", None]
INITIAL_ROW8 = ["l", "n", "s", "g", "k", "g", "s", "n", "l"]  # player0(下側)


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("将棋は2人でのみプレイできます")
    board = [[None] * 9 for _ in range(9)]
    for c in range(9):
        board[0][c] = {"type": INITIAL_ROW0[c], "owner": 1} if INITIAL_ROW0[c] else None
        board[1][c] = {"type": INITIAL_ROW1[c], "owner": 1} if INITIAL_ROW1[c] else None
        board[2][c] = {"type": "p", "owner": 1}
        board[6][c] = {"type": "p", "owner": 0}
        board[7][c] = {"type": INITIAL_ROW7[c], "owner": 0} if INITIAL_ROW7[c] else None
        board[8][c] = {"type": INITIAL_ROW8[c], "owner": 0} if INITIAL_ROW8[c] else None
    return {
        "board": board, "turn_order": list(player_ids), "turn_index": 0, "winner": None,
        "hands": {"0": [], "1": []},
        "rules": rules, "log": ["ゲーム開始!(簡易ルール: 相手の王を取ったら勝ち)"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _in_bounds(r, c):
    return 0 <= r < 9 and 0 <= c < 9


def _sliding(piece_type):
    return piece_type in ("l", "b", "r", "+b", "+r")


def _piece_directions(piece_type, owner):
    if piece_type == "l":
        dirs = [(-1, 0)]
    elif piece_type == "n":
        dirs = [(-2, -1), (-2, 1)]
    elif piece_type in ("b", "+b"):
        dirs = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    elif piece_type in ("r", "+r"):
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    else:
        dirs = PIECE_MOVES.get(piece_type, [])
    if owner == 1:
        dirs = [(-dr, dc) for dr, dc in dirs]
    return dirs


def legal_moves_for(state, r, c):
    board = state["board"]
    piece = board[r][c]
    if not piece:
        return []
    moves = []
    dirs = _piece_directions(piece["type"], piece["owner"])
    is_slider = _sliding(piece["type"])
    for dr, dc in dirs:
        nr, nc = r + dr, c + dc
        while _in_bounds(nr, nc):
            target = board[nr][nc]
            if target is None:
                moves.append((nr, nc))
            else:
                if target["owner"] != piece["owner"]:
                    moves.append((nr, nc))
                break
            if not is_slider:
                break
            nr += dr
            nc += dc
    if piece["type"] in ("+b", "+r"):
        extra = [(-1, 0), (1, 0), (0, -1), (0, 1)] if piece["type"] == "+b" else [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dr, dc in extra:
            nr, nc = r + dr, c + dc
            if _in_bounds(nr, nc) and (board[nr][nc] is None or board[nr][nc]["owner"] != piece["owner"]):
                moves.append((nr, nc))
    return moves


def _promotion_zone(row, owner):
    return row <= 2 if owner == 0 else row >= 6


def apply_move(state, user_id, from_r, from_c, to_r, to_c, promote=False):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    board = state["board"]
    owner = state["turn_order"].index(user_id)
    piece = board[from_r][from_c] if _in_bounds(from_r, from_c) else None
    if not piece or piece["owner"] != owner:
        return "自分の駒を選んでください。"
    if (to_r, to_c) not in legal_moves_for(state, from_r, from_c):
        return "そこには移動できません。"

    captured = board[to_r][to_c]
    if captured:
        base_type = DEMOTE.get(captured["type"], captured["type"])
        state["hands"][str(owner)].append(base_type)
        state["log"].append("{name}が相手の駒を取った!")
        if captured["type"] == "k":
            state["winner"] = user_id
            state["log"].append("{name}が王を取って勝利!")

    can_promote = piece["type"] in PROMOTE and (_promotion_zone(from_r, owner) or _promotion_zone(to_r, owner))
    board[to_r][to_c] = piece
    board[from_r][from_c] = None
    if can_promote and promote:
        piece["type"] = PROMOTE[piece["type"]]
        state["log"].append("{name}の駒が成った!")

    state["log"].append(f"{{name}}が({from_r},{from_c})から({to_r},{to_c})へ移動した。")
    if state["winner"] is None:
        state["turn_index"] += 1
    return None


def apply_drop(state, user_id, piece_type, r, c):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    owner = state["turn_order"].index(user_id)
    hand = state["hands"][str(owner)]
    if piece_type not in hand:
        return "その持ち駒はありません。"
    if state["board"][r][c] is not None:
        return "そこにはすでに駒があります。"

    limit_rows = CAN_DROP_NO_PROMOTE_ROW.get(piece_type)
    if limit_rows:
        forbidden_row = limit_rows if owner == 0 else tuple(8 - x for x in limit_rows)
        if r in forbidden_row:
            return "その駒はその段には打てません(動けなくなってしまいます)。"

    hand.remove(piece_type)
    state["board"][r][c] = {"type": piece_type, "owner": owner}
    state["log"].append(f"{{name}}が持ち駒を({r},{c})に打った。")
    state["turn_index"] += 1
    return None
