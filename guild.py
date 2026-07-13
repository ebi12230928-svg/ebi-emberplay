"""ギルド機能。フレンドより大きい単位のチーム。1人1ギルドまで所属できる。"""
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Guild, GuildMember, User

guild_bp = Blueprint("guild", __name__)


@guild_bp.route("/guild")
@login_required
def index():
    my_membership = GuildMember.query.filter_by(user_id=current_user.id).first()
    my_guild = my_membership.guild_id if my_membership else None

    if my_guild:
        guild = Guild.query.get(my_guild)
        members = GuildMember.query.filter_by(guild_id=guild.id).all()
        return render_template("guild.html", guild=guild, members=members, is_owner=(guild.owner_id == current_user.id))

    guilds = Guild.query.order_by(Guild.points.desc()).limit(30).all()
    member_counts = {g.id: GuildMember.query.filter_by(guild_id=g.id).count() for g in guilds}
    return render_template("guild_list.html", guilds=guilds, member_counts=member_counts)


@guild_bp.route("/guild/create", methods=["POST"])
@login_required
def create():
    if GuildMember.query.filter_by(user_id=current_user.id).first():
        flash("すでにギルドに所属しています。", "error")
        return redirect(url_for("guild.index"))

    name = request.form.get("name", "").strip()[:40]
    description = request.form.get("description", "").strip()[:200]
    if not name:
        flash("ギルド名を入力してください。", "error")
        return redirect(url_for("guild.index"))
    if Guild.query.filter_by(name=name).first():
        flash("そのギルド名はすでに使われています。", "error")
        return redirect(url_for("guild.index"))

    guild = Guild(name=name, owner_id=current_user.id, description=description)
    db.session.add(guild)
    db.session.flush()
    db.session.add(GuildMember(guild_id=guild.id, user_id=current_user.id))
    db.session.commit()
    flash(f"ギルド「{name}」を設立しました!", "success")
    return redirect(url_for("guild.index"))


@guild_bp.route("/guild/<int:guild_id>/join", methods=["POST"])
@login_required
def join(guild_id):
    if GuildMember.query.filter_by(user_id=current_user.id).first():
        flash("すでにギルドに所属しています。", "error")
        return redirect(url_for("guild.index"))
    guild = Guild.query.get(guild_id)
    if not guild:
        flash("ギルドが見つかりません。", "error")
        return redirect(url_for("guild.index"))

    db.session.add(GuildMember(guild_id=guild.id, user_id=current_user.id))
    db.session.commit()
    flash(f"ギルド「{guild.name}」に加入しました!", "success")
    return redirect(url_for("guild.index"))


@guild_bp.route("/guild/leave", methods=["POST"])
@login_required
def leave():
    membership = GuildMember.query.filter_by(user_id=current_user.id).first()
    if membership:
        guild = Guild.query.get(membership.guild_id)
        db.session.delete(membership)
        db.session.commit()
        if guild and guild.owner_id == current_user.id:
            remaining = GuildMember.query.filter_by(guild_id=guild.id).count()
            if remaining == 0:
                db.session.delete(guild)
                db.session.commit()
    return redirect(url_for("guild.index"))
