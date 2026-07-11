"""デイリーチャレンジ機能。毎日(UTC基準)リセットされる、その日限りの簡単な目標と報酬。"""
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, DailyChallengeClaim, Transaction, utcnow

challenges_bp = Blueprint("challenges", __name__)

# key -> (表示名, 説明, 判定関数(statsを受け取りboolを返す), 報酬)
CHALLENGES = {
    "variety": ("色々遊ぼう", "今日、3種類以上の異なるゲームをプレイする", lambda s: s["distinct_games"] >= 3, 300),
    "wager": ("たくさん賭けよう", "今日の合計プレイ額が2,000に到達する", lambda s: s["total_wagered"] >= 2000, 400),
    "wins": ("勝利を重ねよう", "今日、3回勝利する", lambda s: s["win_count"] >= 3, 300),
    "bigwin": ("大勝負", "今日、5倍以上の配当を1回獲得する", lambda s: s["max_multiplier"] >= 5, 500),
    "plays": ("たくさんプレイ", "今日、合計10回プレイする", lambda s: s["total_bets"] >= 10, 250),
}


def _today_str():
    return utcnow().strftime("%Y-%m-%d")


def _today_stats(user_id):
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = BetRecord.query.filter(BetRecord.user_id == user_id, BetRecord.created_at >= today_start).all()

    total_bets = len(rows)
    total_wagered = sum(r.wager for r in rows)
    win_count = sum(1 for r in rows if r.payout > r.wager)
    max_multiplier = max((r.multiplier for r in rows), default=0)
    distinct_games = len({r.game for r in rows})

    return {
        "total_bets": total_bets, "total_wagered": total_wagered, "win_count": win_count,
        "max_multiplier": max_multiplier, "distinct_games": distinct_games,
    }


@challenges_bp.route("/challenges")
@login_required
def index():
    stats = _today_stats(current_user.id)
    today = _today_str()
    claimed_keys = {
        c.challenge_key for c in DailyChallengeClaim.query.filter_by(
            user_id=current_user.id, challenge_date=today
        ).all()
    }

    items = []
    for key, (name, desc, check_fn, reward) in CHALLENGES.items():
        completed = check_fn(stats)
        items.append({
            "key": key, "name": name, "description": desc, "reward": reward,
            "completed": completed, "claimed": key in claimed_keys,
        })

    return render_template("challenges.html", items=items, stats=stats)


@challenges_bp.route("/challenges/claim/<key>", methods=["POST"])
@login_required
def claim(key):
    if key not in CHALLENGES:
        return jsonify({"error": "存在しないチャレンジです。"}), 400

    today = _today_str()
    if DailyChallengeClaim.query.filter_by(user_id=current_user.id, challenge_key=key, challenge_date=today).first():
        return jsonify({"error": "すでに受け取り済みです。"}), 400

    name, desc, check_fn, reward = CHALLENGES[key]
    stats = _today_stats(current_user.id)
    if not check_fn(stats):
        return jsonify({"error": "まだ条件を達成していません。"}), 400

    current_user.balance += reward
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="daily_challenge", description=f"デイリーチャレンジ「{name}」達成"
    ))
    db.session.add(DailyChallengeClaim(user_id=current_user.id, challenge_key=key, challenge_date=today))
    db.session.commit()

    return jsonify({"ok": True, "reward": reward, "balance": current_user.balance})
