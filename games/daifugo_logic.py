"""
大富豪(だいふごう)のゲームロジック。純粋な状態遷移関数のみを扱う(DB・Flaskに依存しない)。
ルール: 場に出ているカードと同じ枚数・同ランクを出す。前の場より強いランクでないと出せない。
カードの強さ: 3が最弱、2が最強(Jokerを除く)、Jokerはあらゆるカードより強い。革命時は逆転する。
オプションルール: 8切り(8を出すと場が流れる)、革命(4枚同時出しで強さが逆転)、
ジョーカー(あらゆるカードより強く、複数枚出しでは好きなランクの代わりとして使える)、
10捨て(10を出した枚数分、手札から好きなカードを捨てられる)。
"""
from . import cards_common as cc


def _strength(rank):
    if rank == 0:
        return 16  # ジョーカー(最強)
    if rank == 1:
        return 14  # A
    if rank == 2:
        return 15  # 2(ジョーカーの次に強い)
    return rank


def new_game(player_ids, rules):
    deck = cc.make_deck(with_joker=bool(rules.get("joker", True)))
    hands = cc.deal_even(deck, player_ids)
    return {
        "hands": {str(pid): hands[pid] for pid in player_ids},
        "turn_order": list(player_ids),
        "turn_index": 0,
        "pile": [],
        "pile_owner": None,
        "passed": [],
        "finished_order": [],
        "revolution": False,
        "rules": rules,
        "phase": "playing",
        "exchange_pending": [],
        "discard_pending": None,  # 10捨て: {"user_id":..., "count":...}
        "log": ["ゲーム開始!カードが配られました。"],
    }


def _active_players(state):
    finished = set(state["finished_order"])
    return [p for p in state["turn_order"] if p not in finished]


def current_turn_player(state):
    active = _active_players(state)
    if not active:
        return None
    idx = state["turn_index"] % len(active)
    return active[idx]


def _effective_strength(state, rank):
    s = _strength(rank)
    if state.get("revolution"):
        return 100 - s
    return s


def _effective_rank_of_set(cards):
    """
    出されたカードの集合から、実質的なランクを求める。
    ジョーカーは「他のカードと同じランクの代わり」として扱えるため、
    ジョーカー以外のカードが1種類のランクにそろっていればOKとする。
    全てジョーカーの場合はジョーカー(0)として扱う。
    """
    non_joker_ranks = set(cc.rank_of(c) for c in cards if c != 52)
    if len(non_joker_ranks) > 1:
        return None  # ジョーカー以外に複数のランクが混ざっている場合は不正
    if not non_joker_ranks:
        return 0  # 全てジョーカー
    return non_joker_ranks.pop()


def legal_play(state, user_id, cards):
    if state.get("phase") == "exchange":
        return "カード交換が終わるまでお待ちください。"
    if state.get("phase") == "discard":
        return "捨てるカードを選んでいる最中です。"
    hand = state["hands"].get(str(user_id), [])
    if not cards or any(c not in hand for c in cards):
        return "手札にないカードが含まれています。"

    rank = _effective_rank_of_set(cards)
    if rank is None:
        return "同じランクのカード(+ジョーカー)しか同時に出せません。"

    if state["pile"]:
        if len(cards) != len(state["pile"]):
            return f"場と同じ枚数({len(state['pile'])}枚)を出してください。"
        pile_rank = _effective_rank_of_set(state["pile"])
        if _effective_strength(state, rank) <= _effective_strength(state, pile_rank):
            return "場のカードより強いランクを出してください。"
    return None


def apply_play(state, user_id, cards):
    err = legal_play(state, user_id, cards)
    if err:
        return err

    hand = state["hands"][str(user_id)]
    for c in cards:
        hand.remove(c)
    state["pile"] = list(cards)
    state["pile_owner"] = user_id
    state["passed"] = []

    rank = _effective_rank_of_set(cards)
    labels = "・".join(cc.card_label(c) for c in cards)
    state["log"].append(f"{{name}}が {labels} を出した!")

    rules = state.get("rules", {})
    cleared = False
    if rules.get("eight_giri") and rank == 8:
        state["log"].append("8切り!場が流れます。")
        cleared = True
    if rules.get("revolution") and len(cards) == 4:
        state["revolution"] = not state["revolution"]
        state["log"].append("革命が発生!強さが逆転した!")

    if not hand:
        state["finished_order"].append(user_id)
        state["log"].append(f"{{name}}が上がった!(第{len(state['finished_order'])}位)")

    active = _active_players(state)
    if len(active) <= 1:
        if active:
            state["finished_order"].append(active[0])
        state["log"].append("ゲーム終了!")
        return None

    if cleared:
        state["pile"] = []
        state["pile_owner"] = None
        state["passed"] = []
        if user_id in state["finished_order"]:
            state["turn_index"] = 0
        else:
            state["turn_index"] = active.index(user_id) if user_id in active else 0
    else:
        if user_id in state["finished_order"]:
            state["turn_index"] = state["turn_index"] % max(1, len(active))
        else:
            state["turn_index"] = (active.index(user_id) + 1) % len(active)

    # 10捨て: 10を出した枚数分、手札から好きなカードを捨てられる(上がった場合は捨てる必要が無い)
    if rules.get("ten_sute") and rank == 10 and hand:
        count = min(len(cards), len(hand))
        state["phase"] = "discard"
        state["discard_pending"] = {"user_id": user_id, "count": count}
        state["log"].append(f"10捨て!{{name}}は手札を{count}枚まで捨てられます。")
    return None


def apply_pass(state, user_id):
    if state.get("phase") == "exchange":
        return "カード交換が終わるまでお待ちください。"
    if state.get("phase") == "discard":
        return "捨てるカードを選んでいる最中です。"
    active = _active_players(state)
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not state["pile"]:
        return "場が空の時はパスできません(何か出してください)。"

    state["passed"].append(user_id)
    state["log"].append("{name}がパスした。")

    remaining = [p for p in active if p not in state["passed"]]
    if len(remaining) <= 1:
        state["pile"] = []
        state["passed"] = []
        winner = state["pile_owner"]
        active2 = _active_players(state)
        if winner in active2:
            state["turn_index"] = active2.index(winner)
        else:
            state["turn_index"] = 0
        state["log"].append("全員パス。場が流れます。")
    else:
        state["turn_index"] = (state["turn_index"] + 1) % len(active)
    return None


def apply_discard(state, user_id, cards):
    """10捨てで選んだカードを実際に手札から捨てる(1枚も捨てずに0枚選んでスキップしてもよい)"""
    pending = state.get("discard_pending")
    if not pending or pending["user_id"] != user_id:
        return "今は捨てるカードを選べません。"
    if len(cards) > pending["count"]:
        return f"最大{pending['count']}枚までしか捨てられません。"

    hand = state["hands"].get(str(user_id), [])
    if any(c not in hand for c in cards):
        return "手札にないカードが含まれています。"

    for c in cards:
        hand.remove(c)
    if cards:
        labels = "・".join(cc.card_label(c) for c in cards)
        state["log"].append(f"{{name}}が {labels} を10捨てで捨てた。")

    state["discard_pending"] = None
    state["phase"] = "playing"

    if not hand:
        state["finished_order"].append(user_id)
        state["log"].append(f"{{name}}が上がった!(第{len(state['finished_order'])}位)")
        active = _active_players(state)
        if len(active) <= 1:
            if active:
                state["finished_order"].append(active[0])
            state["log"].append("ゲーム終了!")
    return None


RANK_LABELS = {
    "daifugo": "大富豪", "fugo": "富豪", "heimin": "平民", "hinmin": "貧民", "daihinmin": "大貧民",
}


def compute_ranks(finished_order, n_players):
    """
    直前のラウンドの上がり順(finished_order)から、大富豪/富豪/平民/貧民/大貧民のランクを決める。
    4人以上いる場合のみ「富豪」「貧民」が存在する(2〜3人なら大富豪・大貧民・平民のみ)。
    """
    ranks = {}
    n = len(finished_order)
    for i, uid in enumerate(finished_order):
        if i == 0:
            ranks[uid] = "daifugo"
        elif i == n - 1:
            ranks[uid] = "daihinmin"
        elif i == 1 and n_players >= 4:
            ranks[uid] = "fugo"
        elif i == n - 2 and n_players >= 4:
            ranks[uid] = "hinmin"
        else:
            ranks[uid] = "heimin"
    return ranks


def start_new_round_with_exchange(prev_state, player_ids, rules):
    """
    前回のラウンドの結果(finished_order)からランクを決め、大富豪戦の「カード交換」ルールを適用して
    新しいラウンドの手札を配り直す。
    - 大貧民は大富豪に、手札の中で最も強いカードを2枚、強制的に渡す
    - 貧民は富豪に、手札の中で最も強いカードを1枚、強制的に渡す
    - 受け取った側(大富豪・富豪)は、同じ枚数だけ好きなカードを選んで渡し返す必要がある(この選択待ちの状態を返す)
    """
    finished_order = prev_state.get("finished_order", [])
    ranks = compute_ranks(finished_order, len(player_ids))

    new_state = new_game(player_ids, rules)
    new_state["ranks"] = ranks
    new_state["prev_ranks"] = ranks  # UI表示用(称号バッジ)

    by_rank = {r: uid for uid, r in ranks.items()}
    exchanges = []  # (献上する側, 受け取る側=大富豪/富豪, 枚数)
    if "daifugo" in by_rank and "daihinmin" in by_rank:
        exchanges.append((by_rank["daihinmin"], by_rank["daifugo"], 2))
    if "fugo" in by_rank and "hinmin" in by_rank:
        exchanges.append((by_rank["hinmin"], by_rank["fugo"], 1))

    pending_returns = []
    for giver, receiver, count in exchanges:
        giver_hand = new_state["hands"][str(giver)]
        # 強制的に、手札の中で最も強いカードから順番に渡す
        giver_hand.sort(key=lambda c: _strength(cc.rank_of(c)), reverse=True)
        given = giver_hand[:count]
        for c in given:
            giver_hand.remove(c)
        new_state["hands"][str(receiver)].extend(given)
        given_labels = "・".join(cc.card_label(c) for c in given)
        new_state["log"].append(
            f"{RANK_LABELS[ranks[giver]]}が{RANK_LABELS[ranks[receiver]]}に {given_labels} を献上した(強制)。"
        )
        pending_returns.append({"from": receiver, "to": giver, "count": count})

    new_state["exchange_pending"] = pending_returns
    new_state["phase"] = "exchange" if pending_returns else "playing"
    if pending_returns:
        new_state["log"].append("大富豪・富豪は、お返しのカードを選んで渡してください。")
    return new_state


def apply_exchange_return(state, user_id, cards):
    """大富豪・富豪が、献上された枚数と同じ枚数だけ好きなカードを選んで、相手に返す"""
    pending = state.get("exchange_pending", [])
    entry = next((e for e in pending if e["from"] == user_id), None)
    if not entry:
        return "今は返すカードがありません。"
    if len(cards) != entry["count"]:
        return f"{entry['count']}枚選んで渡してください。"
    hand = state["hands"].get(str(user_id), [])
    if any(c not in hand for c in cards):
        return "手札にないカードが含まれています。"

    for c in cards:
        hand.remove(c)
    state["hands"].setdefault(str(entry["to"]), []).extend(cards)
    pending.remove(entry)
    labels = "・".join(cc.card_label(c) for c in cards)
    state["log"].append(f"{{name}}が {labels} を渡した。")

    if not pending:
        state["phase"] = "playing"
        state["log"].append("カード交換が完了!ゲームを再開します。")
    return None
