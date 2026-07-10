import fairness

DEBT_REPAY_RATE = 0.01  # 借金完済の瞬間に余った勝利分をこの倍率で残高に反映する

MIN_PAYOUT_SCALAR = 0.1   # 管理者が設定できる下限(配当を90%カットまで)
MAX_PAYOUT_SCALAR = 3.0   # 管理者が設定できる上限(配当を3倍まで)


def get_payout_scalar(game_key: str) -> float:
    """管理者が設定した、そのゲームの配当倍率スケール(未設定なら1.0=通常)"""
    from models import GameSetting
    row = GameSetting.query.get(game_key)
    return row.payout_scalar if row else 1.0


def scale_multiplier(game_key: str, multiplier: float) -> float:
    """配当倍率に管理者設定のスケールを掛けて返す(ゲーム内部のオッズ計算はそのまま維持できる)"""
    if not multiplier:
        return multiplier
    scalar = get_payout_scalar(game_key)
    return round(multiplier * scalar, 4)


def apply_rakeback(user, wager):
    from config import Config
    import vip_perks

    rate = vip_perks.rakeback_rate(user)
    user.pending_rakeback += round(wager * rate)

    old_level = user.level
    xp_mult = vip_perks.xp_multiplier(user)
    user.xp += max(1, round((wager // 10) * xp_mult))  # プレイ額10につき1XP(最低1XP、VIPは倍率アップ)

    if user.level > old_level:
        try:
            from notifications import notify
            notify(user.id, f"レベルアップ!Lv.{old_level} → Lv.{user.level}({user.level_title})になりました。")
        except Exception:
            pass

    try:
        from achievements import check_achievements
        check_achievements(user)
    except Exception:
        pass  # 実績判定に失敗してもプレイ自体は継続させる


def next_float(user):
    """現在のnonceで乱数を1つ取り出し、nonceを進める"""
    value = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    return value, used_nonce


def validate_wager(user, wager):
    if wager is None or wager <= 0:
        return "プレイ料を正しく入力してください。"
    if getattr(user, "debt", 0) and user.debt > 0 and user.balance <= 0:
        return "借金を返済中のため、残高が貯まるまでお待ちください(勝利分は自動的に返済に充てられます)。"
    if wager > user.balance:
        return "残高が不足しています。"
    return None


def credit_winnings(user, amount):
    """
    勝利ポイントを付与する。
    借金がある間は、勝利分を全額そのまま借金の返済に充てる(残高には反映されない)。
    その回で借金がちょうど完済になった場合、余った分だけ0.01倍換算で残高に反映し、
    以降は通常どおり全額が残高に反映されるようになる。
    """
    if amount <= 0:
        return
    if getattr(user, "debt", 0) and user.debt > 0:
        repay = min(amount, user.debt)
        user.debt -= repay
        leftover = amount - repay
        if user.debt <= 0:
            user.debt = 0
            user.debt_started_at = None
            if leftover > 0:
                user.balance += round(leftover * DEBT_REPAY_RATE)
        # 借金がまだ残っている場合、この勝利分は残高に反映しない
    else:
        user.balance += amount
