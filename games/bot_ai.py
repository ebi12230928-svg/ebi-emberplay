"""
トランプ・ボードゲーム共通のボット(CPU)思考ロジック。
どのゲームでも「合法手を試して、通ったら採用」という総当たり方式で安全に動作するようにしている。
"""
import random


def bot_move(game_type, module, state, bot_id, difficulty="normal"):
    """ボットの手番に、そのゲームに応じた1手を打つ。成功したらTrue"""
    try:
        if game_type == "daifugo":
            return _bot_daifugo(module, state, bot_id, difficulty)
        if game_type == "babanuki":
            return module.apply_draw(state, bot_id) is None
        if game_type == "speed":
            return _bot_speed(module, state, bot_id, difficulty)
        if game_type == "uno":
            return _bot_uno(module, state, bot_id, difficulty)
        if game_type in ("gomoku", "othello"):
            return _bot_grid(module, state, bot_id, game_type, difficulty)
        if game_type == "checkers":
            return _bot_checkers(module, state, bot_id, difficulty)
        if game_type == "morris":
            return _bot_morris(module, state, bot_id, difficulty)
        if game_type == "shogi":
            return _bot_shogi(module, state, bot_id, difficulty)
    except Exception:
        return False
    return False


def _bot_daifugo(module, state, bot_id, difficulty):
    hand = state["hands"].get(str(bot_id), [])
    if not hand:
        return False
    from games import cards_common as cc
    by_rank = {}
    for c in hand:
        by_rank.setdefault(cc.rank_of(c), []).append(c)
    groups = sorted(by_rank.values(), key=lambda g: cc.rank_of(g[0]))
    for group in groups:
        for count in range(len(group), 0, -1):
            cards = group[:count]
            if module.legal_play(state, bot_id, cards) is None:
                module.apply_play(state, bot_id, cards)
                return True
    if state["pile"]:
        return module.apply_pass(state, bot_id) is None
    return False


def _bot_speed(module, state, bot_id, difficulty):
    moves = module.legal_moves(state, bot_id)
    if not moves:
        return False
    card, pile_idx = random.choice(moves)
    return module.apply_play(state, bot_id, card, pile_idx) is None


def _bot_uno(module, state, bot_id, difficulty):
    hand = state["hands"].get(str(bot_id), [])
    top = state["discard"][-1] if state.get("discard") else None
    order = list(range(len(hand)))
    random.shuffle(order)
    for i in order:
        card = hand[i]
        if module._card_playable(card, top, state["current_color"]):
            color = random.choice(module.COLORS) if card["color"] == "wild" else None
            if module.apply_play(state, bot_id, i, color) is None:
                return True
    return module.apply_draw(state, bot_id) is None


def _bot_grid(module, state, bot_id, game_type, difficulty):
    board = state["board"]
    if game_type == "othello":
        moves = module.legal_moves(state, bot_id)
        if not moves:
            return module.apply_pass(state, bot_id) is None
        r, c = random.choice(moves)
        return module.apply_place(state, bot_id, r, c) is None
    else:
        empties = [(r, c) for r in range(len(board)) for c in range(len(board[0])) if board[r][c] is None]
        if not empties:
            return False
        r, c = random.choice(empties)
        return module.apply_place(state, bot_id, r, c) is None


def _bot_checkers(module, state, bot_id, difficulty):
    owner = state["turn_order"].index(bot_id)
    board = state["board"]
    pieces = [(r, c) for r in range(8) for c in range(8) if board[r][c] and board[r][c]["owner"] == owner]
    random.shuffle(pieces)
    jump_moves, simple_moves = [], []
    for (r, c) in pieces:
        simple, jumps = module._piece_moves(board, r, c)
        for (tr, tc) in jumps:
            jump_moves.append((r, c, tr, tc))
        for (tr, tc) in simple:
            simple_moves.append((r, c, tr, tc))
    candidates = jump_moves if jump_moves else simple_moves
    if not candidates:
        return False
    random.shuffle(candidates)
    for (r, c, tr, tc) in candidates:
        if module.apply_move(state, bot_id, r, c, tr, tc) is None:
            return True
    return False


def _bot_morris(module, state, bot_id, difficulty):
    if state.get("must_remove"):
        owner = state["turn_order"].index(bot_id)
        opp = 1 - owner
        candidates = [i for i, v in enumerate(state["board"]) if v == opp]
        random.shuffle(candidates)
        for pt in candidates:
            if module.apply_remove(state, bot_id, pt) is None:
                return True
        return False

    if state["phase"] == "placing":
        empties = [i for i, v in enumerate(state["board"]) if v is None]
        random.shuffle(empties)
        for pt in empties:
            if module.apply_place(state, bot_id, pt) is None:
                return True
        return False

    owner = state["turn_order"].index(bot_id)
    mine = [i for i, v in enumerate(state["board"]) if v == owner]
    random.shuffle(mine)
    for fp in mine:
        empties = [i for i, v in enumerate(state["board"]) if v is None]
        random.shuffle(empties)
        for tp in empties:
            if module.apply_move(state, bot_id, fp, tp) is None:
                return True
    return False


def _bot_shogi(module, state, bot_id, difficulty):
    owner = state["turn_order"].index(bot_id)
    board = state["board"]
    pieces = [(r, c) for r in range(9) for c in range(9) if board[r][c] and board[r][c]["owner"] == owner]
    random.shuffle(pieces)
    for (r, c) in pieces:
        moves = module.legal_moves_for(state, r, c)
        if not moves:
            continue
        random.shuffle(moves)
        for (tr, tc) in moves:
            promote = random.random() < 0.6
            if module.apply_move(state, bot_id, r, c, tr, tc, promote) is None:
                return True
    hand = state["hands"].get(str(owner), [])
    if hand:
        piece_type = random.choice(hand)
        empties = [(r, c) for r in range(9) for c in range(9) if board[r][c] is None]
        random.shuffle(empties)
        for (r, c) in empties:
            if module.apply_drop(state, bot_id, piece_type, r, c) is None:
                return True
    return False
