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
from models import UserCharacter, Transaction, SquadRoom, SquadMember, PlayerSpell
import characters as ch

rpgboss_bp = Blueprint("rpgboss", __name__)

# 実際に数百〜1000回のシミュレーションで検証したうえで決めた数値(README参照)。
# レイド・ラスボスはユーザーの要望により大幅強化(ラスボスは単騎最強キャラでも油断できない強さ)
TIERS = {
    "normal":   {"label": "通常ボス", "hp": 1550, "atk": 45, "reward_mult": 1.0},
    "raid":     {"label": "レイド", "hp": 6975, "atk": 72, "reward_mult": 3.2},
    "lastboss": {"label": "ラスボス", "hp": 17050, "atk": 126, "reward_mult": 6.5},
}

# ボスを倒すと確率で入手できる魔法(スペル)。戦闘中に⚔️通常攻撃の代わりにボタンで使用できる
SPELLS = {
    "fireball":   {"name": "ファイアボール", "icon": "🔥", "damage_mult": 1.6, "effect": "burn", "effect_label": "継続ダメージ"},
    "poison_dart": {"name": "ポイズンダート", "icon": "☠️", "damage_mult": 1.3, "effect": "poison", "effect_label": "継続ダメージ(毒)"},
    "ice_shard":  {"name": "アイスシャード", "icon": "❄️", "damage_mult": 1.4, "effect": "chill", "effect_label": "ボスの攻撃を一時的に弱める"},
    "thunderbolt": {"name": "サンダーボルト", "icon": "⚡", "damage_mult": 2.0, "effect": None, "effect_label": "純粋な大ダメージ"},
    "heal_light": {"name": "ヒーリングライト", "icon": "💚", "damage_mult": 0, "effect": "heal", "effect_label": "チームを回復"},
    "dark_curse": {"name": "ダークカース", "icon": "🌑", "damage_mult": 1.5, "effect": "curse", "effect_label": "ボスの防御を下げる"},
}
SPELL_COOLDOWN_TURNS = 3  # 1つの魔法を使ったら、再度使えるまでのターン数
SPELL_LOOT_CHANCE = 0.35  # ボス撃破時に魔法をドロップする確率
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


def _run_endless(team_stats, admin_mult=1.0):
    """エンドレスモード: 倒すたびに次のボスが少しずつ強くなる。全滅するまでの記録を1つのログにまとめて返す"""
    team_max_hp = TEAM_HP_PER_CHARACTER * max(1, len(team_stats))
    team_hp = team_max_hp
    combined_log = []
    bosses_beaten = 0
    turn_offset = 0

    for n in range(1, ENDLESS_MAX_BOSSES + 1):
        boss_hp = round(ENDLESS_BASE_HP * (1 + ENDLESS_HP_GROWTH * (n - 1)) * admin_mult)
        boss_atk = round(ENDLESS_BASE_ATK * (1 + ENDLESS_ATK_GROWTH * (n - 1)) * (admin_mult ** 0.5))
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


@rpgboss_bp.route("/rpgboss/battle/start", methods=["POST"])
@login_required
def battle_start():
    """ボタン式バトルの開始。ボス・チームの最大HPなど、初期状態を返す"""
    data = request.get_json(force=True)
    keys = data.get("characters") or []
    mode = data.get("mode", "normal")

    if not isinstance(keys, list) or not keys:
        return jsonify({"error": "キャラクターを1体以上選んでください。"}), 400
    if len(keys) > MAX_TEAM_SOLO:
        return jsonify({"error": f"選べるキャラクターは最大{MAX_TEAM_SOLO}体までです。"}), 400
    if mode not in TIERS:
        return jsonify({"error": "モードの指定が不正です。"}), 400

    owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    if not all(k in owned for k in keys):
        return jsonify({"error": "所持していないキャラクターが含まれています。"}), 400

    from towerdefense import get_enemy_tier, enemy_tier_multiplier
    admin_mult = enemy_tier_multiplier(get_enemy_tier())
    tier = TIERS[mode]
    boss_max_hp = round(tier["hp"] * admin_mult)
    boss_atk = round(tier["atk"] * (admin_mult ** 0.5))
    team_max_hp = TEAM_HP_PER_CHARACTER * len(keys)

    my_spells = {s.spell_key: s.count for s in PlayerSpell.query.filter_by(user_id=current_user.id).all()}
    spell_list = [
        {**SPELLS[k], "key": k, "count": v} for k, v in my_spells.items() if k in SPELLS and v > 0
    ]

    return jsonify({
        "boss_max_hp": boss_max_hp, "boss_atk": boss_atk, "team_max_hp": team_max_hp,
        "boss_label": tier["label"], "spells": spell_list,
    })


@rpgboss_bp.route("/rpgboss/turn", methods=["POST"])
@login_required
def battle_turn():
    """ボタン式バトルの1ターン分を解決する(通常攻撃 or 魔法)"""
    data = request.get_json(force=True)
    keys = data.get("characters") or []
    mode = data.get("mode", "normal")
    action = data.get("action", "attack")  # "attack" または spellのkey
    try:
        boss_hp = float(data.get("boss_hp"))
        team_hp = float(data.get("team_hp"))
        boss_atk = float(data.get("boss_atk"))
        team_max_hp = float(data.get("team_max_hp"))
    except (TypeError, ValueError):
        return jsonify({"error": "戦闘状態が不正です。"}), 400

    if mode not in TIERS:
        return jsonify({"error": "モードの指定が不正です。"}), 400

    owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    if not all(k in owned for k in keys):
        return jsonify({"error": "所持していないキャラクターが含まれています。"}), 400
    team_stats = _team_stats_for(keys, owned)
    if not team_stats:
        return jsonify({"error": "有効なキャラクターがいません。"}), 400

    used_spell = None
    if action != "attack":
        spell_row = PlayerSpell.query.filter_by(user_id=current_user.id, spell_key=action).first()
        if not spell_row or spell_row.count <= 0 or action not in SPELLS:
            return jsonify({"error": "その魔法は所持していません。"}), 400
        used_spell = SPELLS[action]

    # ダメージ計算(通常攻撃はチーム全体の攻撃力合計、魔法は倍率をかけて追加効果も発生させる)
    base_damage = sum(m["attack"] for m in team_stats)
    is_crit = random.random() < 0.15
    team_damage = base_damage * (1.8 if is_crit else 1.0)
    heal_amount = 0
    effect_text = ""

    if used_spell:
        team_damage = base_damage * used_spell["damage_mult"] * (1.8 if is_crit else 1.0)
        if used_spell["effect"] == "heal":
            heal_amount = round(team_max_hp * 0.3)
            team_damage = 0
        elif used_spell["effect"] == "chill":
            boss_atk = round(boss_atk * 0.5)  # このターンのボス攻撃力を弱める
            effect_text = "ボスの攻撃力を弱めた!"
        elif used_spell["effect"] == "curse":
            team_damage = round(team_damage * 1.2)  # 防御破壊(このターンの追加ダメージとして表現)
            effect_text = "ボスの防御を下げ、追加ダメージ!"
        elif used_spell["effect"] in ("burn", "poison"):
            effect_text = "継続ダメージの炎/毒を付与!"

    team_damage = round(team_damage)
    new_boss_hp = max(0, boss_hp - team_damage)
    new_team_hp = min(team_max_hp, team_hp + heal_amount)

    boss_damage = 0
    if new_boss_hp > 0:
        boss_damage = round(boss_atk * (0.7 + random.random() * 0.6))
        new_team_hp = max(0, new_team_hp - boss_damage)

    if used_spell:
        spell_row.count -= 1
        db.session.commit()

    return jsonify({
        "team_damage": team_damage, "boss_damage": boss_damage, "crit": is_crit,
        "heal_amount": heal_amount, "effect_text": effect_text,
        "new_boss_hp": new_boss_hp, "new_team_hp": new_team_hp,
        "spell_used": action if used_spell else None,
    })


@rpgboss_bp.route("/rpgboss/manual-complete", methods=["POST"])
@login_required
def manual_complete():
    """ボタン式バトルの結果を報告し、報酬付与+勝利時は確率で魔法をドロップする"""
    data = request.get_json(force=True)
    mode = data.get("mode", "normal")
    victory = bool(data.get("victory"))
    try:
        turns = max(0, int(data.get("turns", 0)))
    except (TypeError, ValueError):
        turns = 0

    if mode not in TIERS:
        return jsonify({"error": "モードの指定が不正です。"}), 400
    tier = TIERS[mode]

    reward = round(turns * REWARD_PER_TURN_SURVIVED * tier["reward_mult"])
    if victory:
        reward += round(VICTORY_BONUS * tier["reward_mult"])

    from games.common import credit_reward
    credit_reward(current_user, reward)
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="rpgboss",
        description=f"RPGボス討伐({tier['label']}・ボタン式)" + ("(勝利)" if victory else "")
    ))

    looted_spell = None
    if victory and random.random() < SPELL_LOOT_CHANCE:
        spell_key = random.choice(list(SPELLS.keys()))
        row = PlayerSpell.query.filter_by(user_id=current_user.id, spell_key=spell_key).first()
        if row:
            row.count += 1
        else:
            db.session.add(PlayerSpell(user_id=current_user.id, spell_key=spell_key, count=1))
        looted_spell = {**SPELLS[spell_key], "key": spell_key}

    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({"reward": reward, "balance": current_user.balance, "looted_spell": looted_spell})


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
        from towerdefense import get_enemy_tier, enemy_tier_multiplier
        result = _run_endless(team_stats, admin_mult=enemy_tier_multiplier(get_enemy_tier()))
        reward = result["bosses_beaten"] * ENDLESS_REWARD_PER_BOSS
        from games.common import credit_reward
        credit_reward(current_user, reward)
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
    from towerdefense import get_enemy_tier, enemy_tier_multiplier
    admin_mult = enemy_tier_multiplier(get_enemy_tier())
    # HPはそのまま倍率を反映、攻撃力は平方根で緩やかに(全滅即死のような理不尽な難易度にならないようにする)
    boss_hp = round(tier["hp"] * admin_mult)
    boss_atk = round(tier["atk"] * (admin_mult ** 0.5))
    result = _run_battle(team_stats, boss_hp, boss_atk)

    reward = round(result["turns"] * REWARD_PER_TURN_SURVIVED * tier["reward_mult"])
    if result["victory"]:
        reward += round(VICTORY_BONUS * tier["reward_mult"])

    from games.common import credit_reward
    credit_reward(current_user, reward)
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
    from towerdefense import get_enemy_tier, enemy_tier_multiplier
    admin_mult = enemy_tier_multiplier(get_enemy_tier())
    boss_hp = round(tier["hp"] * admin_mult)
    boss_atk = round(tier["atk"] * (admin_mult ** 0.5))
    result = _run_battle(combined_team, boss_hp, boss_atk)

    reward_each = round(
        (result["turns"] * REWARD_PER_TURN_SURVIVED + (VICTORY_BONUS if result["victory"] else 0)) * tier["reward_mult"]
    )
    for m in members:
        from games.common import credit_reward
        credit_reward(m.user, reward_each)
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
