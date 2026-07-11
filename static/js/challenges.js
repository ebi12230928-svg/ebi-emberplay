(function () {
  document.querySelectorAll(".claim-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const data = await EmberPlay.postJSON(`/challenges/claim/${btn.dataset.key}`, {});
        EmberPlay.updateBalance(data.balance, "win");
        btn.textContent = "受け取り済み";
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
})();
