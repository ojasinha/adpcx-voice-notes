(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const HTML_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  const STATUS_ORDER = ["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"];
  const STATUS_META = {
    PENDING: { label: "Pending", className: "pending" },
    IN_PROGRESS: { label: "In progress", className: "progress" },
    COMPLETED: { label: "Completed", className: "completed" },
    CANCELLED: { label: "Cancelled", className: "cancelled" },
  };
  const PRIORITY_ORDER = { URGENT: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  const PRIORITY_META = {
    URGENT: { label: "Urgent", className: "urgent" },
    HIGH: { label: "High", className: "high" },
    MEDIUM: { label: "Medium", className: "medium" },
    LOW: { label: "Low", className: "low" },
  };
  const INTENT_META = {
    CREATE_TASK: { label: "Task created", className: "intent-create" },
    UPDATE_TASK_STATUS: { label: "Status updated", className: "intent-update" },
    QUERY_TASKS: { label: "Tasks queried", className: "intent-query" },
    GENERAL_NOTE: { label: "Note saved", className: "intent-note" },
  };
  const VIEW_META = {
    overview: { title: "Overview", eyebrow: "Workspace" },
    tasks: { title: "Tasks", eyebrow: "Workspace" },
    notes: { title: "Notes", eyebrow: "Workspace" },
  };
  const MAX_RECORD_SECONDS = 120;

  const icons = {
    mic: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 11.5v.5a6.5 6.5 0 0 0 13 0v-.5M12 18.5V21M8.5 21h7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    text: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.6"/><path d="M7 10h2M11 10h2M15 10h2M7 14h2M11 14h2M15 14h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4.5 7h15M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7M7 7l.7 12a1.5 1.5 0 0 0 1.5 1.4h5.6a1.5 1.5 0 0 0 1.5-1.4L17 7M10 11v5M14 11v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`,
    calendar: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="5.5" width="16" height="15" rx="2.5" stroke="currentColor" stroke-width="1.7"/><path d="M8 3.5v4M16 3.5v4M4 10h16" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`,
    close: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>`,
    alert: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 8v5M12 16.5v.1M10.3 3.8 2.4 18a1.6 1.6 0 0 0 1.4 2.4h16.4a1.6 1.6 0 0 0 1.4-2.4L13.7 3.8a1.9 1.9 0 0 0-3.4 0Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`,
    info: `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 11v5M12 8v.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  };

  const state = {
    view: "overview",
    tasks: [],
    tasksTotal: 0,
    notes: [],
    notesTotal: 0,
    notesOffset: 0,
    notesLimit: 30,
    notesLoading: false,
    taskFilter: "ALL",
    taskQuery: "",
    noteSource: "ALL",
    refreshing: false,
    loaded: false,
    recording: null,
    processing: false,
    processingTimer: null,
    processingStartedAt: 0,
    pendingDeleteId: null,
    highlightTaskId: null,
    updatingTasks: new Set(),
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => HTML_ESCAPES[character]);
  }

  function setText(selector, value) {
    const node = $(selector);
    if (node) {
      node.textContent = String(value);
    }
  }

  function pluralize(count, singular, plural = `${singular}s`) {
    return count === 1 ? singular : plural;
  }

  function formatDuration(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function formatRelative(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    const difference = Date.now() - date.getTime();
    if (difference < 0) {
      return formatDate(value);
    }
    if (difference < 60_000) {
      return "Just now";
    }
    if (difference < 3_600_000) {
      return `${Math.floor(difference / 60_000)}m ago`;
    }
    if (difference < 86_400_000) {
      return `${Math.floor(difference / 3_600_000)}h ago`;
    }
    if (difference < 604_800_000) {
      return `${Math.floor(difference / 86_400_000)}d ago`;
    }
    return formatDate(value);
  }

  function startOfToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function parseDateOnly(value) {
    const [year, month, day] = String(value).split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function dueInfo(value) {
    if (!value) {
      return { label: "", className: "" };
    }
    const due = parseDateOnly(value);
    if (Number.isNaN(due.getTime())) {
      return { label: "", className: "" };
    }
    const today = startOfToday();
    const difference = Math.round((due.getTime() - today.getTime()) / 86_400_000);
    let label;
    if (difference === 0) {
      label = "Today";
    } else if (difference === 1) {
      label = "Tomorrow";
    } else if (difference === -1) {
      label = "Yesterday";
    } else if (difference < 0) {
      label = `Overdue ${Math.abs(difference)}d`;
    } else {
      label = due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
    return {
      label,
      className: difference < 0 ? "is-overdue" : difference === 0 ? "is-today" : "",
    };
  }

  function statusMeta(status) {
    return STATUS_META[status] || { label: status || "Unknown", className: "pending" };
  }

  function priorityMeta(priority) {
    return PRIORITY_META[priority] || { label: "No priority", className: "low" };
  }

  function intentMeta(intent) {
    return INTENT_META[intent] || { label: "Note", className: "intent-note" };
  }

  function statusPill(status) {
    const meta = statusMeta(status);
    return `<span class="status-pill status-${meta.className}">${meta.label}</span>`;
  }

  function statusOptions(current) {
    return STATUS_ORDER.map((status) => {
      const meta = statusMeta(status);
      return `<option value="${status}"${status === current ? " selected" : ""}>${meta.label}</option>`;
    }).join("");
  }

  function compareTasks(left, right) {
    const statusLeft = STATUS_ORDER.indexOf(left.status);
    const statusRight = STATUS_ORDER.indexOf(right.status);
    if (statusLeft !== statusRight) {
      return statusLeft - statusRight;
    }
    const dueLeft = left.due_date || "9999-12-31";
    const dueRight = right.due_date || "9999-12-31";
    if (dueLeft !== dueRight) {
      return dueLeft < dueRight ? -1 : 1;
    }
    const priorityLeft = PRIORITY_ORDER[left.priority] ?? 4;
    const priorityRight = PRIORITY_ORDER[right.priority] ?? 4;
    if (priorityLeft !== priorityRight) {
      return priorityLeft - priorityRight;
    }
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  }

  function focusCompare(left, right) {
    const dueLeft = left.due_date || "9999-12-31";
    const dueRight = right.due_date || "9999-12-31";
    if (dueLeft !== dueRight) {
      return dueLeft < dueRight ? -1 : 1;
    }
    return (PRIORITY_ORDER[left.priority] ?? 4) - (PRIORITY_ORDER[right.priority] ?? 4);
  }

  function taskCounts() {
    const counts = {
      ALL: state.tasks.length,
      PENDING: 0,
      IN_PROGRESS: 0,
      COMPLETED: 0,
      CANCELLED: 0,
    };
    for (const task of state.tasks) {
      if (Object.prototype.hasOwnProperty.call(counts, task.status)) {
        counts[task.status] += 1;
      }
    }
    return counts;
  }

  async function api(path, options = {}) {
    const { method = "GET", body } = options;
    const request = { method, headers: {} };
    if (body instanceof FormData) {
      request.body = body;
    } else if (body !== undefined) {
      request.headers["Content-Type"] = "application/json";
      request.body = JSON.stringify(body);
    }
    const response = await fetch(path, request);
    let payload = null;
    if (response.status !== 204) {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        payload = await response.json().catch(() => null);
      } else {
        payload = await response.text().catch(() => "");
      }
    }
    if (!response.ok) {
      const message =
        (payload && payload.error && payload.error.message) ||
        (typeof payload === "string" && payload) ||
        `Request failed (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function setApiOnline(online) {
    const banner = $("#offline-banner");
    if (banner) {
      banner.hidden = online;
    }
  }

  async function checkHealth({ announce = false } = {}) {
    try {
      await api("/health");
      setApiOnline(true);
      if (announce) {
        showToast("Backend is reachable.", "success");
      }
      return true;
    } catch {
      setApiOnline(false);
      if (announce) {
        showToast("Backend is still offline. Start the server and retry.", "error");
      }
      return false;
    }
  }

  function setTodayLabel() {
    setText(
      "#today-label",
      new Intl.DateTimeFormat(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      }).format(new Date()),
    );
  }

  function navigate(view, { updateHash = true } = {}) {
    const nextView = VIEW_META[view] ? view : "overview";
    state.view = nextView;
    const meta = VIEW_META[nextView];
    $$("[data-view]").forEach((section) => {
      section.hidden = section.dataset.view !== nextView;
    });
    $$("[data-view-link]").forEach((link) => {
      link.classList.toggle("is-active", link.dataset.viewLink === nextView);
    });
    setText("#view-title", meta.title);
    setText("#view-eyebrow", meta.eyebrow);
    if (updateHash && window.location.hash !== `#${nextView}`) {
      window.history.replaceState(null, "", `#${nextView}`);
    }
    if (nextView !== "overview") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function focusCapture() {
    navigate("overview");
    window.setTimeout(() => {
      const input = $("#note-text");
      if (!input) {
        return;
      }
      input.focus();
      input.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 80);
  }

  function toggleRefresh(active) {
    const button = $("#refresh-btn");
    if (!button) {
      return;
    }
    button.classList.toggle("is-spinning", active);
    button.disabled = active;
  }

  function renderSkeletons() {
    setText("#stat-open", "—");
    setText("#stat-open-sub", "Loading workspace");
    setText("#stat-due", "—");
    setText("#stat-due-sub", "Checking dates");
    setText("#stat-completed", "—");
    setText("#stat-completed-sub", "Reading tasks");
    setText("#stat-notes", "—");
    setText("#stat-notes-sub", "Opening memory");
    setText("#nav-task-count", "0");
    $("#focus-list").innerHTML = `<div class="skeleton skeleton-row"></div>`.repeat(3);
    $("#recent-notes").innerHTML = `<div class="skeleton skeleton-row"></div>`.repeat(3);
    $("#task-list").innerHTML = `<div class="skeleton skeleton-task"></div>`.repeat(3);
    $("#notes-list").innerHTML = `<div class="skeleton skeleton-note"></div>`.repeat(3);
    $("#focus-empty").hidden = true;
    $("#recent-empty").hidden = true;
    $("#task-empty").hidden = true;
    $("#notes-empty").hidden = true;
    $("#notes-load-more").hidden = true;
  }

  function renderLoadError() {
    setText("#stat-open", "—");
    setText("#stat-open-sub", "API unavailable");
    setText("#stat-due", "—");
    setText("#stat-due-sub", "API unavailable");
    setText("#stat-completed", "—");
    setText("#stat-completed-sub", "API unavailable");
    setText("#stat-notes", "—");
    setText("#stat-notes-sub", "API unavailable");
    $("#focus-list").innerHTML = "";
    $("#recent-notes").innerHTML = "";
    $("#task-list").innerHTML = "";
    $("#notes-list").innerHTML = "";
    $("#focus-empty").hidden = false;
    $("#recent-empty").hidden = false;
    $("#task-empty").hidden = false;
    $("#notes-empty").hidden = false;
    $("#notes-load-more").hidden = true;
    setText("#task-empty-title", "Could not load tasks");
    setText("#task-empty-copy", "Start the backend and use Retry above.");
  }

  async function refreshAll({ initial = false } = {}) {
    if (state.refreshing) {
      return;
    }
    state.refreshing = true;
    toggleRefresh(true);
    if (initial) {
      renderSkeletons();
    }
    try {
      const [tasksPage, notesPage] = await Promise.all([
        api("/api/tasks?limit=100&offset=0"),
        api(`/api/notes?limit=${state.notesLimit}&offset=0`),
      ]);
      state.tasks = Array.isArray(tasksPage?.items) ? tasksPage.items : [];
      state.tasksTotal = Number.isFinite(tasksPage?.total) ? tasksPage.total : state.tasks.length;
      state.notes = Array.isArray(notesPage?.items) ? notesPage.items : [];
      state.notesTotal = Number.isFinite(notesPage?.total) ? notesPage.total : state.notes.length;
      state.notesOffset = state.notes.length;
      state.loaded = true;
      setApiOnline(true);
      renderAll();
    } catch (error) {
      setApiOnline(false);
      if (initial) {
        renderLoadError();
      }
      showToast(error?.message || "Could not load the workspace.", "error");
    } finally {
      state.refreshing = false;
      toggleRefresh(false);
    }
  }

  function renderAll() {
    renderStats();
    renderNav();
    renderFocus();
    renderRecentNotes();
    renderTasks();
    renderNotes();
  }

  function renderStats() {
    const counts = taskCounts();
    const openTasks = state.tasks.filter(
      (task) => task.status === "PENDING" || task.status === "IN_PROGRESS",
    );
    const open = counts.PENDING + counts.IN_PROGRESS;
    const highPriority = openTasks.filter(
      (task) => task.priority === "HIGH" || task.priority === "URGENT",
    ).length;
    const today = startOfToday().getTime();
    const dueToday = openTasks.filter(
      (task) => task.due_date && parseDateOnly(task.due_date).getTime() === today,
    ).length;
    const overdue = openTasks.filter(
      (task) => task.due_date && parseDateOnly(task.due_date).getTime() < today,
    ).length;
    const completed = counts.COMPLETED;
    const completionBase = counts.PENDING + counts.IN_PROGRESS + counts.COMPLETED;
    const completionRate = completionBase ? Math.round((completed / completionBase) * 100) : 0;

    setText("#stat-open", open);
    setText(
      "#stat-open-sub",
      highPriority ? `${highPriority} high priority` : open ? "On track" : "All clear",
    );
    setText("#stat-due", dueToday + overdue);
    setText(
      "#stat-due-sub",
      overdue ? `${overdue} overdue` : dueToday ? "Due before midnight" : "Nothing overdue",
    );
    setText("#stat-completed", completed);
    setText(
      "#stat-completed-sub",
      completionBase ? `${completionRate}% completion rate` : "No tasks yet",
    );
    setText("#stat-notes", state.notesTotal);
    setText("#stat-notes-sub", state.notesTotal ? "Voice and text memories" : "No captures yet");
  }

  function renderNav() {
    const open = state.tasks.filter(
      (task) => task.status === "PENDING" || task.status === "IN_PROGRESS",
    ).length;
    setText("#nav-task-count", open);
  }

  function renderFocus() {
    const list = $("#focus-list");
    const empty = $("#focus-empty");
    const openTasks = state.tasks
      .filter((task) => task.status === "PENDING" || task.status === "IN_PROGRESS")
      .sort(focusCompare);
    const focus = openTasks.slice(0, 4);
    if (!focus.length) {
      list.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    list.innerHTML = focus.map(focusRow).join("");
  }

  function focusRow(task) {
    const priority = priorityMeta(task.priority);
    const due = dueInfo(task.due_date);
    return `<div class="focus-row">
      <button class="focus-check" type="button" data-complete-task="${escapeHtml(task.id)}" aria-label="Mark ${escapeHtml(task.title)} complete" title="Mark complete">${icons.check}</button>
      <div class="focus-main">
        <p class="focus-title">${escapeHtml(task.title)}</p>
        <div class="focus-meta">
          <span class="focus-priority priority-${priority.className}">${priority.label}</span>
          ${task.due_date ? `<span class="focus-due ${due.className}">${icons.calendar}${escapeHtml(due.label)}</span>` : ""}
        </div>
      </div>
    </div>`;
  }

  function renderRecentNotes() {
    const list = $("#recent-notes");
    const empty = $("#recent-empty");
    const notes = state.notes.slice(0, 3);
    if (!notes.length) {
      list.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    list.innerHTML = notes.map(recentNote).join("");
  }

  function recentNote(note) {
    const source = String(note.source).toLowerCase() === "voice" ? "voice" : "text";
    const intent = intentMeta(note.intent);
    return `<button class="recent-note" type="button" data-open-note="${escapeHtml(note.id)}">
      <span class="recent-icon is-${source}">${source === "voice" ? icons.mic : icons.text}</span>
      <span class="recent-main">
        <span class="recent-text">${escapeHtml(note.raw_transcript)}</span>
        <span class="recent-meta"><span>${intent.label}</span><span>${formatRelative(note.created_at)}</span></span>
      </span>
    </button>`;
  }

  function renderTasks() {
    renderTaskFilters();
    const query = state.taskQuery.toLowerCase();
    let tasks = state.tasks.slice();
    if (state.taskFilter !== "ALL") {
      tasks = tasks.filter((task) => task.status === state.taskFilter);
    }
    if (query) {
      tasks = tasks.filter((task) =>
        `${task.title} ${task.description || ""}`.toLowerCase().includes(query),
      );
    }
    tasks.sort(compareTasks);

    const list = $("#task-list");
    const empty = $("#task-empty");
    if (!tasks.length) {
      list.innerHTML = "";
      empty.hidden = false;
      setTaskEmptyCopy();
      return;
    }
    empty.hidden = true;
    list.innerHTML = tasks.map(taskCard).join("");
  }

  function renderTaskFilters() {
    const counts = taskCounts();
    $$("[data-filter-count]").forEach((node) => {
      node.textContent = counts[node.dataset.filterCount] ?? 0;
    });
    $$("[data-task-filter]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.taskFilter === state.taskFilter);
    });
  }

  function setTaskEmptyCopy() {
    const title = $("#task-empty-title");
    const copy = $("#task-empty-copy");
    if (!title || !copy) {
      return;
    }
    if (state.taskQuery) {
      title.textContent = "No matches";
      copy.textContent = `Nothing matches "${state.taskQuery}". Try a different search.`;
      return;
    }
    if (state.taskFilter !== "ALL") {
      const label = statusMeta(state.taskFilter).label.toLowerCase();
      title.textContent = `No ${label} tasks`;
      copy.textContent = "Try another filter or capture a new note.";
      return;
    }
    title.textContent = "No tasks here";
    copy.textContent =
      'Record a note like "Remind me to send the update tomorrow" and it will appear here.';
  }

  function taskCard(task) {
    const priority = priorityMeta(task.priority);
    const due = dueInfo(task.due_date);
    const status = statusMeta(task.status);
    const classes = [
      "task-card",
      `priority-${priority.className}`,
      `status-${status.className}`,
    ];
    if (state.highlightTaskId === task.id) {
      classes.push("is-highlighted");
    }
    const description = task.description
      ? `<p class="task-desc">${escapeHtml(task.description)}</p>`
      : "";
    const dueChip = task.due_date
      ? `<span class="due-chip ${due.className}">${icons.calendar}<span>${escapeHtml(due.label)}</span></span>`
      : "";
    const isDone = task.status === "COMPLETED";
    const checkAttrs = isDone ? 'disabled aria-pressed="true"' : 'aria-pressed="false"';
    return `<article class="${classes.join(" ")}">
      <button class="task-check" type="button" data-complete-task="${escapeHtml(task.id)}" aria-label="Mark ${escapeHtml(task.title)} complete" title="Mark complete" ${checkAttrs}>${icons.check}</button>
      <div class="task-content">
        <div class="task-top">
          <h3 class="task-title">${escapeHtml(task.title)}</h3>
          <span class="priority-badge">${priority.label}</span>
        </div>
        ${description}
        <div class="task-meta">
          ${dueChip}
          ${statusPill(task.status)}
          <span class="task-updated">${formatRelative(task.updated_at)}</span>
        </div>
      </div>
      <div class="task-footer">
        <select class="status-select" data-status-task="${escapeHtml(task.id)}" aria-label="Update status for ${escapeHtml(task.title)}">${statusOptions(task.status)}</select>
        <button class="task-delete" type="button" data-delete-task="${escapeHtml(task.id)}" aria-label="Delete ${escapeHtml(task.title)}" title="Delete task">${icons.trash}</button>
      </div>
    </article>`;
  }

  function renderNotes() {
    $$("[data-note-source]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.noteSource === state.noteSource);
    });
    const notes =
      state.noteSource === "ALL"
        ? state.notes
        : state.notes.filter(
            (note) => String(note.source).toUpperCase() === state.noteSource,
          );
    const list = $("#notes-list");
    const empty = $("#notes-empty");
    setNotesEmptyCopy();
    if (!notes.length) {
      list.innerHTML = "";
      empty.hidden = false;
      updateLoadMore();
      return;
    }
    empty.hidden = true;
    list.innerHTML = notes.map(noteCard).join("");
    updateLoadMore();
  }

  function setNotesEmptyCopy() {
    const title = $("#notes-empty h3");
    const copy = $("#notes-empty p");
    if (!title || !copy) {
      return;
    }
    if (state.noteSource === "VOICE") {
      title.textContent = "No voice notes yet";
      copy.textContent = "Tap the microphone on the overview and speak a thought.";
      return;
    }
    if (state.noteSource === "TEXT") {
      title.textContent = "No typed notes yet";
      copy.textContent = "Type a note on the overview and it will appear here.";
      return;
    }
    title.textContent = "No notes yet";
    copy.textContent =
      "Your voice recordings and typed notes will build a searchable memory here.";
  }

  function noteCard(note) {
    const source = String(note.source).toLowerCase() === "voice" ? "voice" : "text";
    const intent = intentMeta(note.intent);
    const linkedTask = state.tasks.find((task) => task.id === note.task_id);
    const linkLabel = linkedTask ? linkedTask.title : note.task_id ? "Linked task" : "";
    return `<article class="note-card source-${source}">
      <div class="note-main">
        <div class="note-head">
          <span class="source-badge ${source === "text" ? "is-text" : ""}">${source === "voice" ? icons.mic : icons.text}${source === "voice" ? "Voice" : "Text"}</span>
          <span class="intent-badge ${intent.className}">${intent.label}</span>
          <time class="note-time" datetime="${escapeHtml(note.created_at)}">${formatRelative(note.created_at)}</time>
        </div>
        <p class="note-text">${escapeHtml(note.raw_transcript)}</p>
        <div class="note-foot">
          <span class="note-link">${linkLabel ? `Linked to <strong>${escapeHtml(linkLabel)}</strong>` : "No linked task"}</span>
          <button class="link-btn" type="button" data-open-note="${escapeHtml(note.id)}">Details</button>
        </div>
        ${note.processing_error ? `<p class="note-error">${escapeHtml(note.processing_error)}</p>` : ""}
      </div>
    </article>`;
  }

  function updateLoadMore() {
    const button = $("#notes-load-more");
    if (!button) {
      return;
    }
    button.hidden = state.notesOffset >= state.notesTotal;
  }

  async function loadMoreNotes() {
    if (state.notesLoading) {
      return;
    }
    state.notesLoading = true;
    const button = $("#notes-load-more");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Loading...";
    try {
      const page = await api(`/api/notes?limit=${state.notesLimit}&offset=${state.notesOffset}`);
      const items = Array.isArray(page?.items) ? page.items : [];
      state.notes = state.notes.concat(items);
      state.notesOffset += items.length;
      if (Number.isFinite(page?.total)) {
        state.notesTotal = page.total;
      }
      if (!items.length) {
        state.notesTotal = state.notesOffset;
      }
      renderNotes();
      renderRecentNotes();
    } catch (error) {
      showToast(error?.message || "Could not load more notes.", "error");
    } finally {
      state.notesLoading = false;
      button.disabled = false;
      button.textContent = label;
      updateLoadMore();
    }
  }

  function openDialog(dialog) {
    if (!dialog || dialog.open) {
      return;
    }
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function closeDialog(dialog) {
    if (!dialog || !dialog.open) {
      return;
    }
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  }

  function showQueryResults(action) {
    const tasks = Array.isArray(action.tasks) ? action.tasks : [];
    const total = Number.isFinite(action.total) ? action.total : tasks.length;
    setText("#query-title", "Tasks found");
    setText(
      "#query-sub",
      total
        ? `${total} matching ${pluralize(total, "task")}`
        : "No tasks matched that query.",
    );
    $("#query-body").innerHTML = tasks.length
      ? tasks.map(dialogTaskRow).join("")
      : `<div class="empty-inline"><span class="empty-icon">${icons.info}</span><div><strong>No matches</strong><span>Try a broader query or check your task board.</span></div></div>`;
    openDialog($("#query-dialog"));
  }

  function dialogTaskRow(task) {
    const priority = priorityMeta(task.priority);
    const due = dueInfo(task.due_date);
    return `<div class="dialog-task">
      <div class="dialog-task-main">
        <p class="dialog-task-title">${escapeHtml(task.title)}</p>
        <div class="dialog-task-meta">
          ${statusPill(task.status)}
          <span class="focus-priority priority-${priority.className}">${priority.label}</span>
          ${task.due_date ? `<span class="due-chip ${due.className}">${icons.calendar}<span>${escapeHtml(due.label)}</span></span>` : ""}
        </div>
      </div>
    </div>`;
  }

  async function openNoteDetail(noteId) {
    const dialog = $("#note-dialog");
    setText("#note-dialog-title", "Loading note");
    setText("#note-dialog-eyebrow", "Note");
    $("#note-dialog-body").innerHTML = `<div class="skeleton skeleton-note"></div>`;
    openDialog(dialog);
    try {
      const note = await api(`/api/notes/${encodeURIComponent(noteId)}`);
      const source = String(note.source).toLowerCase() === "voice" ? "voice" : "text";
      const sourceLabel = source === "voice" ? "Voice" : "Text";
      const intent = intentMeta(note.intent);
      const task = note.task;
      const due = task ? dueInfo(task.due_date) : null;
      const taskBlock = task
        ? `<div class="note-related"><span class="eyebrow">Linked task</span><p>${escapeHtml(task.title)}</p><div class="dialog-task-meta">${statusPill(task.status)}${task.due_date ? `<span class="due-chip ${due.className}">${icons.calendar}<span>${escapeHtml(due.label)}</span></span>` : ""}</div></div>`
        : `<div class="note-related"><span class="eyebrow">Linked task</span><p>No linked task</p></div>`;
      setText("#note-dialog-title", "Transcript");
      setText("#note-dialog-eyebrow", `${sourceLabel} note`);
      $("#note-dialog-body").innerHTML = `<div class="note-dialog-meta">
          <span class="source-badge ${source === "text" ? "is-text" : ""}">${source === "voice" ? icons.mic : icons.text}${sourceLabel}</span>
          <span class="intent-badge ${intent.className}">${intent.label}</span>
          <span class="note-time">${escapeHtml(formatDate(note.created_at))}</span>
        </div>
        <p class="note-transcript">${escapeHtml(note.raw_transcript)}</p>
        ${taskBlock}
        ${note.processing_error ? `<div class="note-error-block"><strong>Processing error</strong><br>${escapeHtml(note.processing_error)}</div>` : ""}`;
    } catch (error) {
      setText("#note-dialog-title", "Note unavailable");
      $("#note-dialog-body").innerHTML = `<div class="note-error-block">${escapeHtml(error?.message || "Could not load this note.")}</div>`;
    }
  }

  function requestDelete(taskId) {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) {
      return;
    }
    state.pendingDeleteId = taskId;
    setText("#delete-copy", `"${task.title}" will be removed. Linked notes are kept.`);
    openDialog($("#delete-dialog"));
  }

  async function confirmDelete() {
    const taskId = state.pendingDeleteId;
    if (!taskId) {
      return;
    }
    const button = $("#confirm-delete");
    button.disabled = true;
    button.textContent = "Deleting...";
    try {
      await api(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      state.tasks = state.tasks.filter((task) => task.id !== taskId);
      state.tasksTotal = Math.max(0, state.tasksTotal - 1);
      state.pendingDeleteId = null;
      renderAll();
      closeDialog($("#delete-dialog"));
      showToast("Task deleted. Linked notes were kept.", "success");
      await refreshAll();
    } catch (error) {
      showToast(error?.message || "Could not delete the task.", "error");
    } finally {
      button.disabled = false;
      button.textContent = "Delete task";
    }
  }

  async function updateTaskStatus(taskId, status) {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task || task.status === status || state.updatingTasks.has(taskId)) {
      return;
    }
    state.updatingTasks.add(taskId);
    const previous = { status: task.status, updated_at: task.updated_at };
    task.status = status;
    task.updated_at = new Date().toISOString();
    renderAll();
    try {
      const updated = await api(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: { status },
      });
      Object.assign(task, updated);
      renderAll();
      showToast(`Task marked ${statusMeta(status).label.toLowerCase()}.`, "success");
    } catch (error) {
      Object.assign(task, previous);
      renderAll();
      showToast(error?.message || "Could not update the task.", "error");
    } finally {
      state.updatingTasks.delete(taskId);
    }
  }

  function setProcessing(active, title = "Working", subtitle = "Please wait.") {
    state.processing = active;
    const panel = $("#processing");
    panel.hidden = !active;
    if (active) {
      setText("#processing-title", title);
      setText("#processing-sub", subtitle);
      state.processingStartedAt = Date.now();
      setText("#processing-elapsed", "0s");
      window.clearInterval(state.processingTimer);
      state.processingTimer = window.setInterval(() => {
        const seconds = Math.floor((Date.now() - state.processingStartedAt) / 1000);
        setText(
          "#processing-elapsed",
          seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`,
        );
      }, 250);
      setCaptureDisabled(true);
    } else {
      window.clearInterval(state.processingTimer);
      state.processingTimer = null;
      setCaptureDisabled(false);
    }
  }

  function setCaptureDisabled(disabled) {
    ["#note-text", "#note-submit", "#record-btn", "#audio-file", "#cancel-record"].forEach(
      (selector) => {
        const node = $(selector);
        if (node) {
          node.disabled = disabled;
        }
      },
    );
  }

  function setRecordingUI(active) {
    const button = $("#record-btn");
    button.classList.toggle("is-recording", active);
    button.setAttribute("aria-label", active ? "Stop recording" : "Start recording");
    $("#mic-icon").hidden = active;
    $("#mic-stop").hidden = !active;
    setText("#record-label", active ? "Recording" : "Tap to record");
    setText(
      "#record-hint",
      active
        ? "Tap the button again to stop and process."
        : "Speak a task, status update, or question.",
    );
    $("#record-timer").hidden = !active;
    $("#record-live").hidden = !active;
    $("#waveform").hidden = !active;
    $("#cancel-record").hidden = !active;
    if (!active) {
      setText("#record-timer", "00:00");
    }
    const locked = active || state.processing;
    $("#note-text").disabled = locked;
    $("#note-submit").disabled = locked;
    $("#audio-file").disabled = locked;
    $("#record-btn").disabled = state.processing;
  }

  function startLevelMeter(stream, context) {
    const waveform = $("#waveform");
    const bars = waveform ? $$("#waveform span", waveform) : [];
    if (!context || !waveform || bars.length < 2) {
      return null;
    }

    try {
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.72;
      source.connect(analyser);
      context.resume().catch(() => {});

      const bins = new Uint8Array(analyser.frequencyBinCount);
      const half = Math.floor(bars.length / 2);
      const nyquist = context.sampleRate / 2;
      const binHz = nyquist / analyser.frequencyBinCount;
      const minHz = 70;
      const maxHz = Math.min(9000, nyquist);
      const edges = [];
      for (let index = 0; index <= half; index += 1) {
        const hz = minHz * Math.pow(maxHz / minHz, index / half);
        edges.push(Math.max(1, Math.min(bins.length - 1, Math.round(hz / binHz))));
      }

      const meter = { context, source, analyser, bins, edges, bars, half, frame: 0 };
      const paint = () => {
        analyser.getByteFrequencyData(bins);
        for (let pair = 0; pair < half; pair += 1) {
          const start = edges[pair];
          const end = Math.max(start + 1, edges[pair + 1]);
          let sum = 0;
          let count = 0;
          for (let bin = start; bin < end; bin += 1) {
            sum += bins[bin];
            count += 1;
          }
          const average = count ? sum / count : 0;
          const boosted = Math.min(1, (average / 280) * (1 + pair * 0.07));
          const height = 8 + Math.pow(boosted, 0.8) * 92;
          const left = bars[half - 1 - pair];
          const right = bars[half + pair];
          if (left) {
            left.style.height = `${height.toFixed(1)}%`;
          }
          if (right) {
            right.style.height = `${height.toFixed(1)}%`;
          }
        }
        meter.frame = window.requestAnimationFrame(paint);
      };

      waveform.classList.add("is-live");
      meter.frame = window.requestAnimationFrame(paint);
      return meter;
    } catch {
      context.close().catch(() => {});
      return null;
    }
  }

  function stopLevelMeter(session) {
    const meter = session?.meter;
    if (!meter) {
      return;
    }
    session.meter = null;
    window.cancelAnimationFrame(meter.frame);
    try {
      meter.source.disconnect();
    } catch {}
    try {
      meter.analyser.disconnect();
    } catch {}
    meter.context.close().catch(() => {});
    meter.bars.forEach((bar) => {
      bar.style.height = "";
    });
    $("#waveform")?.classList.remove("is-live");
  }

  function pickMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function liveStreamUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/voice/stream`;
  }

  function setLiveTranscript(visible, { status, text } = {}) {
    const panel = $("#live-transcript");
    if (!panel) {
      return;
    }
    panel.hidden = !visible;
    if (status !== undefined) {
      setText("#live-transcript-status", status);
    }
    if (text !== undefined) {
      const node = $("#live-transcript-text");
      node.textContent = text || "Waiting for speech…";
      node.classList.toggle("is-empty", !text);
    }
  }

  function liveTranscriptStatus(status) {
    setText("#live-transcript-status", status);
  }

  function pcm16FromSamples(samples, sourceRate) {
    const targetRate = 16000;
    const step = sourceRate / targetRate;
    const length = step === 1 ? samples.length : Math.max(1, Math.floor(samples.length / step));
    const output = new Int16Array(length);
    for (let index = 0; index < length; index += 1) {
      const position = index * step;
      const base = Math.floor(position);
      const fraction = position - base;
      const raw =
        step === 1
          ? samples[index]
          : (samples[base] ?? 0) * (1 - fraction) +
            (samples[base + 1] ?? samples[base] ?? 0) * fraction;
      const sample = Math.max(-1, Math.min(1, raw));
      output[index] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return output.buffer;
  }

  function stopLiveAudio(session) {
    if (session.audioStopped) {
      return;
    }
    session.audioStopped = true;
    try {
      session.source?.disconnect();
    } catch {
      session.source = null;
    }
    try {
      session.worklet?.disconnect();
    } catch {
      session.worklet = null;
    }
    try {
      session.gain?.disconnect();
    } catch {
      session.gain = null;
    }
    if (session.context && session.context.state !== "closed") {
      session.context.close().catch(() => {});
    }
    session.source = null;
    session.worklet = null;
    session.gain = null;
    session.context = null;
  }

  function closeLiveSocket(session) {
    if (!session.socket) {
      return;
    }
    try {
      session.socket.close();
    } catch {
      session.socket = null;
    }
    session.socket = null;
  }

  function fallbackStreamToUpload(session) {
    if (session.fallbackStarted) {
      return;
    }
    session.fallbackStarted = true;
    session.streamWaiting = false;
    session.streamHandled = true;
    closeLiveSocket(session);
    setLiveTranscript(false);
    setProcessing(false);
    if (!session.fallbackBlob) {
      showToast("Live processing stopped and no audio was captured.", "error");
      return;
    }
    const type = session.recorder.mimeType || "audio/webm";
    const extension = type.includes("mp4") ? "mp4" : type.includes("ogg") ? "ogg" : "webm";
    processAudio(new File([session.fallbackBlob], `recording.${extension}`, { type }));
  }

  function handleLiveMessage(session, event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!message || typeof message !== "object") {
      return;
    }

    if (message.type === "ready") {
      session.streamReady = true;
      const maxSeconds = Number(message.max_seconds);
      if (Number.isFinite(maxSeconds) && maxSeconds > 0) {
        session.maxSeconds = maxSeconds;
      }
      setLiveTranscript(true, { status: "Listening", text: session.liveText });
      return;
    }

    if (message.type === "partial") {
      session.liveText = message.text;
      setLiveTranscript(true, { status: "Transcribing live", text: message.text });
      return;
    }

    if (message.type === "final_transcript") {
      session.liveText = message.text;
      setLiveTranscript(true, { status: "Final transcript", text: message.text });
      return;
    }

    if (message.type === "status") {
      if (message.stage === "finalizing") {
        setProcessing(
          true,
          "Finalizing transcript",
          message.message || "Finishing the live transcription.",
        );
        setLiveTranscript(true, { status: "Finalizing", text: session.liveText });
      } else if (message.stage === "extracting") {
        setProcessing(
          true,
          "Extracting task",
          message.message || "Reading the final transcript.",
        );
        setLiveTranscript(true, { status: "Extracting", text: session.liveText });
      }
      return;
    }

    if (message.type === "result") {
      session.streamHandled = true;
      session.streamWaiting = false;
      setLiveTranscript(true, {
        status: "Complete",
        text: message.result?.note?.raw_transcript || session.liveText,
      });
      closeLiveSocket(session);
      handleStreamResult(session, message.result);
      return;
    }

    if (message.type === "error") {
      session.streamHandled = true;
      session.streamWaiting = false;
      closeLiveSocket(session);
      setProcessing(false);
      setLiveTranscript(false);
      if (message.note) {
        showToast("Transcript saved, but the AI could not finish. It is in your notes.", "error");
        void refreshAll();
      } else {
        showToast(message.error?.message || "Could not process the recording.", "error");
      }
    }
  }

  async function handleStreamResult(session, result) {
    try {
      await handlePipelineResult(result);
    } catch (error) {
      showToast(error?.message || "The note was processed, but the UI could not refresh.", "error");
    } finally {
      setProcessing(false);
      window.setTimeout(() => {
        if (!state.recording && !state.processing) {
          setLiveTranscript(false);
        }
      }, 2200);
    }
  }

  async function startLiveStream(session, context) {
    if (!context || !window.AudioWorkletNode || typeof WebSocket === "undefined") {
      setLiveTranscript(false);
      return false;
    }

    let socket;
    try {
      socket = new WebSocket(liveStreamUrl());
    } catch {
      setLiveTranscript(false);
      return false;
    }
    session.socket = socket;
    socket.addEventListener("open", () => {
      try {
        socket.send(JSON.stringify({ type: "start", sample_rate: 16000 }));
      } catch {
        socket.close();
      }
    });
    socket.addEventListener("message", (event) => handleLiveMessage(session, event));
    socket.addEventListener("error", () => {
      liveTranscriptStatus("Live transcript unavailable");
    });
    socket.addEventListener("close", () => {
      session.socket = null;
      if (session.streamHandled || session.cancelled) {
        return;
      }
      session.streamReady = false;
      if (session.streamWaiting) {
        fallbackStreamToUpload(session);
        return;
      }
      if (state.recording === session) {
        liveTranscriptStatus("Live transcript paused");
        showToast(
          "Live transcript paused. The recording will be uploaded when you stop.",
          "info",
        );
      }
    });

    try {
      await context.audioWorklet.addModule("/pcm-worklet.js");
      if (!session.socket || session.cancelled || session.audioStopped) {
        context.close().catch(() => {});
        return false;
      }
      const source = context.createMediaStreamSource(session.stream);
      const worklet = new AudioWorkletNode(context, "pcm-capture");
      const gain = context.createGain();
      gain.gain.value = 0;
      source.connect(worklet);
      worklet.connect(gain);
      gain.connect(context.destination);
      worklet.port.onmessage = (event) => {
        if (session.audioStopped || session.cancelled || !session.socket) {
          return;
        }
        if (session.socket.readyState !== WebSocket.OPEN) {
          return;
        }
        try {
          session.socket.send(pcm16FromSamples(event.data, context.sampleRate));
        } catch {
          closeLiveSocket(session);
        }
      };
      if (context.state === "suspended") {
        await context.resume();
      }
      session.context = context;
      session.source = source;
      session.worklet = worklet;
      session.gain = gain;
      return true;
    } catch {
      session.streamHandled = true;
      closeLiveSocket(session);
      context.close().catch(() => {});
      setLiveTranscript(false);
      return false;
    }
  }

  async function startRecording() {
    if (state.processing) {
      showToast("A note is already being processed.", "info");
      return;
    }
    if (state.recording) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      showToast(
        "This browser does not support in-browser recording. Upload an audio file instead.",
        "error",
      );
      return;
    }

    let liveContext = null;
    if (window.AudioContext) {
      try {
        liveContext = new AudioContext({ sampleRate: 16000 });
        liveContext.resume().catch(() => {});
      } catch {
        liveContext = null;
      }
    }

    let meterContext = null;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      try {
        meterContext = new AudioContextClass();
        meterContext.resume().catch(() => {});
      } catch {
        meterContext = null;
      }
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const mimeType = pickMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const session = {
        recorder,
        stream,
        chunks: [],
        cancelled: false,
        startedAt: Date.now(),
        timer: null,
        finished: false,
        limitReached: false,
        socket: null,
        context: null,
        source: null,
        worklet: null,
        gain: null,
        meter: null,
        streamReady: false,
        streamWaiting: false,
        streamHandled: false,
        fallbackStarted: false,
        fallbackBlob: null,
        audioStopped: false,
        liveText: "",
        maxSeconds: MAX_RECORD_SECONDS,
      };
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          session.chunks.push(event.data);
        }
      });
      recorder.addEventListener("stop", () => finalizeRecording(session));
      recorder.start(250);
      session.timer = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - session.startedAt) / 1000);
        setText("#record-timer", formatDuration(elapsed));
        if (elapsed >= session.maxSeconds && !session.limitReached) {
          session.limitReached = true;
          showToast("Recording limit reached. Processing audio.", "info");
          stopRecording(false);
        }
      }, 250);
      state.recording = session;
      setText("#record-timer", "00:00");
      setRecordingUI(true);
      session.meter = startLevelMeter(stream, meterContext);
      if (!session.meter) {
        meterContext?.close().catch(() => {});
      }
      if (liveContext) {
        setLiveTranscript(true, { status: "Connecting", text: "" });
        void startLiveStream(session, liveContext);
      }
    } catch (error) {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      if (liveContext) {
        liveContext.close().catch(() => {});
      }
      if (meterContext) {
        meterContext.close().catch(() => {});
      }
      const denied = error?.name === "NotAllowedError" || error?.name === "SecurityError";
      showToast(
        denied
          ? "Microphone access was denied. Allow it in the browser or upload an audio file."
          : "Could not start recording. Check your microphone and try again.",
        "error",
      );
    }
  }

  function stopRecording(cancelled = false) {
    const session = state.recording;
    if (!session) {
      return;
    }
    session.cancelled = cancelled;

    if (cancelled) {
      if (session.socket?.readyState === WebSocket.OPEN) {
        try {
          session.socket.send(JSON.stringify({ type: "cancel" }));
        } catch {
          session.socket = null;
        }
      }
      closeLiveSocket(session);
      stopLiveAudio(session);
      setLiveTranscript(false);
    } else if (session.streamReady && session.socket?.readyState === WebSocket.OPEN) {
      session.streamWaiting = true;
      try {
        session.socket.send(JSON.stringify({ type: "stop" }));
        setProcessing(
          true,
          "Finalizing transcript",
          "Finishing the live transcription, then extracting the intent.",
        );
        setLiveTranscript(true, { status: "Finalizing", text: session.liveText });
      } catch {
        session.streamWaiting = false;
      }
    } else {
      closeLiveSocket(session);
      setLiveTranscript(false);
    }

    if (session.recorder.state === "inactive") {
      finalizeRecording(session);
      return;
    }
    try {
      session.recorder.stop();
    } catch {
      finalizeRecording(session);
    }
  }

  function finalizeRecording(session) {
    if (session.finished) {
      return;
    }
    session.finished = true;
    window.clearInterval(session.timer);
    stopLevelMeter(session);
    stopLiveAudio(session);
    session.stream.getTracks().forEach((track) => track.stop());
    if (state.recording === session) {
      state.recording = null;
    }
    setRecordingUI(false);
    if (session.cancelled) {
      closeLiveSocket(session);
      setLiveTranscript(false);
      showToast("Recording discarded.", "info");
      return;
    }
    const type = session.recorder.mimeType || "audio/webm";
    const extension = type.includes("mp4") ? "mp4" : type.includes("ogg") ? "ogg" : "webm";
    const blob = new Blob(session.chunks, { type });
    session.fallbackBlob = blob;
    if (session.streamWaiting) {
      setLiveTranscript(true, { status: "Finalizing", text: session.liveText });
      return;
    }
    closeLiveSocket(session);
    setLiveTranscript(false);
    if (!blob.size) {
      showToast("No audio was captured. Try again.", "error");
      return;
    }
    processAudio(new File([blob], `recording.${extension}`, { type }));
  }

  async function processAudio(file) {
    if (state.processing) {
      showToast("A note is already being processed.", "info");
      return;
    }
    if (!file || file.size === 0) {
      showToast("The audio file is empty.", "error");
      return;
    }
    setLiveTranscript(false);
    setProcessing(
      true,
      "Transcribing audio",
      "Extracting the intent. The first run may take a minute.",
    );
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api("/api/voice/transcribe", { method: "POST", body: form });
      await handlePipelineResult(result);
    } catch (error) {
      if (error?.payload?.note) {
        showToast(
          "Transcript saved, but the AI could not finish. It is in your notes.",
          "error",
        );
        await refreshAll();
      } else {
        showToast(error?.message || "Could not process the audio.", "error");
      }
    } finally {
      setProcessing(false);
    }
  }

  async function submitNote(event) {
    event.preventDefault();
    if (state.processing) {
      return;
    }
    const input = $("#note-text");
    const text = input.value.trim();
    if (!text) {
      showToast("Type a note first.", "error");
      input.focus();
      return;
    }
    input.value = "";
    setLiveTranscript(false);
    setProcessing(true, "Extracting intent", "Saving the note and reading the intent.");
    try {
      const result = await api("/api/notes", { method: "POST", body: { text } });
      await handlePipelineResult(result);
    } catch (error) {
      if (error?.payload?.note) {
        showToast("Note saved, but the AI could not finish. It is in your notes.", "error");
        await refreshAll();
      } else {
        input.value = text;
        showToast(error?.message || "Could not save the note.", "error");
      }
    } finally {
      setProcessing(false);
    }
  }

  async function handlePipelineResult(result) {
    const action = result?.action || {};
    if (action.type === "task_created" && action.task) {
      state.highlightTaskId = action.task.id;
      state.taskFilter = "ALL";
      state.taskQuery = "";
      const search = $("#task-search");
      if (search) {
        search.value = "";
      }
      showToast(`Task created: ${action.task.title}`, "success");
    } else if (action.type === "task_updated" && action.task) {
      state.highlightTaskId = action.task.id;
      showToast(
        `Task updated: ${action.task.title} is now ${statusMeta(action.task.status).label.toLowerCase()}.`,
        "success",
      );
    } else if (action.type === "tasks_listed") {
      const count = action.total ?? action.tasks?.length ?? 0;
      showToast(`${count} ${pluralize(count, "task")} found.`, "info");
      showQueryResults(action);
    } else {
      showToast("Note saved to your memory.", "success");
    }

    await refreshAll();

    if (state.highlightTaskId) {
      const highlightedId = state.highlightTaskId;
      window.setTimeout(() => {
        if (state.highlightTaskId === highlightedId) {
          state.highlightTaskId = null;
        }
        $$(".task-card.is-highlighted").forEach((card) => {
          card.classList.remove("is-highlighted");
        });
      }, 5000);
    }
  }

  function showToast(message, type = "info", timeout = 6000) {
    const stack = $("#toast-stack");
    const toast = document.createElement("div");
    const icon = type === "success" ? icons.check : type === "error" ? icons.alert : icons.info;
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    toast.innerHTML = `<span class="toast-icon">${icon}</span><p>${escapeHtml(message)}</p><button class="toast-close" type="button" aria-label="Dismiss">${icons.close}</button>`;
    const remove = () => {
      if (!toast.isConnected) {
        return;
      }
      toast.classList.add("is-leaving");
      window.setTimeout(() => toast.remove(), 200);
    };
    toast.querySelector(".toast-close").addEventListener("click", remove);
    stack.appendChild(toast);
    while (stack.children.length > 4) {
      stack.firstElementChild.remove();
    }
    window.setTimeout(remove, timeout);
  }

  function handleClick(event) {
    const viewLink = event.target.closest("[data-view-link]");
    if (viewLink) {
      event.preventDefault();
      navigate(viewLink.dataset.viewLink);
      return;
    }
    const newNote = event.target.closest("[data-new-note]");
    if (newNote) {
      event.preventDefault();
      focusCapture();
      return;
    }
    const example = event.target.closest("[data-example]");
    if (example) {
      const input = $("#note-text");
      input.value = example.dataset.example;
      input.focus();
      return;
    }
    const closeButton = event.target.closest("[data-close-dialog]");
    if (closeButton) {
      closeDialog(closeButton.closest("dialog"));
      return;
    }
    const filter = event.target.closest("[data-task-filter]");
    if (filter) {
      state.taskFilter = filter.dataset.taskFilter;
      renderTasks();
      return;
    }
    const source = event.target.closest("[data-note-source]");
    if (source) {
      state.noteSource = source.dataset.noteSource;
      renderNotes();
      return;
    }
    const complete = event.target.closest("[data-complete-task]");
    if (complete) {
      updateTaskStatus(complete.dataset.completeTask, "COMPLETED");
      return;
    }
    const remove = event.target.closest("[data-delete-task]");
    if (remove) {
      requestDelete(remove.dataset.deleteTask);
      return;
    }
    const note = event.target.closest("[data-open-note]");
    if (note) {
      openNoteDetail(note.dataset.openNote);
    }
  }

  function handleChange(event) {
    const select = event.target.closest("[data-status-task]");
    if (!select) {
      return;
    }
    updateTaskStatus(select.dataset.statusTask, select.value);
  }

  function handleAudioFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      processAudio(file);
    }
  }

  function handleSearch(event) {
    state.taskQuery = event.target.value.trim();
    renderTasks();
  }

  async function handleRefresh() {
    await checkHealth();
    await refreshAll();
  }

  async function handleRetry() {
    const online = await checkHealth({ announce: true });
    if (online) {
      await refreshAll();
    }
  }

  function handleMobileCapture() {
    if (state.recording) {
      stopRecording(false);
      return;
    }
    navigate("overview");
    window.setTimeout(() => startRecording(), 80);
  }

  function handleHashChange() {
    const view = window.location.hash.replace("#", "");
    navigate(VIEW_META[view] ? view : "overview", { updateHash: false });
  }

  function bindEvents() {
    $("#note-form").addEventListener("submit", submitNote);
    $("#record-btn").addEventListener("click", () => {
      if (state.recording) {
        stopRecording(false);
      } else {
        startRecording();
      }
    });
    $("#cancel-record").addEventListener("click", () => stopRecording(true));
    $("#audio-file").addEventListener("change", handleAudioFile);
    $("#task-search").addEventListener("input", handleSearch);
    $("#refresh-btn").addEventListener("click", handleRefresh);
    $("#retry-connection").addEventListener("click", handleRetry);
    $("#notes-load-more").addEventListener("click", loadMoreNotes);
    $("#confirm-delete").addEventListener("click", confirmDelete);
    $("#mobile-capture").addEventListener("click", handleMobileCapture);
    document.addEventListener("click", handleClick);
    document.addEventListener("change", handleChange);
    $$("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => closeDialog(button.closest("dialog")));
    });
    $$("dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
          closeDialog(dialog);
        }
      });
      dialog.addEventListener("close", () => {
        if (dialog.id === "delete-dialog") {
          state.pendingDeleteId = null;
        }
      });
    });
    window.addEventListener("hashchange", handleHashChange);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        checkHealth();
      }
    });
  }

  function init() {
    setTodayLabel();
    bindEvents();
    const initialView = window.location.hash.replace("#", "");
    navigate(VIEW_META[initialView] ? initialView : "overview");
    renderSkeletons();
    refreshAll({ initial: true });
    window.setInterval(() => checkHealth(), 30000);
  }

  init();
})();
