const form = document.getElementById("download-form");
const urlInput = document.getElementById("url-input");
const extensionSelect = document.getElementById("extension-select");
const qualityField = document.getElementById("quality-field");
const qualitySelect = document.getElementById("quality-select");
const filenameInput = document.getElementById("filename-input");
const submitBtn = document.getElementById("submit-btn");
const spinner = document.getElementById("spinner");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const downloadLink = document.getElementById("download-link");
const expiresInEl = document.getElementById("expires-in");
const objectKeyEl = document.getElementById("object-key");

const apiUrl = window.APP_CONFIG?.apiUrl;

const VIDEO_EXTENSIONS = new Set(["mp4", "webm"]);
const FILENAME_PATTERN = /^[A-Za-z0-9_-]*$/;

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.classList.toggle("loading", loading);
  spinner.classList.toggle("hidden", !loading);
  urlInput.disabled = loading;
  extensionSelect.disabled = loading;
  qualitySelect.disabled = loading;
  filenameInput.disabled = loading;
}

function isVideoExtension(ext) {
  return VIDEO_EXTENSIONS.has(ext.toLowerCase());
}

function updateQualityVisibility() {
  const showQuality = isVideoExtension(extensionSelect.value);
  qualityField.hidden = !showQuality;
}

function sanitizeFilename(value) {
  return value.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 200);
}

function validateUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function buildRequestBody() {
  const body = {
    url: urlInput.value.trim(),
    extension: extensionSelect.value,
  };

  const filename = sanitizeFilename(filenameInput.value.trim());
  if (filename) {
    body.filename = filename;
  }

  if (isVideoExtension(extensionSelect.value)) {
    body.quality = qualitySelect.value;
  }

  return body;
}

function displayFilename(data) {
  if (data.filename) {
    return data.filename;
  }
  const key = data.key ?? "";
  const basename = key.split("/").pop();
  return basename || "download";
}

extensionSelect.addEventListener("change", updateQualityVisibility);

filenameInput.addEventListener("input", () => {
  const sanitized = sanitizeFilename(filenameInput.value);
  if (filenameInput.value !== sanitized) {
    filenameInput.value = sanitized;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resultEl.classList.add("hidden");

  if (!apiUrl || apiUrl.includes("YOUR_API_ID")) {
    setStatus("config.js の apiUrl を設定してください。", true);
    return;
  }

  const url = urlInput.value.trim();
  if (!url) {
    setStatus("URL を入力してください。", true);
    urlInput.focus();
    return;
  }

  if (!validateUrl(url)) {
    setStatus("有効な http:// または https:// の URL を入力してください。", true);
    urlInput.focus();
    return;
  }

  const filename = sanitizeFilename(filenameInput.value.trim());
  if (filenameInput.value.trim() && !filename) {
    setStatus("ファイル名は英数字・ハイフン・アンダースコアのみ使用できます。", true);
    filenameInput.focus();
    return;
  }

  if (filename && !FILENAME_PATTERN.test(filename)) {
    setStatus("ファイル名は英数字・ハイフン・アンダースコアのみ使用できます。", true);
    filenameInput.focus();
    return;
  }

  const body = buildRequestBody();
  setLoading(true);
  setStatus("ダウンロードとアップロードを実行しています。しばらくお待ちください…");

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }

    const label = displayFilename(data);
    downloadLink.href = data.presigned_url;
    downloadLink.textContent = `${label} をダウンロード`;
    downloadLink.setAttribute("download", label);
    expiresInEl.textContent = String(data.expires_in ?? "");
    objectKeyEl.textContent = data.key ?? "";
    resultEl.classList.remove("hidden");
    setStatus("ダウンロードリンクを取得しました。");
  } catch (err) {
    setStatus(err.message || "リクエストに失敗しました。", true);
  } finally {
    setLoading(false);
  }
});

updateQualityVisibility();
