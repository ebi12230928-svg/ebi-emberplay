"""
実績バッジシステム。
定義は静的にこのファイルで持ち、解除状況だけをUserAchievementテーブルに保存する。
check_achievements(user) はいつ呼んでも安全(すでに解除済みのものは再判定しない)。
"""
from extensions import db
from models import BetRecord, UserAchievement

# 各実績: key -> (表示名, 説明, アイコン, 判定関数)
# 判定関数は stats dict を受け取り、条件を満たしていれば True を返す
ACHIEVEMENTS = {
    "first_bet": ("初プレイ", "はじめてゲームをプレイした", "🎮", lambda s: s["total_bets"] >= 1),
    "first_win": ("初勝利", "はじめて勝利した", "🎉", lambda s: s["win_count"] >= 1),
    "bets_100": ("常連さん", "累計100回プレイした", "🔁", lambda s: s["total_bets"] >= 100),
    "bets_1000": ("プレイの鬼", "累計1,000回プレイした", "🔥", lambda s: s["total_bets"] >= 1000),
    "wagered_10k": ("駆け出し", "累計プレイ額が10,000を超えた", "🪙", lambda s: s["total_wagered"] >= 10000),
    "wagered_100k": ("常連プレイヤー", "累計プレイ額が100,000を超えた", "💰", lambda s: s["total_wagered"] >= 100000),
    "wagered_1m": ("ハイローラー", "累計プレイ額が1,000,000を超えた", "💎", lambda s: s["total_wagered"] >= 1000000),
    "big_win_10x": ("倍率ハンター", "10倍以上の配当を獲得した", "⚡", lambda s: s["max_multiplier"] >= 10),
    "big_win_50x": ("大金星", "50倍以上の配当を獲得した", "🌟", lambda s: s["max_multiplier"] >= 50),
    "big_win_100x": ("ジャックポット", "100倍以上の配当を獲得した", "🏆", lambda s: s["max_multiplier"] >= 100),
    "level_5": ("レベル5到達", "プレイヤーレベル5に到達した", "🥉", lambda s: s["level"] >= 5),
    "level_10": ("レベル10到達", "プレイヤーレベル10に到達した", "🥈", lambda s: s["level"] >= 10),
    "level_25": ("レベル25到達", "プレイヤーレベル25に到達した", "🥇", lambda s: s["level"] >= 25),
    "debt_free": ("完済達成", "借金を完済した", "🕊️", lambda s: s["debt_cleared"]),
    "vip": ("VIP認定", "VIPに認定された", "👑", lambda s: s["is_vip"]),
    "chat_10": ("おしゃべり", "チャットに10回投稿した", "💬", lambda s: s["chat_count"] >= 10),
    "giveaway_win": ("当選者", "プレゼント企画に当選した", "🎁", lambda s: s["giveaway_wins"] >= 1),
    "event_win": ("トップランカー", "イベントで入賞した", "🏁", lambda s: s["event_wins"] >= 1),
    "night_owl": ("夜更かし", "深夜0時〜4時にプレイした", "🦉", lambda s: s["night_bet"]),
    "first_gacha": ("召喚士デビュー", "初めてガチャでキャラクターを手に入れた", "🎴", lambda s: s["character_count"] >= 1),
    "collector": ("コレクター", "10種類以上のキャラクターを集めた", "📖", lambda s: s["character_count"] >= 10),
    "td_victory": ("タワーディフェンス制覇", "タワーディフェンスを全ウェーブクリアした", "🏰", lambda s: s["td_victories"] >= 1),
}


def _collect_stats(user):
    from sqlalchemy import func
    from models import GiveawayEntry

    agg = (
        db.session.query(
            func.count(BetRecord.id), func.coalesce(func.sum(BetRecord.wager), 0),
            func.coalesce(func.max(BetRecord.multiplier), 0)
        )
        .filter(BetRecord.user_id == user.id)
        .first()
    )
    total_bets, total_wagered, max_multiplier = agg

    win_count = (
        BetRecord.query.filter(BetRecord.user_id == user.id, BetRecord.payout > BetRecord.wager).count()
    )

    night_bet = False
    try:
        night_bet = db.session.query(BetRecord.id).filter(
            BetRecord.user_id == user.id,
            func.strftime("%H", BetRecord.created_at).in_(["00", "01", "02", "03"])
        ).first() is not None
    except Exception:
        db.session.rollback()  # SQLite以外(Postgresなど)ではstrftimeが使えないため、その場合は判定をスキップする

    chat_count = 0
    try:
        from models import ChatMessage
        chat_count = ChatMessage.query.filter_by(user_id=user.id).count()
    except Exception:
        pass

    giveaway_wins = GiveawayEntry.query.filter_by(user_id=user.id, is_winner=True).count()

    character_count = 0
    td_victories = 0
    try:
        from models import UserCharacter, TowerDefenseRun
        character_count = UserCharacter.query.filter_by(user_id=user.id).count()
        td_victories = TowerDefenseRun.query.filter_by(user_id=user.id, victory=True).count()
    except Exception:
        pass

    return {
        "total_bets": total_bets or 0,
        "total_wagered": total_wagered or 0,
        "max_multiplier": max_multiplier or 0,
        "win_count": win_count,
        "level": user.level,
        "debt_cleared": (user.debt == 0) and (total_bets or 0) > 0,
        "is_vip": user.is_vip,
        "chat_count": chat_count,
        "giveaway_wins": giveaway_wins,
        "event_wins": getattr(user, "_event_wins_hint", 0),
        "night_bet": night_bet,
        "character_count": character_count,
        "td_victories": td_victories,
    }


def check_achievements(user, event_win=False):
    """まだ解除していない実績を判定し、条件を満たしていれば解除して通知する"""
    from notifications import notify

    unlocked_keys = {a.achievement_key for a in UserAchievement.query.filter_by(user_id=user.id).all()}
    remaining = {k: v for k, v in ACHIEVEMENTS.items() if k not in unlocked_keys}
    if not remaining:
        return

    stats = _collect_stats(user)
    if event_win:
        stats["event_wins"] = 1

    for key, (name, desc, icon, check_fn) in remaining.items():
        try:
            if check_fn(stats):
                db.session.add(UserAchievement(user_id=user.id, achievement_key=key))
                notify(user.id, f"実績解除: {icon} 「{name}」 ─ {desc}")
        except Exception:
            continue

    db.session.commit()
