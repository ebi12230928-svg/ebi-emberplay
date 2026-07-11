"""カジノ要素とは無関係のミニゲーム。クイズに正解するとEmbersを直接獲得できる(賭け金なし)。"""
import random

from flask import render_template, request, jsonify, session
from flask_login import login_required, current_user

from extensions import db
from models import Transaction
from . import games_bp

REWARD = 80

QUESTIONS = [
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
    ("人間の心臓は何気筒?という冗談があるが、実際の心房の数は?", ["1", "2", "3", "4"], 3),
    ("チェスで最初に動けるポーンのマス数(最大)は?", ["1マス", "2マス", "3マス", "4マス"], 1),
    ("光の速さはおよそ秒速何km?", ["3万km", "30万km", "300万km", "3千km"], 1),
]


@games_bp.route("/trivia")
@login_required
def trivia_page():
    return render_template("games/trivia.html", reward=REWARD)


@games_bp.route("/trivia/question", methods=["POST"])
@login_required
def trivia_question():
    idx = random.randrange(len(QUESTIONS))
    question, choices, _correct = QUESTIONS[idx]
    session["trivia_idx"] = idx
    return jsonify({"question": question, "choices": choices})


@games_bp.route("/trivia/answer", methods=["POST"])
@login_required
def trivia_answer():
    data = request.get_json(force=True)
    try:
        choice = int(data.get("choice"))
    except (TypeError, ValueError):
        return jsonify({"error": "回答が不正です。"}), 400

    idx = session.pop("trivia_idx", None)
    if idx is None or not (0 <= idx < len(QUESTIONS)):
        return jsonify({"error": "出題情報が見つかりません。もう一度出題してください。"}), 400

    _question, choices, correct = QUESTIONS[idx]
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
