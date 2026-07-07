from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models import Transaction, RedeemCode, RedeemCodeRedemption
from models import utcnow
from config import Config

rewards_bp = Blueprint("rewards", __name__)


def _time_left(last_claim, cooldown: timedelta):
    if not last_claim:
        return None
    next_available = last_claim + cooldown
    remaining = next_available - utcnow()
    return remaining if remaining.total_seconds() > 0 else None


def _monthly_locked_by_debt(user) -> bool:
    """借金を1ヶ月以上返済していない場合、マンスリー報酬をロックする"""
    if not user.debt or user.debt <= 0 or not user.debt_started_at:
        return False
    return (utcnow() - user.debt_started_at) > timedelta(days=30)


@rewards_bp.route("/wallet")
@login_required
def wallet():
    user = current_user

    def secs(td):
        return int(td.total_seconds()) if td else 0

    # ログインストリーク: 「前回受け取り日」が今日か昨日かで継続/途切れを判定するだけ(受け取り操作はclaim_streakで行う)
    streak_ready = True
    streak_next_day = user.login_streak_count + 1
    if user.last_streak_claim:
        last_date = user.last_streak_claim.date()
        today = utcnow().date()
        if last_date == today:
            streak_ready = False  # 今日はすでに受け取り済み
        elif (today - last_date).days > 1:
            streak_next_day = 1  # 1日以上空いたのでリセット

    idx = min(streak_next_day, len(Config.LOGIN_STREAK_REWARDS)) - 1
    streak_reward_amount = Config.LOGIN_STREAK_REWARDS[idx]

    context = {
        "hourly_wait": secs(_time_left(user.last_hourly_claim, timedelta(hours=1))),
        "daily_wait": secs(_time_left(user.last_daily_claim, timedelta(hours=24))),
        "weekly_wait": secs(_time_left(user.last_weekly_claim, timedelta(days=7))),
        "monthly_wait": secs(_time_left(user.last_monthly_claim, timedelta(days=30))),
        "reload_wait": secs(_time_left(user.last_reload_claim, timedelta(hours=Config.RELOAD_COOLDOWN_HOURS))),
        "reload_eligible": user.balance <= Config.RELOAD_THRESHOLD,
        "monthly_locked": _monthly_locked_by_debt(user),
        "streak_ready": streak_ready,
        "streak_next_day": streak_next_day,
        "streak_reward_amount": streak_reward_amount,
        "config": Config,
    }
    return render_template("wallet.html", **context)


def _grant(user, amount, kind, description):
    user.balance += amount
    db.session.add(Transaction(user_id=user.id, amount=amount, kind=kind, description=description))
    db.session.commit()


@rewards_bp.route("/rewards/daily", methods=["POST"])
@login_required
def claim_daily():
    if _time_left(current_user.last_daily_claim, timedelta(hours=24)):
        flash("デイリー報酬はまだ受け取れません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.last_daily_claim = utcnow()
    _grant(current_user, Config.DAILY_REWARD, "daily", "デイリー報酬")
    flash(f"デイリー報酬として {Config.DAILY_REWARD:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/hourly", methods=["POST"])
@login_required
def claim_hourly():
    if _time_left(current_user.last_hourly_claim, timedelta(hours=1)):
        flash("アワリー報酬はまだ受け取れません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.last_hourly_claim = utcnow()
    _grant(current_user, Config.HOURLY_REWARD, "hourly", "アワリー報酬")
    flash(f"アワリー報酬として {Config.HOURLY_REWARD:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/streak", methods=["POST"])
@login_required
def claim_streak():
    user = current_user
    today = utcnow().date()

    if user.last_streak_claim and user.last_streak_claim.date() == today:
        flash("ログインボーナスは今日すでに受け取り済みです。", "error")
        return redirect(url_for("rewards.wallet"))

    if user.last_streak_claim and (today - user.last_streak_claim.date()).days > 1:
        user.login_streak_count = 0  # 1日以上あいたのでリセット

    user.login_streak_count += 1
    user.last_streak_claim = utcnow()

    idx = min(user.login_streak_count, len(Config.LOGIN_STREAK_REWARDS)) - 1
    amount = Config.LOGIN_STREAK_REWARDS[idx]
    _grant(user, amount, "login_streak", f"ログインボーナス({user.login_streak_count}日目)")

    flash(f"ログインボーナス({user.login_streak_count}日目)として {amount:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/weekly", methods=["POST"])
@login_required
def claim_weekly():
    if _time_left(current_user.last_weekly_claim, timedelta(days=7)):
        flash("ウィークリー報酬はまだ受け取れません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.last_weekly_claim = utcnow()
    _grant(current_user, Config.WEEKLY_REWARD, "weekly", "ウィークリー報酬")
    flash(f"ウィークリー報酬として {Config.WEEKLY_REWARD:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/monthly", methods=["POST"])
@login_required
def claim_monthly():
    if _monthly_locked_by_debt(current_user):
        flash("借金を1ヶ月以内に返済しなかったため、マンスリー報酬は借金完済まで利用できません。", "error")
        return redirect(url_for("rewards.wallet"))

    if _time_left(current_user.last_monthly_claim, timedelta(days=30)):
        flash("マンスリー報酬はまだ受け取れません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.last_monthly_claim = utcnow()
    _grant(current_user, Config.MONTHLY_REWARD, "monthly", "マンスリー報酬")
    flash(f"マンスリー報酬として {Config.MONTHLY_REWARD:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/reload", methods=["POST"])
@login_required
def claim_reload():
    if current_user.balance > Config.RELOAD_THRESHOLD:
        flash(f"リロード報酬は残高が {Config.RELOAD_THRESHOLD:,} Embers以下のときだけ受け取れます。", "error")
        return redirect(url_for("rewards.wallet"))

    if _time_left(current_user.last_reload_claim, timedelta(hours=Config.RELOAD_COOLDOWN_HOURS)):
        flash("リロード報酬はまだ受け取れません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.last_reload_claim = utcnow()
    _grant(current_user, Config.RELOAD_AMOUNT, "reload", "リロード報酬")
    flash(f"リロード報酬として {Config.RELOAD_AMOUNT:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/rakeback", methods=["POST"])
@login_required
def claim_rakeback():
    amount = current_user.pending_rakeback
    if amount <= 0:
        flash("受け取れるレーキバックがありません。", "error")
        return redirect(url_for("rewards.wallet"))

    current_user.pending_rakeback = 0
    _grant(current_user, amount, "rakeback", "レーキバック")
    flash(f"レーキバックとして {amount:,} Embersを受け取りました。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/rewards/borrow", methods=["POST"])
@login_required
def borrow():
    user = current_user
    if user.debt and user.debt > 0:
        flash("すでに借金があります。完済してからもう一度借りてください。", "error")
        return redirect(url_for("rewards.wallet"))

    user.debt = Config.LOAN_AMOUNT
    user.debt_started_at = utcnow()
    user.balance += Config.LOAN_AMOUNT
    db.session.add(Transaction(
        user_id=user.id, amount=Config.LOAN_AMOUNT, kind="loan",
        description="借金による借り入れ"
    ))
    db.session.commit()

    flash(f"{Config.LOAN_AMOUNT:,} Embersを借り入れました。完済するまで勝利分は返済に充てられます。", "success")
    return redirect(url_for("rewards.wallet"))


@rewards_bp.route("/redeem", methods=["GET", "POST"])
@login_required
def redeem():
    if request.method == "POST":
        code_text = request.form.get("code", "").strip()
        rc = RedeemCode.query.filter_by(code=code_text, active=True).first()

        if not rc:
            flash("そのコードは無効か、存在しません。", "error")
            return redirect(url_for("rewards.redeem"))

        if rc.code_type == "once_per_user":
            already = RedeemCodeRedemption.query.filter_by(code_id=rc.id, user_id=current_user.id).first()
            if already:
                flash("このコードはすでに利用済みです。", "error")
                return redirect(url_for("rewards.redeem"))
        else:  # global_limit
            if rc.max_global_uses and rc.total_uses >= rc.max_global_uses:
                flash("このコードは利用回数の上限に達しています。", "error")
                return redirect(url_for("rewards.redeem"))

        rc.total_uses += 1
        db.session.add(RedeemCodeRedemption(code_id=rc.id, user_id=current_user.id))
        _grant(current_user, rc.amount, "redeem_code", f"コード「{rc.code}」の利用")
        flash(f"コードを利用して {rc.amount:,} Embersを受け取りました。", "success")
        return redirect(url_for("rewards.redeem"))

    return render_template("redeem.html")


@rewards_bp.route("/fairness", methods=["GET", "POST"])
@login_required
def fairness_settings():
    if request.method == "POST":
        new_client_seed = request.form.get("client_seed", "").strip()
        if new_client_seed:
            current_user.client_seed = new_client_seed[:64]
            db.session.commit()
            flash("クライアントシードを更新しました。", "success")
        elif request.form.get("action") == "rotate":
            old_seed, old_nonce = current_user.rotate_server_seed()
            db.session.commit()
            flash(f"サーバーシードをローテーションしました。前回のシード: {old_seed}(nonce {old_nonce}回分)", "success")
        return redirect(url_for("rewards.fairness_settings"))

    return render_template("fairness.html", user=current_user)
