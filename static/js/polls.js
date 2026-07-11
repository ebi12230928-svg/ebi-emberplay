(function () {
  document.querySelectorAll(".poll-card").forEach((card) => {
    const pollId = card.dataset.pollId;
    card.querySelectorAll(".vote-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        card.querySelectorAll(".vote-btn").forEach((b) => (b.disabled = true));
        try {
          const data = await EmberPlay.postJSON(`/polls/${pollId}/vote`, {
            option_index: parseInt(btn.dataset.option, 10),
          });
          if (data.reward > 0) {
            EmberPlay.updateBalance(data.balance, "win");
          }
          location.reload();
        } catch (err) {
          alert(err.message);
          card.querySelectorAll(".vote-btn").forEach((b) => (b.disabled = false));
        }
      });
    });
  });
})();
