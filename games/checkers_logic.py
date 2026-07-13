"""チェッカー。8x8の盤面(暗いマスのみ使用)、斜め移動、ジャンプで相手駒を取る。キング(成り)あり。"""

SIZE = 8


def _dark_square(r, c):
    return (r + c) % 2 == 1


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("チェッカーは2人でのみプレイできます")
    board = [[None] * SIZE for _ in range(SIZE)]
    for r in range(3):
        for c in range(SIZE):
            if _dark_square(r, c):
                board[r][c] = {"owner": 0, "king": False}
    for r in range(5, 8):
        for c in range(SIZE):
            if _dark_square(r, c):
                board[r][c] = {"owner": 1, "king": False}
    return {
        "board": board, "turn_order": list(player_ids), "turn_index": 0, "winner": None,
        "rules": rules, "log": ["ゲーム開始!斜めに移動し、相手の駒を飛び越えて取ろう。"],
    }


def current_turn_player(state):
    return state["turn_order"][state["turn_index"] % 2]


def _piece_moves(board, r, c):
    piece = board[r][c]
    if not piece:
        return [], []
    owner = piece["owner"]
    dirs = [(-1, -1), (-1, 1), (1, -1), (1, 1)] if piece["king"] else (
        [(1, -1), (1, 1)] if owner == 0 else [(-1, -1), (-1, 1)]
    )
    simple, jumps = [], []
    for dr, dc in dirs:
        nr, nc = r + dr, c + dc
        if 0 <= nr < SIZE and 0 <= nc < SIZE and board[nr][nc] is None:
            simple.append((nr, nc))
        jr, jc = r + dr * 2, c + dc * 2
        if 0 <= jr < SIZE and 0 <= jc < SIZE and board[nr][nc] and board[nr][nc]["owner"] != owner and board[jr][jc] is None:
            jumps.append((jr, jc))
    return simple, jumps


def _has_any_jump(board, owner):
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] and board[r][c]["owner"] == owner:
                if _piece_moves(board, r, c)[1]:
                    return True
    return False


def apply_move(state, user_id, from_r, from_c, to_r, to_c):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    board = state["board"]
    piece = board[from_r][from_c] if 0 <= from_r < SIZE and 0 <= from_c < SIZE else None
    owner = state["turn_order"].index(user_id)
    if not piece or piece["owner"] != owner:
        return "自分の駒を選んでください。"

    simple, jumps = _piece_moves(board, from_r, from_c)
    must_jump = _has_any_jump(board, owner)
    if must_jump and (to_r, to_c) not in jumps:
        return "取れる駒がある場合は、そちらを優先しなければなりません。"
    if not must_jump and (to_r, to_c) not in simple:
        return "そこには移動できません。"

    board[to_r][to_c] = piece
    board[from_r][from_c] = None
    if abs(to_r - from_r) == 2:
        mid_r, mid_c = (from_r + to_r) // 2, (from_c + to_c) // 2
        board[mid_r][mid_c] = None
        state["log"].append("{name}が相手の駒を取った!")

    if (owner == 0 and to_r == SIZE - 1) or (owner == 1 and to_r == 0):
        piece["king"] = True
        state["log"].append("{name}の駒がキングに成った!")

    state["turn_index"] += 1

    remaining = sum(1 for row in board for cell in row if cell and cell["owner"] != owner)
    if remaining == 0:
        state["winner"] = user_id
        state["log"].append("{name}が相手の駒を全て取って勝利!")
    return None
