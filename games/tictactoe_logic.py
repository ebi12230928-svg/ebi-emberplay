"""三目並べ。3x3の盤面に交互に印を置き、縦横斜めのいずれかに3つ並べたら勝ち。"""


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("三目並べは2人でのみプレイできます")
    return {
        "board": [[None] * 3 for _ in range(3)], "turn_order": list(player_ids), "turn_index": 0,
        "winner": None, "is_draw": False, "rules": rules,
        "log": ["ゲーム開始!交互にマスを選んで3つ並べよう。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _check_win(board, owner):
    lines = []
    lines.extend(board)
    lines.extend([[board[r][c] for r in range(3)] for c in range(3)])
    lines.append([board[i][i] for i in range(3)])
    lines.append([board[i][2 - i] for i in range(3)])
    return any(all(cell == owner for cell in line) for line in lines)


def apply_place(state, user_id, row, col):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not (0 <= row < 3 and 0 <= col < 3) or state["board"][row][col] is not None:
        return "そこには置けません。"

    owner = state["turn_order"].index(user_id)
    state["board"][row][col] = owner
    state["log"].append("{name}が置いた。")

    if _check_win(state["board"], owner):
        state["winner"] = user_id
        state["log"].append("{name}の勝利!3つ並びました。")
        return None

    if all(cell is not None for row_ in state["board"] for cell in row_):
        state["is_draw"] = True
        state["log"].append("引き分けです。")
        return None

    state["turn_index"] += 1
    return None
