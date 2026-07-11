"""
RPGボス討伐モード。選んだキャラクター編成でボスに挑む、ターン制の自動バトル。
ソロでも、スクワッド(フレンドとの協力プレイ)でも遊べる。
「通常ボス」「レイド」「ラスボス」の3段階の強さと、「エンドレスモード」がある。
"""
import json
import random

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import UserCharacter, Transaction, SquadRoom, SquadMember
import characters as ch

rpgboss_bp = Blueprint("rpgboss", __name__)

# 実際に数百〜1000回のシミュレーションで検証したうえで決めた数値(README参照)。
# レイド・ラスボスはユーザーの要望により大幅強化(ラスボスは単騎最強キャラでも油断できない強さ)
TIERS = {
    "normal":   {"label": "通常ボス", "hp": 1550, "atk": 45, "reward_mult": 1.0},
    "raid":     {"label": "レイド", "hp": 6975, "atk": 72, "reward_mult": 3.2},
    "lastboss": {"label": "ラスボス", "hp": 17050, "atk": 126, "reward_mult": 6.5},
}
ENDLESS_BASE_HP = 1550
ENDLESS_BASE_ATK = 45
ENDLESS_HP_GROWTH = 0.35   # 1体倒すごとにHPが+35%
ENDLESS_ATK_GROWTH = 0.12  # 1体倒すごとに攻撃力が+12%
ENDLESS_HEAL_RATIO = 0.4   # ボスを倒すたびにチームHPを最大値の40%回復
ENDLESS_MAX_BOSSES = 25    # 際限なく計算し続けないための安全な上限

TEAM_HP_PER_CHARACTER = 120
MAX_TURNS = 40
REWARD_PER_TURN_SURVIVED = 15
REWARD_PER_TURN = 15  # squad.pyから参照される名前(同じ意味)
VICTORY_BONUS = 500
ENDLESS_REWARD_PER_BOSS = 220
CRIT_CHANCE = 0.2
CRIT_MULTIPLIER = 2.0
MISS_CHANCE = 0.08
MAX_TEAM_SOLO = 6  # ソロプレイで選べるキャラクター数の上限(タワーディフェンスと同じ)


def _fight_one_boss(team_stats, boss_hp, boss_atk, team_hp, team_max_hp):
    """1体のボスとの戦闘を1回分だけ解決する(エンドレスモードでの使い回し用)。アビリティ効果も反映する"""
    from collections import Counter
    ability_counts = Counter()
    for member in team_stats:
        for a in member.get("abilities", []):
            ability_counts[a] += 1

    crit_chance = min(0.7, CRIT_CHANCE + ability_counts["crit_boost"] * 0.05)
    dot_bonus = 1 + ability_counts["poison"] * 0.05 + ability_counts["fire"] * 0.05
    armor_break_bonus = 1 + ability_counts["armor_break"] * 0.08
    lifesteal_ratio = ability_counts["lifesteal"] * 0.04
    stun_chance = min(0.6, ability_counts["stun"] * 0.08)
    regen_flat = ability_counts["regen"] * 15

    log = []
    turn = 0
    boss_max_hp = boss_hp
    while boss_hp > 0 and team_hp > 0 and turn < MAX_TURNS:
        turn += 1
        team_damage = 0
        crit = False
        for member in team_stats:
            r = random.random()
            if r < MISS_CHANCE:
                continue
            elif r < MISS_CHANCE + crit_chance:
                team_damage += round(member["attack"] * CRIT_MULTIPLIER)
                crit = True
            else:
                team_damage += member["attack"]
        team_damage = round(team_damage * dot_bonus * armor_break_bonus)
        boss_hp = max(0, boss_hp - team_damage)

        if lifesteal_ratio > 0:
            team_hp = min(team_max_hp, team_hp + team_damage * lifesteal_ratio)
        if regen_flat > 0:
            team_hp = min(team_max_hp, team_hp + regen_flat)

        boss_damage = 0
        if boss_hp > 0 and random.random() >= stun_chance:  # stunアビリティでボスの攻撃を無効化することがある
            boss_damage = round(boss_atk * (0.7 + random.random() * 0.6))
            team_hp = max(0, team_hp - boss_damage)

        log.append({
            "turn": turn, "team_damage": team_damage, "crit": crit,
            "boss_hp": boss_hp, "boss_max_hp": boss_max_hp,
            "boss_damage": boss_damage, "team_hp": team_hp, "team_max_hp": team_max_hp,
        })

    return {"log": log, "victory": boss_hp <= 0, "turns": turn, "final_team_hp": team_hp}


def _run_battle(team_stats, boss_hp, boss_atk):
    """team_stats: [{name, icon, attack}, ...] のリスト。1体のボスと戦い、ターンごとのログを返す"""
    team_hp = TEAM_HP_PER_CHARACTER * max(1, len(team_stats))
    result = _fight_one_boss(team_stats, boss_hp, boss_atk, team_hp, team_hp)
    return {
        "log": result["log"], "victory": result["victory"], "turns": result["turns"],
        "boss_max_hp": boss_hp, "team_max_hp": team_hp,
    }


def _run_endless(team_stats):
    """エンドレスモード: 倒すたびに次のボスが少しずつ強くなる。全滅するまでの記録を1つのログにまとめて返す"""
    team_max_hp = TEAM_HP_PER_CHARACTER * max(1, len(team_stats))
    team_hp = team_max_hp
    combined_log = []
    bosses_beaten = 0
    turn_offset = 0

    for n in range(1, ENDLESS_MAX_BOSSES + 1):
        boss_hp = round(ENDLESS_BASE_HP * (1 + ENDLESS_HP_GROWTH * (n - 1)))
        boss_atk = round(ENDLESS_BASE_ATK * (1 + ENDLESS_ATK_GROWTH * (n - 1)))
        result = _fight_one_boss(team_stats, boss_hp, boss_atk, team_hp, team_max_hp)

        for entry in result["log"]:
            entry = dict(entry)
            entry["turn"] += turn_offset
            entry["boss_number"] = n
            combined_log.append(entry)
        turn_offset += result["turns"]
        team_hp = result["final_team_hp"]

        if result["victory"]:
            bosses_beaten += 1
            team_hp = min(team_max_hp, team_hp + team_max_hp * ENDLESS_HEAL_RATIO)
        else:
            break

    return {
        "log": combined_log, "bosses_beaten": bosses_beaten, "team_max_hp": team_max_hp,
        "reached_cap": bosses_beaten >= ENDLESS_MAX_BOSSES,
    }


def _team_stats_for(character_keys, owner_lookup):
    """character_keys: [key,...], owner_lookup: key -> UserCharacter.count(レベル) の辞書"""
    team = []
    for key in character_keys:
        level = owner_lookup.get(key, 1)
        info = ch.stats_at_level(key, level)
        if info:
            team.append(info)
    return team


@rpgboss_bp.route("/rpgboss")
@login_required
def index():
    owned_rows = UserCharacter.query.filter_by(user_id=current_user.id).all()
    roster = []
    for row in owned_rows:
        info = ch.stats_at_level(row.character_key, row.count)
        if info:
            info["count"] = row.count
            roster.append(info)
    roster.sort(key=lambda c: (-ch.RARITY_ORDER.index(c["rarity"]), -c["attack"]))

    return render_template(
        "rpgboss.html", roster=roster, tiers=TIERS, max_turns=MAX_TURNS, max_team=MAX_TEAM_SOLO
    )


@rpgboss_bp.route("/rpgboss/battle", methods=["POST"])
@login_required
def battle():
    data = request.get_json(force=True)
    keys = data.get("characters") or []
    mode = data.get("mode", "normal")

    if not isinstance(keys, list) or not keys:
        return jsonify({"error": "キャラクターを1体以上選んでください。"}), 400
    if len(keys) > MAX_TEAM_SOLO:
        return jsonify({"error": f"選べるキャラクターは最大{MAX_TEAM_SOLO}体までです。"}), 400

    owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    if not all(k in owned for k in keys):
        return jsonify({"error": "所持していないキャラクターが含まれています。"}), 400

    team_stats = _team_stats_for(keys, owned)

    if mode == "endless":
        result = _run_endless(team_stats)
        reward = result["bosses_beaten"] * ENDLESS_REWARD_PER_BOSS
        current_user.balance += reward
        db.session.add(Transaction(
            user_id=current_user.id, amount=reward, kind="rpgboss_endless",
            description=f"エンドレスモード({result['bosses_beaten']}体撃破)"
        ))
        db.session.commit()
        try:
            from seasons import award_season_points, record_endless_score
            award_season_points(current_user, reward)
            record_endless_score(current_user, "rpgboss", result["bosses_beaten"])
        except Exception:
            pass
        try:
            from achievements import check_achievements
            check_achievements(current_user)
        except Exception:
            pass
        return jsonify({**result, "mode": mode, "reward": reward, "balance": current_user.balance})

    if mode not in TIERS:
        return jsonify({"error": "モードの指定が不正です。"}), 400

    tier = TIERS[mode]
    result = _run_battle(team_stats, tier["hp"], tier["atk"])

    reward = round(result["turns"] * REWARD_PER_TURN_SURVIVED * tier["reward_mult"])
    if result["victory"]:
        reward += round(VICTORY_BONUS * tier["reward_mult"])

    current_user.balance += reward
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="rpgboss",
        description=f"RPGボス討伐({tier['label']})" + ("(勝利)" if result["victory"] else "")
    ))
    db.session.commit()

    try:
        from seasons import award_season_points
        award_season_points(current_user, reward)
    except Exception:
        pass

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({**result, "mode": mode, "reward": reward, "balance": current_user.balance})


@rpgboss_bp.route("/rpgboss/squad-battle", methods=["POST"])
@login_required
def squad_battle():
    """
    スクワッド(協力プレイ)でのボス討伐。ホストのみ実行でき、結果は参加者全員に報酬として配られる。
    通常ボス/レイド/ラスボスから選べる(エンドレスモードはソロ専用)。
    """
    data = request.get_json(force=True)
    room_id = data.get("room_id")
    mode = data.get("mode", "normal")
    if mode not in TIERS:
        return jsonify({"error": "モードの指定が不正です。"}), 400

    room_obj = SquadRoom.query.get(room_id) if room_id else None
    if not room_obj or room_obj.host_id != current_user.id or room_obj.status != "battling":
        return jsonify({"error": "この部屋ではボス討伐を開始できません。"}), 400

    members = SquadMember.query.filter_by(room_id=room_id).all()
    from squad import difficulty_scale
    difficulty = difficulty_scale(len(members))

    combined_team = []
    for m in members:
        keys = json.loads(m.character_keys_json)
        owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=m.user_id).all()}
        combined_team.extend(_team_stats_for(keys, owned))

    if not combined_team:
        return jsonify({"error": "誰もキャラクターを選択していません。"}), 400

    tier = TIERS[mode]
    result = _run_battle(combined_team, tier["hp"], tier["atk"])

    reward_each = round(
        (result["turns"] * REWARD_PER_TURN_SURVIVED + (VICTORY_BONUS if result["victory"] else 0)) * tier["reward_mult"]
    )
    for m in members:
        m.user.balance += reward_each
        db.session.add(Transaction(
            user_id=m.user_id, amount=reward_each, kind="squad_rpgboss",
            description=f"協力ボス討伐({tier['label']}・{len(members)}人)の報酬"
        ))

    room_obj.status = "finished"
    room_obj.result_json = json.dumps({"victory": result["victory"], "turns": result["turns"], "mode": mode})
    db.session.commit()

    try:
        from achievements import check_achievements
        for m in members:
            check_achievements(m.user)
    except Exception:
        pass

    return jsonify({**result, "mode": mode, "reward_each": reward_each, "member_count": len(members)})
