import random

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import Giveaway, GiveawayEntry, Transaction
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
    try:
        prize_amount = int(request.form.get("prize_amount", "0"))
        winner_count = int(request.form.get("winner_count", "1"))
    except ValueError:
        flash("賞金額・当選人数は数値で入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    if not title or prize_amount <= 0 or winner_count <= 0:
        flash("タイトル・賞金額・当選人数を正しく入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    giveaway = Giveaway(
        title=title, description=description, prize_amount=prize_amount,
        winner_count=winner_count, created_by=current_user.username
    )
    db.session.add(giveaway)
    db.session.commit()

    notify_all(f"新しいプレゼント企画「{title}」が始まりました。{prize_amount:,} Embersが{winner_count}名に当たります。/giveawaysから参加できます。")
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

    for entry in winners:
        entry.is_winner = True
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
