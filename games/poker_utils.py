"""
5枚のカードからポーカー役を判定する共通ロジック。
カードは0〜51のインデックスで表す(rank = idx%13+1 [1=A,11=J,12=Q,13=K], suit = idx//13)。
videopoker.py・casinoholdem.py・letitride.py で共通利用する。
"""
from collections import Counter

RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}
SUIT_SYMBOLS = "♠♥♦♣"

# 役の強さ順(数字が大きいほど強い)。Casino Hold'em・Let It Rideの勝敗比較に使う
HAND_STRENGTH = [
    "nothing", "jacks_or_better", "two_pair", "three_kind", "straight",
    "flush", "full_house", "four_kind", "straight_flush", "royal_flush",
]

HAND_LABELS = {
    "royal_flush": "Royal Flush", "straight_flush": "Straight Flush", "four_kind": "Four of a Kind",
    "full_house": "Full House", "flush": "Flush", "straight": "Straight", "three_kind": "Three of a Kind",
    "two_pair": "Two Pair", "jacks_or_better": "Jacks or Better", "nothing": "No Win",
}


def rank_of(card_index):
    return (card_index % 13) + 1


def suit_of(card_index):
    return card_index // 13


def card_label(card_index):
    rank = rank_of(card_index)
    suit = SUIT_SYMBOLS[suit_of(card_index)]
    return f"{RANK_NAMES.get(rank, str(rank))}{suit}"


def evaluate_5card(cards):
    """5枚のカード(インデックスのリスト)から役を判定する(video pokerと同じロジック)"""
    ranks = sorted(rank_of(c) for c in cards)
    suits = [suit_of(c) for c in cards]
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks))
    is_straight = False
    if len(unique_ranks) == 5:
        if unique_ranks[-1] - unique_ranks[0] == 4:
            is_straight = True
        elif unique_ranks == [1, 10, 11, 12, 13]:  # A-10-J-Q-K(ブロードウェイ)
            is_straight = True

    counts = sorted(Counter(ranks).values(), reverse=True)

    if is_straight and is_flush:
        if set(ranks) == {1, 10, 11, 12, 13}:
            return "royal_flush"
        return "straight_flush"
    if counts[0] == 4:
        return "four_kind"
    if counts[0] == 3 and counts[1] == 2:
        return "full_house"
    if is_flush:
        return "flush"
    if is_straight:
        return "straight"
    if counts[0] == 3:
        return "three_kind"
    if counts[0] == 2 and counts[1] == 2:
        return "two_pair"
    if counts[0] == 2:
        pair_rank = next(r for r in set(ranks) if ranks.count(r) == 2)
        if pair_rank in (1, 11, 12, 13):
            return "jacks_or_better"
    return "nothing"


def best_hand_from(cards):
    """6枚または7枚から最も強い5枚の組み合わせを選ぶ(Casino Hold'emなどで使用)"""
    from itertools import combinations
    best = None
    best_strength = -1
    for combo in combinations(cards, 5):
        hand = evaluate_5card(combo)
        strength = HAND_STRENGTH.index(hand)
        if strength > best_strength:
            best_strength = strength
            best = hand
    return best, best_strength
