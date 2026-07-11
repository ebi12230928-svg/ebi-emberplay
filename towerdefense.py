"""
タワーディフェンス。ガチャで入手したキャラクターを配置して、波状に迫る敵から拠点を守る。
実際のゲームロジック(敵の移動・タワーの攻撃・当たり判定)はブラウザ側(JS)でリアルタイムに動作し、
サーバーはキャラクターの所持確認と、結果に応じた報酬付与だけを担当する。
「通常」「レイド」「ラスボス」「エンドレスモード」の4種類がある。
"""
import json

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import UserCharacter, TowerDefenseRun, Transaction
import characters as ch

towerdefense_bp = Blueprint("towerdefense", __name__)

MAX_TEAM_SIZE = 6

# waves=Noneはエンドレス(上限なし)を意味する。lastbossは1ウェーブだけ、非常に頑丈な敵1体と戦う特別な形式
TD_MODES = {
    "normal":   {"label": "通常",     "waves": 10, "hp_mult": 1.0, "reward_per_wave": 40, "victory_bonus": 600},
    "raid":     {"label": "レイド",   "waves": 10, "hp_mult": 2.6, "reward_per_wave": 90, "victory_bonus": 1600},
    "lastboss": {"label": "ラスボス", "waves": 1,  "hp_mult": 1.0, "reward_per_wave": 0, "victory_bonus": 3500},
    "endless":  {"label": "エンドレス", "waves": None, "hp_mult": 1.0, "reward_per_wave": 30, "victory_bonus": 0},
}
ENDLESS_REWARD_CAP_WAVES = 60  # 経済保護のため、報酬計算上はこのウェーブ数で頭打ちにする


@towerdefense_bp.route("/towerdefense")
@login_required
def index():
    mode = request.args.get("mode", "normal")
    if mode not in TD_MODES:
        mode = "normal"

    squad_room_id = request.args.get("squad_room", type=int)
    squad_info = None

    if squad_room_id:
        from models import SquadRoom, SquadMember
        room_obj = SquadRoom.query.get(squad_room_id)
        if not room_obj or room_obj.status != "battling" or room_obj.mode != "towerdefense":
            squad_room_id = None
        else:
            members = SquadMember.query.filter_by(room_id=squad_room_id).all()
            combined_roster = []
            for m in members:
                keys = json.loads(m.character_keys_json)
                owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=m.user_id).all()}
                for key in keys:
                    if key in owned:
                        info = ch.stats_at_level(key, owned[key])
                        info["owner"] = m.user.username
                        combined_roster.append(info)
            from squad import difficulty_scale
            mode = request.args.get("mode", "normal")
            if mode not in ("normal", "raid", "lastboss"):
                mode = "normal"  # スクワッドではエンドレスは選べない
            squad_info = {
                "room_id": squad_room_id, "is_host": room_obj.host_id == current_user.id,
                "difficulty": difficulty_scale(len(members)), "member_count": len(members),
                "roster": combined_roster, "mode": mode,
            }

    if squad_info:
        roster = squad_info["roster"]
    else:
        owned_rows = UserCharacter.query.filter_by(user_id=current_user.id).all()
        roster = []
        for row in owned_rows:
            info = ch.stats_at_level(row.character_key, row.count)
            if info:
                info["count"] = row.count
                roster.append(info)
        roster.sort(key=lambda c: (-["common", "rare", "epic", "legendary", "ultimate"].index(c["rarity"]), -c["attack"]))

    recent_runs = (
        TowerDefenseRun.query.filter_by(user_id=current_user.id)
        .order_by(TowerDefenseRun.created_at.desc()).limit(5).all()
    )

    return render_template(
        "towerdefense.html", roster=roster, modes=TD_MODES, current_mode=mode, max_team_size=MAX_TEAM_SIZE,
        recent_runs=recent_runs, squad_info=squad_info
    )


@towerdefense_bp.route("/towerdefense/complete", methods=["POST"])
@login_required
def complete():
    data = request.get_json(force=True)
    mode = data.get("mode", "normal")
    if mode not in TD_MODES:
        return jsonify({"error": "モードの指定が不正です。"}), 400
    cfg = TD_MODES[mode]

    try:
        waves_cleared = int(data.get("waves_cleared", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "結果データが不正です。"}), 400

    used_keys = data.get("characters_used") or []
    if not isinstance(used_keys, list):
        return jsonify({"error": "使用キャラクターの情報が不正です。"}), 400

    # 実際に所持しているキャラクターだけが使われたかを検証する(不正防止)
    owned_keys = {c.character_key for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    if not all(k in owned_keys for k in used_keys) or len(used_keys) > MAX_TEAM_SIZE:
        return jsonify({"error": "使用キャラクターの検証に失敗しました。"}), 400

    waves_cleared = max(0, waves_cleared)
    if cfg["waves"] is not None:
        waves_cleared = min(cfg["waves"], waves_cleared)
    victory = cfg["waves"] is not None and waves_cleared >= cfg["waves"]

    reward_waves = min(waves_cleared, ENDLESS_REWARD_CAP_WAVES)
    reward = reward_waves * cfg["reward_per_wave"]
    if victory:
        reward += cfg["victory_bonus"]

    current_user.balance += reward
    total_label = f"/{cfg['waves']}" if cfg["waves"] is not None else ""
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="towerdefense",
        description=f"タワーディフェンス({cfg['label']}・{waves_cleared}{total_label}ウェーブ)"
    ))
    db.session.add(TowerDefenseRun(
        user_id=current_user.id, waves_cleared=waves_cleared, victory=victory, reward=reward,
        characters_used=json.dumps(used_keys)
    ))
    db.session.commit()

    rank_message = None
    try:
        from seasons import award_season_points, record_endless_score
        award_season_points(current_user, reward)
        if mode == "endless":
            record_endless_score(current_user, "towerdefense", waves_cleared)
            rank_message = "エンドレスランキングに記録しました"
    except Exception:
        pass

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({
        "reward": reward, "victory": victory, "balance": current_user.balance, "rank_message": rank_message
    })
