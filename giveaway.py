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
        winners = [e.user.username for e in g.entries.filter_by(is_winner=True).all()]
        closed_info.append({"giveaway": g, "winners": winners})

    return render_template(
        "giveaways.html", open_giveaways=open_giveaways, closed_info=closed_info, my_entry_ids=my_entry_ids
    )


@giveaway_bp.route("/giveaways/<int:giveaway_id>/enter", methods=["POST"])
@login_required
def enter(giveaway_id):
    giveaway = Giveaway.query.get(giveaway_id)
    if not giveaway or giveaway.status != "open":
        flash("この企画は現在参加できません。", "error")
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

    try:
        winner_count = int(request.form.get("winner_count", "1"))
    except ValueError:
        flash("当選人数は数値で入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    if not title or winner_count <= 0:
        flash("タイトル・当選人数を正しく入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    paypay_links_json = None
    prize_amount = 0

    if prize_type == "paypay":
        # PayPayの場合、賞金は「Embersの自動付与」ではなく、管理者が事前にPayPayアプリ側で
        # 作成した送金リンクを当選者へ届けるだけの仕組みにする(このサイトは送金処理そのものには
        # 一切関与しない。カジノゲームの勝敗とも完全に無関係の、通常の抽選企画として扱う)
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
            flash("賞金額を正しく入力してください。", "error")
            return redirect(url_for("admin.dashboard"))

    giveaway = Giveaway(
        title=title, description=description, prize_amount=prize_amount,
        winner_count=winner_count, created_by=current_user.username,
        prize_type=prize_type, paypay_links_json=paypay_links_json,
    )
    db.session.add(giveaway)
    db.session.commit()

    prize_desc = f"{prize_amount:,} Embers" if prize_type == "embers" else "PayPay送金リンク"
    notify_all(f"新しいプレゼント企画「{title}」が始まりました。{prize_desc}が{winner_count}名に当たります。/giveawaysから参加できます。")
    db.session.commit()

    flash(f"「{title}」を作成しました。", "success")
    return redirect(url_for("admin.dashboard"))


@giveaway_bp.route("/admin/giveaways/<int:giveaway_id>/draw", methods=["POST"])
@login_required
@admin_required
def draw(giveaway_id):
    from models import utcnow

    giveaway = Giveaway.query.get(giveaway_id)
    if not giveaway or giveaway.status != "open":
        flash("この企画はすでに抽選済みか、存在しません。", "error")
        return redirect(url_for("admin.dashboard"))

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
                # 管理者からのお知らせとして、当選者のDMに直接メッセージを作成する
                # (通常のDM機能はフレンド間限定だが、これは運営からの当選連絡なのでフレンド制限の対象外とする)
                db.session.add(DirectMessage(
                    from_user_id=current_user.id, to_user_id=entry.user_id,
                    message=f"🎉「{giveaway.title}」当選おめでとうございます!以下のリンクからPayPayを受け取ってください: {link}",
                ))
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
