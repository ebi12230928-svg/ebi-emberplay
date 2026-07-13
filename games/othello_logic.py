"""オセロ(リバーシ)。8x8の盤面で相手の石を挟んでひっくり返す。石が多い方が勝ち。"""

SIZE = 8
DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("オセロは2人でのみプレイできます")
    board = [[None] * SIZE for _ in range(SIZE)]
    board[3][3], board[4][4] = 1, 1
    board[3][4], board[4][3] = 0, 0
    return {
        "board": board, "turn_order": list(player_ids), "turn_index": 0,
        "winner": None, "is_draw": False, "pass_count": 0,
        "rules": rules, "log": ["ゲーム開始!相手の石を挟んでひっくり返そう。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _flips_for(board, row, col, symbol):
    if board[row][col] is not None:
        return []
    opp = 1 - symbol
    all_flips = []
    for dr, dc in DIRS:
        r, c = row + dr, col + dc
        line = []
        while 0 <= r < SIZE and 0 <= c < SIZE and board[r][c] == opp:
            line.append((r, c))
            r += dr
            c += dc
        if line and 0 <= r < SIZE and 0 <= c < SIZE and board[r][c] == symbol:
            all_flips.extend(line)
    return all_flips


def legal_moves(state, user_id):
    symbol = state["turn_order"].index(user_id)
    board = state["board"]
    return [(r, c) for r in range(SIZE) for c in range(SIZE) if _flips_for(board, r, c, symbol)]


def apply_place(state, user_id, row, col):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    symbol = state["turn_order"].index(user_id)
    flips = _flips_for(state["board"], row, col, symbol)
    if not flips:
        return "そこには置けません(相手の石を挟める場所に置いてください)。"

    state["board"][row][col] = symbol
    for r, c in flips:
        state["board"][r][c] = symbol
    state["log"].append(f"{{name}}が({row},{col})に置いて{len(flips)}個ひっくり返した!")
    state["pass_count"] = 0

    _advance_or_end(state)
    return None


def apply_pass(state, user_id):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if legal_moves(state, user_id):
        return "置ける場所があるのでパスできません。"
    state["log"].append("{name}はパス(置ける場所がありません)。")
    state["pass_count"] += 1
    if state["pass_count"] >= 2:
        _finish_game(state)
        return None
    state["turn_index"] += 1
    return None


def _advance_or_end(state):
    state["turn_index"] += 1
    next_player = current_turn_player(state)
    if not legal_moves(state, next_player):
        other = state["turn_order"][(state["turn_index"] + 1) % 2]
        if not legal_moves(state, other):
            _finish_game(state)


def _finish_game(state):
    counts = [0, 0]
    for row in state["board"]:
        for cell in row:
            if cell is not None:
                counts[cell] += 1
    state["log"].append(f"ゲーム終了!{counts[0]} - {counts[1]}")
    if counts[0] == counts[1]:
        state["is_draw"] = True
    else:
        winner_symbol = 0 if counts[0] > counts[1] else 1
        state["winner"] = state["turn_order"][winner_symbol]
