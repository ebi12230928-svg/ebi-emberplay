"""VIPティア(Bronze/Silver/Gold/Diamond)に応じた特典値を計算するヘルパー"""
from config import Config


def tier_name(user):
    if not user.is_vip:
        return None
    return Config.VIP_TIER_NAMES.get(user.vip_tier, "Bronze")


def rakeback_rate(user):
    if user.is_vip:
        return Config.VIP_TIER_RAKEBACK.get(user.vip_tier, Config.VIP_RAKEBACK_RATE)
    return Config.RAKEBACK_RATE


def xp_multiplier(user):
    if user.is_vip:
        return Config.VIP_TIER_XP_MULTIPLIER.get(user.vip_tier, Config.VIP_XP_MULTIPLIER)
    return Config.XP_MULTIPLIER


def hourly_cooldown_hours(user):
    if user.is_vip:
        return Config.VIP_TIER_HOURLY_COOLDOWN.get(user.vip_tier, Config.VIP_HOURLY_COOLDOWN_HOURS)
    return Config.HOURLY_COOLDOWN_HOURS


def loan_amount(user):
    if user.is_vip:
        return Config.VIP_TIER_LOAN.get(user.vip_tier, Config.VIP_LOAN_AMOUNT)
    return Config.LOAN_AMOUNT


def spin_table(user):
    if user.is_vip:
        prizes = Config.VIP_TIER_SPIN_PRIZES.get(user.vip_tier, Config.VIP_SPIN_PRIZES)
        return prizes, Config.VIP_TIER_SPIN_WEIGHTS
    return Config.SPIN_PRIZES, Config.SPIN_WEIGHTS
