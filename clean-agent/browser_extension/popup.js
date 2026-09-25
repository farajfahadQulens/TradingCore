const status = document.getElementById("status")
const button = document.getElementById("send")

function allowed(url) {
  const parsed = new URL(url)
  return parsed.protocol === "https:" && (
    parsed.hostname === "bi.instructure.com" ||
    parsed.hostname === "bi.no" ||
    parsed.hostname.endsWith(".bi.no")
  )
}

button.addEventListener("click", async () => {
  button.disabled = true
  status.textContent = "Reading visible page..."
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.url || !allowed(tab.url)) throw new Error("Open a BI Canvas or BI student-portal page first.")

    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        content: document.body?.innerText?.slice(0, 50000) || "",
        headings: [...document.querySelectorAll("h1, h2, h3")].map((node) => node.innerText.trim()).filter(Boolean).slice(0, 100),
      }),
    })

    const response = await fetch("http://127.0.0.1:8091/api/browser/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "browser-extension",
        url: tab.url,
        title: tab.title || "",
        content: result.content,
        metadata: { headings: result.headings },
      }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || "Agent rejected the page")
    status.textContent = "Page sent to Clean Agent."
  } catch (error) {
    status.textContent = error.message
  } finally {
    button.disabled = false
  }
})
