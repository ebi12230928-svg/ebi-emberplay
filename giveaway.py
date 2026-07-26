import random
import json

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import Giveaway, GiveawayEntry, Transaction, DirectMessage
from games.common import credit_winnings
from notifications import notify, notify_all

giveaway_bp = Blueprint("giveaway", __name__)


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@giveaway_bp.route("/giveaways")
@login_required
def index():
    open_giveaways = Giveaway.query.filter_by(status="open").order_by(Giveaway.created_at.desc()).all()
    closed_giveaways = Giveaway.query.filter_by(status="closed").order_by(Giveaway.drawn_at.desc()).limit(20).all()

    my_entry_ids = {
        e.giveaway_id for e in GiveawayEntry.query.filter_by(user_id=current_user.id).all()
    }

    closed_info = []
    for g in closed_giveaways:
        winner_entries = g.entries.filter_by(is_winner=True).all()
        if g.source_type == "referral_ranking":
            # 招待ランキング型は、順位(=倍率が大きい順)で並び替えて、順位・紹介人数・倍率も見せる
            winner_entries = sorted(winner_entries, key=lambda e: -(e.reward_multiplier or 0))
            winners = [
                f"{i + 1}位 {e.user.username}({e.referral_count}人紹介・{e.reward_multiplier}倍)"
                for i, e in enumerate(winner_entries)
            ]
        else:
            winners = [e.user.username for e in winner_entries]
        closed_info.append({"giveaway": g, "winners": winners})

    return render_template(
        "giveaways.html", open_giveaways=open_giveaways, closed_info=closed_info, my_entry_ids=my_entry_ids
    )


@giveaway_bp.route("/giveaways/<int:giveaway_id>/enter", methods=["POST"])
@login_required
def enter(giveaway_id):
    from sqlalchemy import func
    from models import User

    giveaway = Giveaway.query.get(giveaway_id)
    if not giveaway or giveaway.status != "open":
        flash("この企画は現在参加できません。", "error")
        return redirect(url_for("giveaway.index"))

    if giveaway.source_type == "referral_ranking":
        # 参加条件: 指定人数以上を紹介していないとエントリーできない
        my_referral_count = (
            db.session.query(func.count(User.id))
            .filter(User.referred_by_id == current_user.id)
            .scalar() or 0
        )
        if my_referral_count < giveaway.min_referral_count:
            flash(f"この企画は{giveaway.min_referral_count}人以上を紹介していないとエントリーできません(現在: {my_referral_count}人)。", "error")
            return redirect(url_for("giveaway.index"))

    existing = GiveawayEntry.query.filter_by(giveaway_id=giveaway_id, user_id=current_user.id).first()
    if existing:
        flash("すでに参加済みです。", "error")
        return redirect(url_for("giveaway.index"))

    db.session.add(GiveawayEntry(giveaway_id=giveaway_id, user_id=current_user.id))
    db.session.commit()

    flash(f"「{giveaway.title}」に参加しました。抽選をお楽しみに!", "success")
    return redirect(url_for("giveaway.index"))


@giveaway_bp.route("/admin/giveaways/create", methods=["POST"])
@login_required
@admin_required
def create():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    prize_type = request.form.get("prize_type", "embers")
    if prize_type not in ("embers", "paypay"):
        prize_type = "embers"
    source_type = request.form.get("source_type", "manual")
    if source_type not in ("manual", "referral_ranking"):
        source_type = "manual"

    if not title:
        flash("タイトルを入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    # 招待ランキング型は、常に上位3名(1位=5倍・2位=3倍・3位=2倍)固定の仕組みなので、当選人数は3に固定する
    winner_count = 3 if source_type == "referral_ranking" else None
    if winner_count is None:
        try:
            winner_count = int(request.form.get("winner_count", "1"))
        except ValueError:
            flash("当選人数は数値で入力してください。", "error")
            return redirect(url_for("admin.dashboard"))
        if winner_count <= 0:
            flash("当選人数を正しく入力してください。", "error")
            return redirect(url_for("admin.dashboard"))

    min_referral_count = 1
    if source_type == "referral_ranking":
        try:
            min_referral_count = int(request.form.get("min_referral_count", "3"))
        except ValueError:
            flash("参加条件(最低招待人数)は数値で入力してください。", "error")
            return redirect(url_for("admin.dashboard"))
        if min_referral_count < 1:
            flash("参加条件(最低招待人数)は1以上で入力してください。", "error")
            return redirect(url_for("admin.dashboard"))

    paypay_links_json = None
    prize_amount = 0

    if prize_type == "paypay":
        # PayPayの場合、賞金は「Embersの自動付与」ではなく、管理者が事前にPayPayアプリ側で
        # 作成した送金リンクを当選者へ届けるだけの仕組みにする(このサイトは送金処理そのものには
        # 一切関与しない。カジノゲームの勝敗とも完全に無関係の、通常の抽選企画/ランキング企画として扱う)
        # 招待ランキング型の場合は、1位から順にリンクを割り当てるため、金額の大きい順に貼り付けてもらう想定
        raw_links = request.form.get("paypay_links", "")
        links = [line.strip() for line in raw_links.splitlines() if line.strip()]
        if len(links) < winner_count:
            flash(f"当選人数({winner_count}名)分のPayPay送金リンクを、1行に1つずつ入力してください。", "error")
            return redirect(url_for("admin.dashboard"))
        paypay_links_json = json.dumps(links)
    else:
        try:
            prize_amount = int(request.form.get("prize_amount", "0"))
        except ValueError:
            flash("賞金額は数値で入力してください。", "error")
            return redirect(url_for("admin.dashboard"))
        if prize_amount <= 0:
            flash("賞金額(招待ランキング型の場合は基本報酬額)を正しく入力してください。", "error")
            return redirect(url_for("admin.dashboard"))

    giveaway = Giveaway(
        title=title, description=description, prize_amount=prize_amount,
        winner_count=winner_count, created_by=current_user.username,
        prize_type=prize_type, paypay_links_json=paypay_links_json,
        source_type=source_type, min_referral_count=min_referral_count,
    )
    db.session.add(giveaway)
    db.session.commit()

    if source_type == "referral_ranking":
        notify_all(f"新しいプレゼント企画「{title}」が始まりました。招待人数ランキングの上位3名(1位5倍・2位3倍・3位2倍)に自動で当たります。参加には{min_referral_count}人以上の紹介が必要です。")
    else:
        prize_desc = f"{prize_amount:,} Embers" if prize_type == "embers" else "PayPay送金リンク"
        notify_all(f"新しいプレゼント企画「{title}」が始まりました。{prize_desc}が{winner_count}名に当たります。/giveawaysから参加できます。")
    db.session.commit()

    flash(f"「{title}」を作成しました。", "success")
    return redirect(url_for("admin.dashboard"))


@giveaway_bp.route("/admin/giveaways/<int:giveaway_id>/draw", methods=["POST"])
@login_required
@admin_required
def draw(giveaway_id):
    from models import utcnow, User

    giveaway = Giveaway.query.get(giveaway_id)
    if not giveaway or giveaway.status != "open":
        flash("この企画はすでに抽選済みか、存在しません。", "error")
        return redirect(url_for("admin.dashboard"))

    if giveaway.source_type == "referral_ranking":
        return _draw_referral_ranking(giveaway)
    return _draw_manual(giveaway)


def _draw_manual(giveaway):
    """通常の抽選企画: 参加エントリーの中からランダムに当選者を選ぶ"""
    from models import utcnow

    entries = giveaway.entries.all()
    if not entries:
        flash("参加者が1人もいないため抽選できません。", "error")
        return redirect(url_for("admin.dashboard"))

    winner_count = min(giveaway.winner_count, len(entries))
    winners = random.sample(entries, winner_count)

    paypay_links = json.loads(giveaway.paypay_links_json) if giveaway.prize_type == "paypay" and giveaway.paypay_links_json else []

    for i, entry in enumerate(winners):
        entry.is_winner = True

        if giveaway.prize_type == "paypay":
            link = paypay_links[i] if i < len(paypay_links) else None
            entry.paypay_link_sent = link
            notify(entry.user_id, f"🎉 おめでとうございます!「{giveaway.title}」に当選しました。DMでPayPayの受け取りリンクをお送りしました。")
            if link:
                _send_admin_dm(entry.user_id, f"🎉「{giveaway.title}」当選おめでとうございます!以下のリンクからPayPayを受け取ってください: {link}")
        else:
            credit_winnings(entry.user, giveaway.prize_amount)
            db.session.add(Transaction(
                user_id=entry.user_id, amount=giveaway.prize_amount, kind="giveaway_win",
                description=f"「{giveaway.title}」当選"
            ))
            notify(entry.user_id, f"おめでとうございます!「{giveaway.title}」に当選し、{giveaway.prize_amount:,} Embersを獲得しました。")

        try:
            from achievements import check_achievements
            check_achievements(entry.user)
        except Exception:
            pass

    giveaway.status = "closed"
    giveaway.drawn_at = utcnow()
    db.session.commit()

    winner_names = ", ".join(e.user.username for e in winners)
    notify_all(f"「{giveaway.title}」の当選者が決定しました: {winner_names}")
    db.session.commit()

    flash(f"抽選が完了しました。当選者: {winner_names}", "success")
    return redirect(url_for("admin.dashboard"))


RANK_MULTIPLIERS = {0: 5, 1: 3, 2: 2}  # 1位=5倍・2位=3倍・3位=2倍


def _draw_referral_ranking(giveaway):
    """
    招待ランキング型: 指定人数以上を紹介しているユーザーだけがエントリーできる。
    エントリーした人たちの中で、招待(紹介)人数が多い順にランキングし、上位3名に
    「基本報酬(またはPayPayリンク)×倍率」(1位=5倍・2位=3倍・3位=2倍)を自動配布する。
    """
    from sqlalchemy import func
    from models import utcnow, User

    entries = giveaway.entries.all()
    if not entries:
        flash("エントリーした人が1人もいないため抽選できません。", "error")
        return redirect(url_for("admin.dashboard"))

    # エントリーした人それぞれの、現時点での紹介人数を数える
    entrant_ids = [e.user_id for e in entries]
    counts_by_user = dict(
        db.session.query(User.referred_by_id, func.count(User.id))
        .filter(User.referred_by_id.in_(entrant_ids))
        .group_by(User.referred_by_id)
        .all()
    )

    ranked = sorted(
        entries, key=lambda e: counts_by_user.get(e.user_id, 0), reverse=True
    )[:3]

    paypay_links = json.loads(giveaway.paypay_links_json) if giveaway.prize_type == "paypay" and giveaway.paypay_links_json else []

    results = []
    for rank, entry in enumerate(ranked):
        user = entry.user
        count = counts_by_user.get(entry.user_id, 0)
        multiplier = RANK_MULTIPLIERS[rank]

        entry.is_winner = True
        entry.referral_count = count
        entry.reward_multiplier = multiplier

        if giveaway.prize_type == "paypay":
            link = paypay_links[rank] if rank < len(paypay_links) else None
            entry.paypay_link_sent = link
            notify(user.id, f"🏆 招待ランキング{rank + 1}位おめでとうございます!({count}人紹介・{multiplier}倍)DMでPayPayの受け取りリンクをお送りしました。")
            if link:
                _send_admin_dm(user.id, f"🏆「{giveaway.title}」招待ランキング{rank + 1}位、おめでとうございます!({count}人紹介・{multiplier}倍)以下のリンクからPayPayを受け取ってください: {link}")
        else:
            reward = giveaway.prize_amount * multiplier
            user.balance += reward
            db.session.add(Transaction(
                user_id=user.id, amount=reward, kind="referral_ranking",
                description=f"「{giveaway.title}」招待ランキング{rank + 1}位ボーナス(紹介{count}人・{multiplier}倍)"
            ))
            notify(user.id, f"🏆 招待ランキング{rank + 1}位おめでとうございます!({count}人紹介・{multiplier}倍ボーナス){reward:,} Embersを獲得しました。")

        try:
            from achievements import check_achievements
            check_achievements(user)
        except Exception:
            pass

        results.append(f"{rank + 1}位 {user.username}({count}人・{multiplier}倍)")

    giveaway.status = "closed"
    giveaway.drawn_at = utcnow()
    db.session.commit()

    winner_summary = " / ".join(results)
    notify_all(f"🏆「{giveaway.title}」招待ランキングの結果: {winner_summary}")
    db.session.commit()

    flash(f"招待ランキング報酬を配布しました: {winner_summary}", "success")
    return redirect(url_for("admin.dashboard"))


def _send_admin_dm(to_user_id, message):
    """
    運営(管理者)からの当選連絡DM。通常のDM機能はフレンド間限定だが、これは
    運営からの当選連絡なのでフレンド制限の対象外として、直接メッセージ行を作成する。
    """
    db.session.add(DirectMessage(from_user_id=current_user.id, to_user_id=to_user_id, message=message))


@giveaway_bp.route("/admin/giveaways/<int:giveaway_id>/cancel", methods=["POST"])
@login_required
@admin_required
def cancel(giveaway_id):
    giveaway = Giveaway.query.get(giveaway_id)
    if giveaway and giveaway.status == "open":
        db.session.delete(giveaway)
        db.session.commit()
        flash("企画を削除しました。", "success")
    return redirect(url_for("admin.dashboard"))
