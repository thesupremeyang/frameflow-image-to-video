(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const form = $("generation-form");
  const input = $("image-input");
  const dropzone = $("dropzone");
  const submit = $("submit-button");
  let selectedModel = "seedance-2.5";
  let currentId = null;
  let jobs = [];
  let previewUrl = null;
  let pollTimer = null;
  let submitting = false;
  let specs = {};
  let appConfig = null;
  const configFields = ["ark_base_url", "minimax_base_url", "seedance_25_model", "seedance_20_model", "minimax_model", "s3_endpoint_url", "s3_region", "s3_bucket", "s3_public_base_url", "s3_prefix"];
  const configInputs = { ark_base_url: "ark-base-url", minimax_base_url: "minimax-base-url", seedance_25_model: "seedance-25-model", seedance_20_model: "seedance-20-model", minimax_model: "minimax-model", s3_endpoint_url: "s3-endpoint-url", s3_region: "s3-region", s3_bucket: "s3-bucket", s3_public_base_url: "s3-public-base-url", s3_prefix: "s3-prefix" };
  const statusLabels = { queued: "排队中", running: "生成中", succeeded: "已完成", failed: "未成功" };

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = `请求失败（HTTP ${response.status}）`;
      try { message = (await response.json()).detail || message; } catch (_) { /* Non-JSON proxy error. */ }
      throw new Error(message);
    }
    return response.json();
  }

  function toast(message) {
    $("toast").textContent = message;
    $("toast").hidden = false;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => { $("toast").hidden = true; }, 5000);
  }

  function showError(message) {
    $("form-error").textContent = message;
    $("form-error").hidden = false;
  }

  function clearErrors() {
    $("form-error").hidden = true;
    $("image-error").hidden = true;
  }

  function updateModel() {
    const previousModel = selectedModel;
    selectedModel = new FormData(form).get("model");
    document.querySelectorAll(".model-option").forEach((option) => {
      option.classList.toggle("selected", option.querySelector("input").checked);
    });
    const spec = specs[selectedModel];
    if (!spec) return;
    const oldDuration = Number($("duration").value) || 5;
    const [min, max] = spec.durations;
    $("duration").replaceChildren();
    for (let value = min; value <= max; value++) {
      $("duration").add(new Option(`${value}`, value));
    }
    $("duration").value = String(Math.min(max, Math.max(min, oldDuration)));
    const resolution = $("resolution").value;
    $("resolution").replaceChildren();
    spec.resolutions.forEach((value) => $("resolution").add(new Option(value, value)));
    $("resolution").value = spec.resolutions.includes(resolution) ? resolution : spec.default_resolution;
    $("audio-row").hidden = !spec.audio;
    if (previousModel !== selectedModel && !currentId) setStage("empty");
    updateOutputSpec();
    updateConfigurationUI();
  }

  function updateConfigurationUI() {
    if (!appConfig || !specs[selectedModel]) return;
    const ready = selectedModel === "minimax-h3" ? appConfig.ready.minimax : appConfig.ready.ark;
    const notice = $("config-notice");
    notice.textContent = ready
      ? `${specs[selectedModel].provider}已配置，可以直接生成。`
      : selectedModel === "minimax-h3"
        ? "MiniMax H3 尚未就绪，请配置 MiniMax API Key 和 S3 图片存储。"
        : "Seedance 尚未就绪，请配置火山方舟 API Key。";
    $("config-notice-button").hidden = ready;
    $("config-indicator").classList.toggle("configured", Boolean(appConfig.ready.ark && appConfig.ready.minimax));
  }

  function markSecret(configured, id, placeholder) {
    const state = $(id);
    state.textContent = configured ? "已配置" : "未配置";
    state.classList.toggle("configured", configured);
    const input = state.closest(".config-field").querySelector("input");
    input.placeholder = configured ? "已保存，留空则不修改" : placeholder;
  }

  function fillConfiguration() {
    if (!appConfig) return;
    const config = appConfig.configuration;
    configFields.forEach((name) => { $(configInputs[name]).value = (config.fields && config.fields[name]) || ""; });
    ["ark-api-key", "minimax-api-key", "s3-access-key-id", "s3-secret-access-key"].forEach((id) => { $(id).value = ""; });
    markSecret(config.ark_api_key_configured, "ark-key-state", "输入火山方舟 API Key");
    markSecret(config.minimax_api_key_configured, "minimax-key-state", "输入 MiniMax API Key");
    markSecret(Boolean(config.fields.s3_access_key_configured), "s3-access-state", "输入存储访问密钥");
    markSecret(Boolean(config.fields.s3_secret_configured), "s3-secret-state", "输入存储私密密钥");
    $("config-file-error").hidden = !config.config_file_error;
    $("config-file-error").textContent = config.config_file_error || "";
  }

  function openConfiguration() {
    if (!appConfig) {
      toast("本地配置尚未加载，请稍后重试。");
      return;
    }
    $("config-error").hidden = true;
    fillConfiguration();
    $("config-dialog").showModal();
  }

  async function saveConfiguration(event) {
    event.preventDefault();
    const button = $("save-config");
    const errorBox = $("config-error");
    errorBox.hidden = true;
    const data = new FormData($("config-form"));
    const payload = Object.fromEntries(data.entries());
    button.disabled = true;
    button.firstElementChild.textContent = "保存中…";
    try {
      appConfig = await request("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      $("config-dialog").close();
      updateConfigurationUI();
      toast("模型配置已保存并生效。");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    } finally {
      button.disabled = false;
      button.firstElementChild.textContent = "保存配置";
    }
  }

  function updateOutputSpec() {
    const spec = specs[selectedModel];
    if (!spec) return;
    $("output-model").textContent = spec.name;
    $("output-spec").textContent = `${$("duration").value} 秒 · ${$("resolution").value}`;
  }

  function selectFile(file) {
    clearErrors();
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) {
      input.value = "";
      $("image-error").textContent = "图片不能超过 30 MB。";
      $("image-error").hidden = false;
      return;
    }
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    const preview = $("image-preview");
    preview.src = previewUrl;
    preview.hidden = false;
    dropzone.classList.add("has-image");
    document.querySelectorAll(".upload-symbol,.upload-title,.upload-help").forEach((element) => { element.hidden = true; });
    const size = file.size < 1024 * 1024 ? `${Math.round(file.size / 1024)} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`;
    $("image-meta").textContent = `${file.name} · ${size}`;
    $("image-meta").hidden = false;
    preview.onerror = () => {
      preview.hidden = true;
      $("image-error").textContent = "浏览器无法预览此图片。可尝试 JPG、PNG 或 WEBP，服务端仍会验证实际格式。";
      $("image-error").hidden = false;
    };
  }

  function setStage(stage, job = null) {
    ["empty", "processing", "success", "failed"].forEach((name) => {
      $(`output-${name}`).hidden = name !== stage;
    });
    $("output-stage").className = `output-stage ${stage}`;
    const badge = $("output-status");
    if (!job) {
      badge.textContent = "等待创作";
      badge.className = "status-badge idle";
      return;
    }
    badge.textContent = statusLabels[job.status] || job.status;
    badge.className = `status-badge ${job.status === "succeeded" ? "succeeded" : job.status === "failed" ? "failed" : "processing"}`;
    if (job.status === "queued" || job.status === "running") {
      $("processing-image").src = job.image_url;
      $("processing-state").textContent = job.status === "queued" ? "任务已进入云端队列" : "云端正在生成视频";
      $("step-cloud").classList.toggle("complete", job.status === "running");
    } else if (job.status === "succeeded") {
      if ($("result-video").dataset.job !== job.id) {
        $("result-video").src = job.video_url;
        $("result-video").dataset.job = job.id;
      }
      $("result-meta").textContent = `${job.model_name} · ${job.duration} 秒 · ${job.resolution}`;
      $("download-button").href = job.download_url;
    } else if (job.status === "failed") {
      $("output-error").textContent = job.error || "云端未能完成视频生成，请调整参数后重试。";
    }
  }

  function renderJob(job) {
    currentId = job.id;
    $("output-model").textContent = job.model_name;
    $("output-spec").textContent = `${job.duration} 秒 · ${job.resolution}`;
    if (job.status === "succeeded") setStage("success", job);
    else if (job.status === "failed") setStage("failed", job);
    else setStage("processing", job);
    renderHistory();
    schedulePolling();
  }

  function renderHistory() {
    const list = $("history-list");
    list.replaceChildren();
    $("history-empty").hidden = jobs.length > 0;
    $("clear-history").hidden = jobs.length === 0;
    jobs.forEach((job) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `history-card${job.id === currentId ? " active" : ""}`;
      card.setAttribute("aria-label", `查看 ${job.model_name} 的创作，${statusLabels[job.status]}`);
      const thumb = document.createElement("div");
      thumb.className = "history-thumb";
      const img = document.createElement("img");
      img.src = job.image_url;
      img.alt = "";
      img.loading = "lazy";
      const status = document.createElement("span");
      status.className = "history-status";
      status.textContent = statusLabels[job.status];
      thumb.append(img, status);
      const info = document.createElement("div");
      info.className = "history-info";
      const title = document.createElement("strong");
      title.textContent = job.model_name;
      const prompt = document.createElement("p");
      prompt.textContent = job.prompt;
      info.append(title, prompt);
      card.append(thumb, info);
      card.addEventListener("click", () => renderJob(job));
      list.append(card);
    });
  }

  async function refreshJobs() {
    try {
      jobs = await request("/api/generations");
      const current = jobs.find((job) => job.id === currentId);
      if (current) renderJob(current);
      else renderHistory();
    } catch (error) {
      if (!jobs.length) toast(`无法读取本地记录：${error.message}`);
    } finally {
      schedulePolling();
    }
  }

  function schedulePolling() {
    window.clearTimeout(pollTimer);
    if (jobs.some((job) => ["queued", "running"].includes(job.status))) {
      pollTimer = window.setTimeout(refreshJobs, 2500);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) return;
    clearErrors();
    updateModel();
    if (!input.files.length) {
      $("image-error").textContent = "请先选择一张首帧图片。";
      $("image-error").hidden = false;
      input.focus();
      return;
    }
    if (!$("prompt").value.trim()) {
      showError("请填写视频生成提示词。");
      $("prompt").focus();
      return;
    }
    submitting = true;
    submit.disabled = true;
    submit.firstElementChild.textContent = "正在提交…";
    const data = new FormData(form);
    data.set("generate_audio", $("generate-audio").checked && specs[selectedModel].audio);
    try {
      const job = await request("/api/generations", { method: "POST", body: data });
      jobs = [job, ...jobs.filter((item) => item.id !== job.id)];
      renderJob(job);
      if (window.innerWidth < 768) $("output-status").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
      showError(error.message);
    } finally {
      submitting = false;
      submit.disabled = false;
      submit.firstElementChild.textContent = "开始生成视频";
    }
  });

  input.addEventListener("change", () => selectFile(input.files[0]));
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.remove("dragover");
  }));
  dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));
  document.querySelectorAll('input[name="model"]').forEach((radio) => radio.addEventListener("change", updateModel));
  $("duration").addEventListener("change", updateOutputSpec);
  $("resolution").addEventListener("change", updateOutputSpec);
  $("prompt").addEventListener("input", () => { $("prompt-count").textContent = `${$("prompt").value.length} / 10000`; });
  $("retry-button").addEventListener("click", () => {
    setStage("empty");
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    $("prompt").focus();
  });
  $("clear-history").addEventListener("click", () => $("clear-dialog").showModal());
  $("open-config").addEventListener("click", openConfiguration);
  $("config-notice-button").addEventListener("click", openConfiguration);
  $("close-config").addEventListener("click", () => $("config-dialog").close());
  $("cancel-config").addEventListener("click", () => $("config-dialog").close());
  $("config-form").addEventListener("submit", saveConfiguration);
  $("cancel-clear").addEventListener("click", () => $("clear-dialog").close());
  $("confirm-clear").addEventListener("click", async () => {
    $("confirm-clear").disabled = true;
    try {
      await request("/api/generations", { method: "DELETE" });
      window.clearTimeout(pollTimer);
      jobs = []; currentId = null;
      $("result-video").pause();
      $("result-video").removeAttribute("src");
      $("result-video").dataset.job = "";
      $("result-video").load();
      renderHistory(); setStage("empty"); updateOutputSpec();
      $("clear-dialog").close();
      toast("本地创作记录已清空。");
    } catch (error) { toast(error.message); }
    finally { $("confirm-clear").disabled = false; }
  });
  $("download-button").addEventListener("click", async (event) => {
    const url = event.currentTarget.href;
    event.preventDefault();
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "视频下载失败。");
      }
      const blob = await response.blob();
      const link = document.createElement("a");
      const objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl;
      link.download = `frameflow-${currentId.slice(0, 8)}.mp4`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    } catch (error) { toast(error.message); }
  });

  async function initialize() {
    try {
      appConfig = await request("/api/config");
      specs = appConfig.models;
      updateModel();
      updateConfigurationUI();
      await refreshJobs();
    } catch (error) {
      showError(`无法连接本地服务：${error.message}`);
      submit.disabled = true;
    }
  }
  initialize();
})();
