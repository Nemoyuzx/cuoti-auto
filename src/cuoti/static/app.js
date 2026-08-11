document.addEventListener("DOMContentLoaded", () => {
  const renderMath = (root = document) => {
    if (!window.renderMathInElement) return;
    const elements = [];
    if (root.matches?.(".math-content")) elements.push(root);
    elements.push(...root.querySelectorAll(".math-content"));
    elements.forEach((element) => {
      window.renderMathInElement(element, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false }
        ],
        throwOnError: false,
        strict: false
      });
    });
  };
  renderMath();

  document.querySelectorAll("[data-preview-source]").forEach((source) => {
    const output = document.querySelector(`[data-preview-output="${source.dataset.previewSource}"]`);
    if (!output) return;
    let timer;
    let controller;
    source.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(async () => {
        controller?.abort();
        controller = new AbortController();
        output.closest(".live-preview")?.classList.add("is-updating");
        try {
          const response = await fetch("/api/render-preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              kind: source.dataset.previewKind || "richtext",
              value: source.value
            }),
            signal: controller.signal
          });
          if (!response.ok) throw new Error(`preview ${response.status}`);
          const payload = await response.json();
          output.innerHTML = payload.html || '<span class="preview-empty">暂无内容</span>';
          renderMath(output);
        } catch (error) {
          if (error.name !== "AbortError") {
            output.innerHTML = '<span class="preview-error">预览暂时无法更新，输入内容仍会保留。</span>';
          }
        } finally {
          output.closest(".live-preview")?.classList.remove("is-updating");
        }
      }, 140);
    });
  });

  const imageStage = document.querySelector("[data-image-stage]");
  if (imageStage) {
    let rotation = 0;
    const images = [...imageStage.querySelectorAll("[data-review-image]")];
    const applyRotation = () => {
      images.forEach((item) => item.style.setProperty("--manual-rotation", `${rotation}deg`));
    };
    document.querySelectorAll("[data-image-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.imageAction;
        if (action === "left") rotation -= 90;
        if (action === "right") rotation += 90;
        if (action === "fit") imageStage.classList.toggle("is-fit");
        applyRotation();
      });
    });
  }

  const exportPanel = document.querySelector("[data-export-panel]");
  if (exportPanel) {
    const filterForm = document.querySelector("[data-filter-form]");
    const jobsRoot = exportPanel.querySelector("[data-export-jobs]");
    const idleBadge = exportPanel.querySelector(".export-idle");
    const trigger = exportPanel.querySelector("[data-export-toggle]");
    const popover = exportPanel.querySelector("[data-export-popover]");
    const subject = exportPanel.dataset.subject || "";
    const storageKey = `cuoti-export-jobs-${subject}`;
    const activePolls = new Set();

    const readJobIds = () => {
      try { return JSON.parse(localStorage.getItem(storageKey) || "[]"); }
      catch { return []; }
    };
    const writeJobIds = (ids) => localStorage.setItem(storageKey, JSON.stringify(ids.slice(0, 12)));
    const rememberJob = (id) => writeJobIds([id, ...readJobIds().filter((item) => item !== id)]);
    const forgetJob = (id) => writeJobIds(readJobIds().filter((item) => item !== id));

    const setPopoverOpen = (open) => {
      popover.hidden = !open;
      trigger.setAttribute("aria-expanded", String(open));
    };
    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      setPopoverOpen(popover.hidden);
    });
    document.addEventListener("click", (event) => {
      if (!popover.hidden && !exportPanel.contains(event.target)) setPopoverOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !popover.hidden) {
        setPopoverOpen(false);
        trigger.focus();
      }
    });

    const updateTriggerState = () => {
      const jobs = [...jobsRoot.querySelectorAll(".export-job")];
      const hasActive = jobs.some((item) => item.classList.contains("queued") || item.classList.contains("running"));
      const hasReady = !hasActive && jobs.some((item) => item.classList.contains("ready"));
      trigger.classList.toggle("has-active", hasActive);
      trigger.classList.toggle("has-ready", hasReady);
      idleBadge.textContent = hasActive ? "处理中" : "就绪";
      idleBadge.classList.toggle("active", hasActive);
    };

    const jobElement = (job) => {
      let element = jobsRoot.querySelector(`[data-export-job="${job.id}"]`);
      if (!element) {
        element = document.createElement("article");
        element.className = "export-job";
        element.dataset.exportJob = job.id;
        element.innerHTML = `
          <div class="export-job-top">
            <span class="export-ring" aria-hidden="true">
              <svg viewBox="0 0 44 44"><circle class="export-ring-track" cx="22" cy="22" r="18" pathLength="100"></circle><circle class="export-ring-value" cx="22" cy="22" r="18" pathLength="100"></circle></svg>
              <span class="export-percent"></span><span class="export-ring-check">✓</span>
            </span>
            <span class="export-job-copy"><span class="export-job-title"></span><span class="export-job-state"></span><span class="export-job-message"></span></span>
          </div>
          <div class="export-job-foot"><span>后台任务</span><span class="export-result"></span></div>`;
        jobsRoot.prepend(element);
      }
      return element;
    };

    const renderJob = (job) => {
      const empty = jobsRoot.querySelector("[data-export-empty]");
      if (empty) empty.remove();
      const element = jobElement(job);
      const stateLabels = { queued: "排队中", running: "生成中", ready: "已完成", error: "失败" };
      element.className = `export-job ${job.state}`;
      element.querySelector(".export-job-title").textContent = job.variant_label;
      element.querySelector(".export-job-state").textContent = stateLabels[job.state] || job.state;
      element.querySelector(".export-job-message").textContent = job.error || job.message;
      element.querySelector(".export-job-message").classList.toggle("export-error", job.state === "error");
      element.querySelector(".export-ring").style.setProperty("--progress", `${job.progress || 0}`);
      element.querySelector(".export-percent").textContent = `${job.progress || 0}%`;
      const result = element.querySelector(".export-result");
      result.replaceChildren();
      if (job.state === "ready" && job.download_url) {
        const link = document.createElement("a");
        link.className = "export-download";
        link.href = job.download_url;
        link.textContent = "下载 PDF";
        result.append(link);
      }
      updateTriggerState();
    };

    const pollJob = async (id) => {
      if (activePolls.has(id)) return;
      activePolls.add(id);
      const poll = async () => {
        try {
          const response = await fetch(`/api/exports/${id}`, { cache: "no-store" });
          if (response.status === 404) {
            forgetJob(id);
            activePolls.delete(id);
            return;
          }
          const job = await response.json();
          renderJob(job);
          if (["ready", "error"].includes(job.state)) {
            activePolls.delete(id);
            return;
          }
        } catch {
          // A short server restart should not discard the visible task.
        }
        window.setTimeout(poll, 700);
      };
      await poll();
    };

    exportPanel.querySelectorAll("[data-export-variant]").forEach((button) => {
      button.addEventListener("click", async () => {
        const formData = new FormData(filterForm);
        formData.set("subject", subject);
        formData.set("variant", button.dataset.exportVariant);
        button.disabled = true;
        try {
          const response = await fetch("/api/exports", { method: "POST", body: formData });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.detail || "无法创建导出任务");
          rememberJob(payload.id);
          renderJob(payload);
          setPopoverOpen(true);
          pollJob(payload.id);
        } catch (error) {
          window.alert(error.message);
        } finally {
          button.disabled = false;
        }
      });
    });

    readJobIds().forEach(pollJob);
  }

  document.querySelectorAll("[data-confirm-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      const confirmed = window.confirm(
        "确认删除本题？它会从错题库、Markdown 和后续 PDF 中移除；系统会保留可恢复备份。"
      );
      if (!confirmed) event.preventDefault();
    });
  });
});
