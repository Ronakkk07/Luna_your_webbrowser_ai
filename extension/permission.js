// Standalone page whose only job is to obtain microphone permission for the
// extension origin. The prompt reliably appears here (unlike in a side panel),
// and once granted the side panel's Web Speech recognition can use the mic.

const btn = document.getElementById("grantBtn");
const result = document.getElementById("result");

btn.onclick = async () => {
  result.textContent = "Requesting…";
  result.className = "";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // We only needed the permission grant; release the mic right away.
    stream.getTracks().forEach((track) => track.stop());
    result.textContent = "Microphone enabled. You can close this tab and talk to Luna.";
    result.className = "ok";
  } catch (err) {
    result.textContent =
      "Access was blocked. Click the mic/site icon in the address bar, allow the " +
      "microphone, then try again.";
    result.className = "err";
    console.error("getUserMedia failed:", err);
  }
};
