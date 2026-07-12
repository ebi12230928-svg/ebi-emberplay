import fairness

DEBT_REPAY_RATE = 0.01  # 借金完済の瞬間に余った勝利分をこの倍率で残高に反映する

MIN_PAYOUT_SCALAR = 0.0     # 管理者が設定できる下限(0=そのゲームの配当を完全にゼロにする)
MAX_PAYOUT_SCALAR = 1000.0  # 管理者が設定できる上限(実質無制限。極端な値を入れる際は自己責任で)


def get_payout_scalar(game_key: str) -> float:
    """管理者が設定した、そのゲームの配当倍率スケール(未設定なら1.0=通常)"""
    from models import GameSetting
    row = GameSetting.query.get(game_key)
    return row.payout_scalar if row else 1.0


def clear_stale_game(model, user, wager_field="wager", timestamp_field="created_at", timeout_minutes=30):
    """
    放置されて「詰み」状態になった進行中ゲーム(Mines・HiLo・Blackjackなど)を自動的に片付け、
    賭け金を全額返金する(ページを閉じた・通信が途切れたなどで途中終了した場合の保険)。
    ゲームのページを開いた時・新しいゲームを始めようとした時に呼び出す。
    """
    from datetime import timedelta
    from extensions import db
    from models import utcnow

    game = model.query.filter_by(user_id=user.id).first()
    if not game:
        return False
    ts = getattr(game, timestamp_field, None)
    if not ts or utcnow() - ts <= timedelta(minutes=timeout_minutes):
        return False

    wager = (getattr(game, wager_field, 0) or 0) if wager_field else 0
    if wager > 0:
        credit_winnings(user, wager)
    db.session.delete(game)
    db.session.commit()
    return True


def cancel_stuck_game(model, user, wager_field="wager"):
    """『動かなくなった場合』のための手動リセット。進行中のゲームを強制的に片付け、賭け金を全額返金する"""
    from extensions import db

    game = model.query.filter_by(user_id=user.id).first()
    if not game:
        return None
    wager = (getattr(game, wager_field, 0) or 0) if wager_field else 0
    if wager > 0:
        credit_winnings(user, wager)
    db.session.delete(game)
    db.session.commit()
    return wager


def get_win_boost(game_key: str) -> float:
    """管理者が設定した、そのゲームの勝率補正(未設定なら0.0=補正なし)"""
    from models import GameSetting
    row = GameSetting.query.get(game_key)
    return row.win_boost if row else 0.0


def apply_win_boost(game_key: str, won: bool) -> bool:
    """
    管理者が設定した勝率補正(win_boost)に基づき、自然な抽選結果の勝敗を確率的に上書きする。
    boost > 0: 負けを勝ちに反転させる確率(1.0で常に勝ちになる)
    boost < 0: 勝ちを負けに反転させる確率(-1.0で常に負けになる)
    ※ このロジック自体はProvably Fairの検証対象外(管理者専用の調整機能)
    """
    import random
    boost = get_win_boost(game_key)
    if boost == 0:
        return won
    roll = random.random()
    if boost > 0 and not won and roll < min(1.0, boost):
        return True
    if boost < 0 and won and roll < min(1.0, abs(boost)):
        return False
    return won


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


def credit_reward(user, amount):
    """
    タワーディフェンス・RPG・ガチャなど、カジノゲーム以外の場所でも使える汎用の残高加算ヘルパー。
    ブラックリスト登録済みのユーザーには一切反映しない(借金の自動返済ロジックは適用しない、単純な加算)。
    """
    if amount <= 0:
        return False
    if getattr(user, "is_blacklisted", False):
        return False
    user.balance += amount
    return True


def credit_winnings(user, amount):
    """
    勝利ポイントを付与する。
    ブラックリスト登録済みのユーザーには一切反映しない(何をしても残高が増えなくなる)。
    借金がある間は、勝利分を全額そのまま借金の返済に充てる(残高には反映されない)。
    その回で借金がちょうど完済になった場合、余った分だけ0.01倍換算で残高に反映し、
    以降は通常どおり全額が残高に反映されるようになる。
    """
    if amount <= 0:
        return
    if getattr(user, "is_blacklisted", False):
        return  # ブラックリスト登録済みのユーザーは、勝っても一切反映しない
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
