from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import BetRecord, UserAchievement, GiveawayEntry, User, Transaction
from achievements import ACHIEVEMENTS, _collect_stats
from notifications import notify

profile_bp = Blueprint("profile", __name__)

# 進捗バーを表示する数値系の実績と、statsキー・目標値の対応
PROGRESS_ACHIEVEMENTS = {
    "wagered_10k": ("total_wagered", 10000),
    "wagered_100k": ("total_wagered", 100000),
    "wagered_1m": ("total_wagered", 1000000),
    "bets_100": ("total_bets", 100),
    "bets_1000": ("total_bets", 1000),
    "level_5": ("level", 5),
    "level_10": ("level", 10),
    "level_25": ("level", 25),
}


@profile_bp.route("/profile")
@login_required
def index():
    user = current_user

    if not user.referral_code:
        from auth import _generate_referral_code
        user.referral_code = _generate_referral_code()
        db.session.commit()

    agg = (
        db.session.query(
            func.count(BetRecord.id), func.coalesce(func.sum(BetRecord.wager), 0),
            func.coalesce(func.sum(BetRecord.payout), 0), func.coalesce(func.max(BetRecord.multiplier), 0)
        )
        .filter(BetRecord.user_id == user.id)
        .first()
    )
    total_bets, total_wagered, total_payout, max_multiplier = agg
    net_profit = (total_payout or 0) - (total_wagered or 0)

    unlocked = {a.achievement_key for a in UserAchievement.query.filter_by(user_id=user.id).all()}
    stats = _collect_stats(user)

    badge_list = []
    for key, (name, desc, icon, _check) in ACHIEVEMENTS.items():
        entry = {
            "key": key, "name": name, "description": desc, "icon": icon, "unlocked": key in unlocked,
            "progress": None,
        }
        if not entry["unlocked"] and key in PROGRESS_ACHIEVEMENTS:
            stat_key, goal = PROGRESS_ACHIEVEMENTS[key]
            current = stats.get(stat_key, 0)
            entry["progress"] = {
                "current": current, "goal": goal, "pct": min(100, round(current / goal * 100, 1))
            }
        badge_list.append(entry)
    badge_list.sort(key=lambda b: (not b["unlocked"], b["name"]))

    referral_count = User.query.filter_by(referred_by_id=user.id).filter(User.discord_id.isnot(None)).count()
    giveaway_wins = GiveawayEntry.query.filter_by(user_id=user.id, is_winner=True).count()

    next_level_xp = int((user.level ** 2) * 500)

    return render_template(
        "profile.html", user=user, total_bets=total_bets or 0, total_wagered=total_wagered or 0,
        net_profit=net_profit, max_multiplier=max_multiplier or 0, badge_list=badge_list,
        referral_count=referral_count, giveaway_wins=giveaway_wins, next_level_xp=next_level_xp,
        avatar_choices=AVATAR_CHOICES
    )


@profile_bp.route("/profile/apply-referral", methods=["POST"])
@login_required
def apply_referral():
    from config import Config

    if current_user.referred_by_id:
        flash("すでに紹介コードが適用されています。", "error")
        return redirect(url_for("profile.index"))

    code = request.form.get("code", "").strip().upper()
    referrer = User.query.filter_by(referral_code=code).first()

    if not referrer or referrer.id == current_user.id:
        flash("有効な紹介コードではありません。", "error")
        return redirect(url_for("profile.index"))

    if not current_user.discord_id:
        flash("紹介コードを適用するには、先に自分自身がDiscordアカウントと連携している必要があります。", "error")
        return redirect(url_for("profile.index"))

    if not referrer.discord_id:
        flash("この紹介コードは、紹介者がDiscord未連携のため現在適用できません。", "error")
        return redirect(url_for("profile.index"))

    current_user.referred_by_id = referrer.id
    current_user.balance += Config.REFERRAL_BONUS_NEW
    referrer.balance += Config.REFERRAL_BONUS_REFERRER

    db.session.add(Transaction(
        user_id=current_user.id, amount=Config.REFERRAL_BONUS_NEW, kind="referral",
        description=f"{referrer.username} の紹介コードを適用"
    ))
    db.session.add(Transaction(
        user_id=referrer.id, amount=Config.REFERRAL_BONUS_REFERRER, kind="referral",
        description=f"{current_user.username} を紹介"
    ))
    db.session.commit()

    notify(referrer.id, f"{current_user.username} があなたの紹介コードを適用しました。{Config.REFERRAL_BONUS_REFERRER:,} Embersを獲得しました。")
    db.session.commit()

    flash(f"紹介コードを適用し、{Config.REFERRAL_BONUS_NEW:,} Embersを受け取りました。", "success")
    return redirect(url_for("profile.index"))


@profile_bp.route("/tip", methods=["POST"])
@login_required
def tip():
    from models import TipRequest

    target_username = request.form.get("username", "").strip()
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0

    if amount <= 0:
        flash("金額は1以上を入力してください。", "error")
        return redirect(url_for("profile.index"))

    if target_username == current_user.username:
        flash("自分自身にチップは送れません。", "error")
        return redirect(url_for("profile.index"))

    target = User.query.filter_by(username=target_username).first()
    if not target:
        flash("そのユーザーは見つかりません。", "error")
        return redirect(url_for("profile.index"))

    if current_user.balance < amount:
        flash("残高が不足しています。", "error")
        return redirect(url_for("profile.index"))

    db.session.add(TipRequest(from_user_id=current_user.id, to_user_id=target.id, amount=amount))
    db.session.commit()

    flash(f"{target.username} さんへの {amount:,} Embersのチップを申請しました。管理者の承認後に送金されます。", "success")
    return redirect(url_for("profile.index"))


AVATAR_CHOICES = [
    "🔥", "🐲", "🎲", "🃏", "🎰", "💎", "👑", "🍀", "⚡", "🌙",
    "🦊", "🐼", "🐯", "🦁", "🐸", "🐙", "🦄", "🐧", "🌸", "🍒",
    "🍩", "🍭", "🎯", "🎪", "🚀", "⭐", "🌈", "🎨", "😎", "🤖",
]


@profile_bp.route("/profile/avatar", methods=["POST"])
@login_required
def set_avatar():
    avatar = request.form.get("avatar", "").strip()
    if avatar not in AVATAR_CHOICES:
        flash("選択できないアバターです。", "error")
        return redirect(url_for("profile.index"))

    current_user.avatar = avatar
    db.session.commit()
    flash("アバターを変更しました。", "success")
    return redirect(url_for("profile.index"))


@profile_bp.route("/profile/change-username", methods=["POST"])
@login_required
def change_own_username():
    """
    自分自身のユーザー名(ID)を変更する。なりすまし防止のため、現在のパスワードの入力を必須とする。
    """
    import re
    from models import AdminAccountLog

    current_password = request.form.get("current_password", "")
    new_username = request.form.get("new_username", "").strip()

    if not current_user.check_password(current_password):
        flash("現在のパスワードが正しくありません。", "error")
        return redirect(url_for("profile.index"))

    if not re.match(r"^[A-Za-z0-9_]{3,32}$", new_username):
        flash("新しいユーザー名は英数字・アンダースコアのみ、3〜32文字で入力してください。", "error")
        return redirect(url_for("profile.index"))

    if new_username == current_user.username:
        flash("現在のユーザー名と同じです。", "error")
        return redirect(url_for("profile.index"))

    if User.query.filter_by(username=new_username).first():
        flash("そのユーザー名はすでに使われています。", "error")
        return redirect(url_for("profile.index"))

    old_username = current_user.username
    current_user.username = new_username
    db.session.add(AdminAccountLog(
        admin_username=old_username, action="username_changed", target_username=new_username,
        details=f"{old_username} → {new_username}(本人による変更)",
    ))
    db.session.commit()

    flash(f"ユーザー名を {new_username} に変更しました。次回ログインからは新しいユーザー名を使ってください。", "success")
    return redirect(url_for("profile.index"))


@profile_bp.route("/profile/change-password", methods=["POST"])
@login_required
def change_own_password():
    """
    自分自身のパスワードを変更する。なりすまし防止のため、現在のパスワードの入力を必須とする。
    """
    from models import AdminAccountLog

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    new_password_confirm = request.form.get("new_password_confirm", "")

    if not current_user.check_password(current_password):
        flash("現在のパスワードが正しくありません。", "error")
        return redirect(url_for("profile.index"))

    if len(new_password) < 4:
        flash("新しいパスワードは4文字以上で入力してください。", "error")
        return redirect(url_for("profile.index"))

    if new_password != new_password_confirm:
        flash("新しいパスワード(確認)が一致しません。", "error")
        return redirect(url_for("profile.index"))

    current_user.set_password(new_password)
    db.session.add(AdminAccountLog(
        admin_username=current_user.username, action="password_changed", target_username=current_user.username,
        details="本人による変更",
    ))
    db.session.commit()

    flash("パスワードを変更しました。", "success")
    return redirect(url_for("profile.index"))
