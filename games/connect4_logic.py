"""コネクトフォー。7列6行の盤に交互にコマを落とし、縦横斜めのいずれかに4つ並べたら勝ち。"""

ROWS, COLS = 6, 7


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("コネクトフォーは2人でのみプレイできます")
    return {
        "board": [[None] * COLS for _ in range(ROWS)], "turn_order": list(player_ids), "turn_index": 0,
        "winner": None, "is_draw": False, "rules": rules,
        "log": ["ゲーム開始!列を選んでコマを落とそう。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _check_win(board, r, c, owner):
    for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
        count = 1
        for sign in (1, -1):
            rr, cc = r + dr * sign, c + dc * sign
            while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == owner:
                count += 1
                rr += dr * sign
                cc += dc * sign
        if count >= 4:
            return True
    return False


def apply_place(state, user_id, col):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not (0 <= col < COLS):
        return "その列は選べません。"

    board = state["board"]
    landing_row = None
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] is None:
            landing_row = r
            break
    if landing_row is None:
        return "その列はもう満杯です。"

    owner = state["turn_order"].index(user_id)
    board[landing_row][col] = owner
    state["log"].append("{name}がコマを落とした。")

    if _check_win(board, landing_row, col, owner):
        state["winner"] = user_id
        state["log"].append("{name}の勝利!4つ並びました。")
        return None

    if all(cell is not None for row_ in board for cell in row_):
        state["is_draw"] = True
        state["log"].append("引き分けです。")
        return None

    state["turn_index"] += 1
    return None
