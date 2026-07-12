"""
トランプ部屋(大富豪・ババ抜き・スピード)共通のカード表現。
カードは0〜51のインデックス(rank=idx%13+1 [1=A...11=J,12=Q,13=K], suit=idx//13)。
ジョーカーは52として扱う(ババ抜きのみで使用)。
"""
import random

SUIT_SYMBOLS = ["♠", "♥", "♦", "♣"]
RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_of(card):
    if card == 52:
        return 0  # ジョーカー
    return (card % 13) + 1


def suit_of(card):
    if card == 52:
        return -1
    return card // 13


def card_label(card):
    if card == 52:
        return "🃏JOKER"
    r = rank_of(card)
    label = RANK_LABELS.get(r, str(r))
    return f"{SUIT_SYMBOLS[suit_of(card)]}{label}"


def make_deck(with_joker=False):
    deck = list(range(52))
    if with_joker:
        deck.append(52)
    random.shuffle(deck)
    return deck


def deal_even(deck, player_ids):
    """デッキを人数分できるだけ均等に配る。余りは先頭のプレイヤーから1枚ずつ多く配る"""
    hands = {pid: [] for pid in player_ids}
    for i, card in enumerate(deck):
        pid = player_ids[i % len(player_ids)]
        hands[pid].append(card)
    for pid in hands:
        hands[pid].sort(key=lambda c: (rank_of(c) if rank_of(c) != 1 else 14, suit_of(c)))
    return hands
