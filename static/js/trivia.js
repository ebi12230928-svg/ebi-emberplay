(function () {
  const nextBtn = document.getElementById("next-btn");
  const questionArea = document.getElementById("question-area");
  const questionText = document.getElementById("question-text");
  const choicesEl = document.getElementById("choices");
  const resultReadout = document.getElementById("result-readout");

  async function loadQuestion() {
    resultReadout.textContent = "";
    nextBtn.disabled = true;
    try {
      const data = await EmberPlay.postJSON("/games/trivia/question", {});
      questionText.textContent = data.question;
      choicesEl.innerHTML = "";
      data.choices.forEach((choice, i) => {
        const btn = document.createElement("button");
        btn.className = "btn btn-ghost";
        btn.textContent = choice;
        btn.addEventListener("click", () => answer(i, btn));
        choicesEl.appendChild(btn);
      });
      questionArea.style.display = "block";
    } catch (err) {
      alert(err.message);
    } finally {
      nextBtn.disabled = false;
    }
  }

  async function answer(choice, btn) {
    Array.from(choicesEl.children).forEach((b) => (b.disabled = true));
    try {
      const data = await EmberPlay.postJSON("/games/trivia/answer", { choice });
      if (data.correct) {
        resultReadout.textContent = `正解! ・ +${data.reward}`;
        EmberPlay.flashResult(resultReadout, true, false);
        EmberPlay.updateBalance(data.balance, "win");
      } else {
        resultReadout.textContent = `不正解(正解は「${data.correct_answer}」)`;
        EmberPlay.flashResult(resultReadout, false, true);
      }
    } catch (err) {
      alert(err.message);
    }
  }

  nextBtn.addEventListener("click", loadQuestion);
})();
