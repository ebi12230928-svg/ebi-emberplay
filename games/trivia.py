"""カジノ要素とは無関係のミニゲーム。クイズに正解するとEmbersを直接獲得できる(賭け金なし)。"""
import random

from flask import render_template, request, jsonify, session
from flask_login import login_required, current_user

from extensions import db
from models import Transaction
from . import games_bp

REWARD = 80

# 固定の一般常識問題(15問)に加えて、下の generate_random_question() でほぼ無限に問題を生成する
STATIC_QUESTIONS = [
    ("世界で一番面積が大きい国は?", ["ロシア", "カナダ", "中国", "アメリカ"], 0),
    ("1年は何日?(うるう年を除く)", ["364日", "365日", "366日", "360日"], 1),
    ("水の化学式は?", ["CO2", "O2", "H2O", "NaCl"], 2),
    ("日本の首都は?", ["大阪", "京都", "東京", "名古屋"], 2),
    ("人体で一番大きい臓器は?", ["肝臓", "皮膚", "脳", "心臓"], 1),
    ("虹は一般的に何色とされる?", ["5色", "6色", "7色", "8色"], 2),
    ("将棋で最初に動かせない駒は?", ["歩", "王将", "飛車", "香車"], 1),
    ("1ダースはいくつ?", ["10", "12", "15", "20"], 1),
    ("地球から一番近い惑星は?(条件による)", ["火星", "金星", "水星", "木星"], 1),
    ("1キロメートルは何メートル?", ["100m", "1000m", "10000m", "10m"], 1),
    ("フランスの首都は?", ["ロンドン", "ベルリン", "パリ", "ローマ"], 2),
    ("三角形の内角の和は?", ["90度", "180度", "270度", "360度"], 1),
    ("人間の心臓の心房の数は?", ["1", "2", "3", "4"], 3),
    ("チェスでポーンが最初に動けるマス数(最大)は?", ["1マス", "2マス", "3マス", "4マス"], 1),
    ("光の速さはおよそ秒速何km?", ["3万km", "30万km", "300万km", "3千km"], 1),
]


def _shuffle_choices(choices, correct_value):
    """選択肢をシャッフルし、正解のインデックスを再計算する"""
    order = list(range(len(choices)))
    random.shuffle(order)
    shuffled = [choices[i] for i in order]
    correct_idx = shuffled.index(correct_value)
    return shuffled, correct_idx


def _gen_arithmetic():
    op = random.choice(["+", "-", "×", "÷"])
    if op == "+":
        a, b = random.randint(2, 98), random.randint(2, 98)
        answer = a + b
        text = f"{a} + {b} = ?"
    elif op == "-":
        a = random.randint(10, 99)
        b = random.randint(1, a)
        answer = a - b
        text = f"{a} - {b} = ?"
    elif op == "×":
        a, b = random.randint(2, 12), random.randint(2, 12)
        answer = a * b
        text = f"{a} × {b} = ?"
    else:
        b = random.randint(2, 12)
        answer = random.randint(2, 12)
        a = answer * b
        text = f"{a} ÷ {b} = ?"

    wrong = set()
    while len(wrong) < 3:
        delta = random.choice([-2, -1, 1, 2, 3, -3])
        candidate = answer + delta
        if candidate != answer and candidate >= 0:
            wrong.add(candidate)
    choices = [str(answer)] + [str(w) for w in wrong]
    shuffled, idx = _shuffle_choices(choices, str(answer))
    return text, shuffled, idx


def _gen_comparison():
    nums = random.sample(range(1, 1000), 4)
    if random.random() < 0.5:
        text = "次のうち、一番大きい数字はどれ?"
        answer = max(nums)
    else:
        text = "次のうち、一番小さい数字はどれ?"
        answer = min(nums)
    choices = [str(n) for n in nums]
    idx = choices.index(str(answer))
    return text, choices, idx


def _gen_sequence():
    start = random.randint(1, 20)
    step = random.randint(2, 9)
    seq = [start + step * i for i in range(4)]
    answer = start + step * 4
    text = f"{', '.join(map(str, seq))}, ? の「?」に入る数字は?"
    wrong = {answer + step, answer - step, answer + 1}
    wrong.discard(answer)
    choices = [str(answer)] + [str(w) for w in list(wrong)[:3]]
    while len(choices) < 4:
        choices.append(str(answer + random.randint(2, 5)))
    shuffled, idx = _shuffle_choices(choices, str(answer))
    return text, shuffled, idx


def _gen_percentage():
    base = random.choice([50, 100, 200, 400, 500, 1000])
    pct = random.choice([10, 20, 25, 50, 75])
    answer = round(base * pct / 100)
    text = f"{base} の {pct}% はいくつ?"
    wrong = set()
    while len(wrong) < 3:
        delta = random.choice([-20, -10, 10, 20, 30])
        candidate = answer + delta
        if candidate != answer and candidate > 0:
            wrong.add(candidate)
    choices = [str(answer)] + [str(w) for w in wrong]
    shuffled, idx = _shuffle_choices(choices, str(answer))
    return text, shuffled, idx


def _gen_unit_conversion():
    templates = [
        ("km", "m", 1000), ("m", "cm", 100), ("kg", "g", 1000), ("L", "mL", 1000), ("時間", "分", 60),
    ]
    unit_from, unit_to, factor = random.choice(templates)
    value = random.randint(2, 20)
    answer = value * factor
    text = f"{value}{unit_from} は何{unit_to}?"
    wrong = set()
    while len(wrong) < 3:
        delta = random.choice([-factor, factor, factor * 2, -factor // 2 if factor >= 2 else 1])
        candidate = answer + delta
        if candidate != answer and candidate > 0:
            wrong.add(candidate)
    choices = [f"{answer}{unit_to}"] + [f"{w}{unit_to}" for w in wrong]
    shuffled, idx = _shuffle_choices(choices, f"{answer}{unit_to}")
    return text, shuffled, idx


RANDOM_GENERATORS = [_gen_arithmetic, _gen_comparison, _gen_sequence, _gen_percentage, _gen_unit_conversion]


def generate_random_question():
    """固定問題(15問)とランダム生成問題(5種類のテンプレートからほぼ無限に生成)をあわせて出題する"""
    if random.random() < 0.35:
        question, choices, correct = random.choice(STATIC_QUESTIONS)
        return question, choices, correct
    generator = random.choice(RANDOM_GENERATORS)
    return generator()


@games_bp.route("/trivia")
@login_required
def trivia_page():
    return render_template("games/trivia.html", reward=REWARD)


@games_bp.route("/trivia/question", methods=["POST"])
@login_required
def trivia_question():
    question, choices, correct = generate_random_question()
    session["trivia_question"] = question
    session["trivia_choices"] = choices
    session["trivia_correct"] = correct
    return jsonify({"question": question, "choices": choices})


@games_bp.route("/trivia/answer", methods=["POST"])
@login_required
def trivia_answer():
    data = request.get_json(force=True)
    try:
        choice = int(data.get("choice"))
    except (TypeError, ValueError):
        return jsonify({"error": "回答が不正です。"}), 400

    choices = session.pop("trivia_choices", None)
    correct = session.pop("trivia_correct", None)
    session.pop("trivia_question", None)
    if choices is None or correct is None:
        return jsonify({"error": "出題情報が見つかりません。もう一度出題してください。"}), 400

    is_correct = choice == correct

    reward = 0
    if is_correct:
        reward = REWARD
        current_user.balance += reward
        db.session.add(Transaction(
            user_id=current_user.id, amount=reward, kind="trivia", description="クイズ正解"
        ))
        db.session.commit()
        try:
            from achievements import check_achievements
            check_achievements(current_user)
        except Exception:
            pass

    return jsonify({
        "correct": is_correct, "correct_answer": choices[correct], "reward": reward, "balance": current_user.balance
    })
