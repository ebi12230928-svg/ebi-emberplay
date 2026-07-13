"""
チェス(簡易版)。8x8盤面、標準的な駒の動きに対応。
【重要な簡略化】将棋と同様、詰み(チェックメイト)の自動判定・キャスリング・アンパッサンは実装していません。
「相手のキングを取ったら勝ち」というシンプルなルールです。ポーンは最終段に到達すると自動でクイーンに昇格します。
"""


def _initial_board():
    board = [[None] * 8 for _ in range(8)]
    back_row = ["r", "n", "b", "q", "k", "b", "n", "r"]
    for c in range(8):
        board[0][c] = {"type": back_row[c], "owner": 1}
        board[1][c] = {"type": "p", "owner": 1}
        board[6][c] = {"type": "p", "owner": 0}
        board[7][c] = {"type": back_row[c], "owner": 0}
    return board


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("チェスは2人でのみプレイできます")
    return {
        "board": _initial_board(), "turn_order": list(player_ids), "turn_index": 0, "winner": None,
        "rules": rules, "log": ["ゲーム開始!(簡易ルール: 相手のキングを取ったら勝ち)"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _in_bounds(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def legal_moves_for(state, r, c):
    board = state["board"]
    piece = board[r][c]
    if not piece:
        return []
    ptype, owner = piece["type"], piece["owner"]
    forward = -1 if owner == 0 else 1
    moves = []

    if ptype == "p":
        one = r + forward
        if _in_bounds(one, c) and board[one][c] is None:
            moves.append((one, c))
            start_row = 6 if owner == 0 else 1
            two = r + forward * 2
            if r == start_row and board[two][c] is None:
                moves.append((two, c))
        for dc in (-1, 1):
            nr, nc = r + forward, c + dc
            if _in_bounds(nr, nc) and board[nr][nc] and board[nr][nc]["owner"] != owner:
                moves.append((nr, nc))
    elif ptype == "n":
        for dr, dc in [(-2, -1), (-2, 1), (2, -1), (2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2)]:
            nr, nc = r + dr, c + dc
            if _in_bounds(nr, nc) and (board[nr][nc] is None or board[nr][nc]["owner"] != owner):
                moves.append((nr, nc))
    elif ptype == "k":
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if _in_bounds(nr, nc) and (board[nr][nc] is None or board[nr][nc]["owner"] != owner):
                    moves.append((nr, nc))
    else:
        dirs = []
        if ptype in ("r", "q"):
            dirs += [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if ptype in ("b", "q"):
            dirs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            while _in_bounds(nr, nc):
                if board[nr][nc] is None:
                    moves.append((nr, nc))
                else:
                    if board[nr][nc]["owner"] != owner:
                        moves.append((nr, nc))
                    break
                nr += dr
                nc += dc
    return moves


def apply_move(state, user_id, from_r, from_c, to_r, to_c):
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
        state["log"].append("{name}が相手の駒を取った!")
        if captured["type"] == "k":
            state["winner"] = user_id
            state["log"].append("{name}がキングを取って勝利!")

    board[to_r][to_c] = piece
    board[from_r][from_c] = None

    if piece["type"] == "p" and (to_r == 0 or to_r == 7):
        piece["type"] = "q"
        state["log"].append("ポーンがクイーンに昇格した!")

    state["log"].append("{name}が駒を動かした。")
    if state["winner"] is None:
        state["turn_index"] += 1
    return None
