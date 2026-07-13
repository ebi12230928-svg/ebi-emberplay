"""五目並べ(ゴモク)。15x15の盤面に交互に石を置き、縦横斜めいずれかに5つ並べたら勝ち。"""

SIZE = 15


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("五目並べは2人でのみプレイできます")
    return {
        "board": [[None] * SIZE for _ in range(SIZE)],
        "turn_order": list(player_ids), "turn_index": 0, "winner": None, "is_draw": False,
        "rules": rules, "log": ["ゲーム開始!交互に石を置いて5つ並べよう。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _check_win(board, row, col, symbol):
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        for sign in (1, -1):
            r, c = row + dr * sign, col + dc * sign
            while 0 <= r < SIZE and 0 <= c < SIZE and board[r][c] == symbol:
                count += 1
                r += dr * sign
                c += dc * sign
        if count >= 5:
            return True
    return False


def apply_place(state, user_id, row, col):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not (0 <= row < SIZE and 0 <= col < SIZE):
        return "盤面の外です。"
    if state["board"][row][col] is not None:
        return "そこにはすでに石があります。"

    symbol = state["turn_order"].index(user_id)
    state["board"][row][col] = symbol
    state["log"].append(f"{{name}}が({row},{col})に石を置いた。")

    if _check_win(state["board"], row, col, symbol):
        state["winner"] = user_id
        state["log"].append("{name}が5つ並べて勝利!")
        return None

    if all(state["board"][r][c] is not None for r in range(SIZE) for c in range(SIZE)):
        state["is_draw"] = True
        state["log"].append("盤面が埋まって引き分け。")
        return None

    state["turn_index"] += 1
    return None
