(function () {
  document.querySelectorAll(".claim-tier-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const data = await EmberPlay.postJSON(`/seasons/pass/claim/${btn.dataset.tier}`, {});
        alert(data.message);
        if (data.balance !== undefined) EmberPlay.updateBalance(data.balance, "win");
        location.reload();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
})();
