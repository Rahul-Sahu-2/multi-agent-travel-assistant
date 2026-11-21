/* =========================================================
   Travel Agent frontend
   Talks to:  POST /api/travel          (start a plan)
              POST /api/travel/approve  (approve / request changes)
   ========================================================= */

let currentThreadId = null;     // LangGraph thread of the plan in progress
let pendingApproval = false;    // true while the draft waits for human review
let isBusy = false;
let latestAnswerMarkdown = "";

const $ = (id) => document.getElementById(id);

/* ---------- small helpers ---------- */

function renderMarkdown(text) {
    const raw = String(text || "");
    if (typeof marked !== "undefined") {
        const html = marked.parse(raw);
        return typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html;
    }
    const div = document.createElement("div");
    div.textContent = raw;
    return div.innerHTML.replace(/\n/g, "<br>");
}

function showError(message) {
    const box = $("errorBox");
    box.textContent = message;
    box.classList.remove("hidden");
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideError() {
    const box = $("errorBox");
    box.classList.add("hidden");
    box.textContent = "";
}

function setLoading(loading) {
    isBusy = loading;

    const sendBtn = $("sendBtn");
    const chatSendBtn = $("chatSendBtn");

    if (sendBtn) sendBtn.disabled = loading;
    if (chatSendBtn) chatSendBtn.disabled = loading;

    document
        .querySelectorAll("#approvalActions button")
        .forEach((b) => (b.disabled = loading));

    $("btnText").classList.toggle("hidden", loading);
    $("btnLoader").classList.toggle("hidden", !loading);
}

/* ---------- chat bubbles ---------- */

function addMessage(role, content, { markdown = false } = {}) {
    const list = $("conversationMessages");
    const isUser = role === "user";

    const wrap = document.createElement("div");
    wrap.className = "message " + (isUser ? "user-message" : "assistant-message");

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = isUser ? "👤" : "✈";

    const body = document.createElement("div");
    body.className = "message-body";

    const name = document.createElement("div");
    name.className = "message-name";
    name.textContent = isUser ? "You" : "Travel Agent";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (markdown) {
        bubble.innerHTML = renderMarkdown(content);
    } else {
        bubble.textContent = content;
        bubble.style.whiteSpace = "pre-wrap";
    }

    body.appendChild(name);
    body.appendChild(bubble);
    wrap.appendChild(avatar);
    wrap.appendChild(body);
    list.appendChild(wrap);
    list.scrollTop = list.scrollHeight;

    return wrap;
}

function addTyping(text) {
    const el = addMessage("assistant", text || "Working on it… this can take 1–2 minutes.");
    el.classList.add("typing");
    return el;
}

function removeEl(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

/* ---------- travel plan panel ---------- */

function showPlan(markdown, label) {
    latestAnswerMarkdown = markdown || "";
    $("resultBox").innerHTML = renderMarkdown(latestAnswerMarkdown);
    $("threadInfo").textContent = label || "";
    $("resultBox").scrollTop = 0;
}

function setApprovalVisible(visible) {
    $("approvalActions").classList.toggle("hidden", !visible);
}

/* ---------- API ---------- */

async function postJSON(url, payload) {
    let response;
    try {
        response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
    } catch (networkError) {
        throw new Error("Cannot reach the server. Is the backend running?");
    }

    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        /* non-JSON error page */
    }

    if (!response.ok || !data || !data.success) {
        const msg = (data && (data.error || data.detail)) || `Server error (${response.status}).`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
}

function handleAgentResult(data) {
    currentThreadId = data.thread_id;

    // Blocked by the input guardrail -> just reply in chat
    if (data.guardrail_allowed === false) {
        pendingApproval = false;
        setApprovalVisible(false);
        currentThreadId = null;
        addMessage("assistant", data.answer || data.guardrail_reason || "I can only help with travel planning.");
        return;
    }

    if (data.requires_approval) {
        pendingApproval = true;
        showPlan(data.answer, "Draft – waiting for your approval");
        setApprovalVisible(true);
        addMessage(
            "assistant",
            "I've prepared a draft travel plan on the right. " +
                "Click “Approve Plan” to finalize it, or type what you'd like changed here in the chat and press send."
        );
    } else {
        pendingApproval = false;
        showPlan(data.answer, "Final travel plan");
        setApprovalVisible(false);
        addMessage("assistant", "Your final travel plan is ready! You can copy it or download it as a PDF.");
        currentThreadId = null; // next request starts a fresh plan
    }
}

async function startPlan(message) {
    hideError();
    setLoading(true);
    setApprovalVisible(false);
    pendingApproval = false;
    const typing = addTyping("Planning your trip with flights, hotels, weather and budget agents… this can take 1–2 minutes.");

    try {
        const data = await postJSON("/api/travel", {
            message: message,
            thread_id: null,
        });
        removeEl(typing);
        handleAgentResult(data);
    } catch (err) {
        removeEl(typing);
        addMessage("assistant", "Sorry, something went wrong: " + err.message);
        showError(err.message);
    } finally {
        setLoading(false);
    }
}

async function submitApproval(approved, feedback = "") {
    if (isBusy) return;

    if (!currentThreadId || !pendingApproval) {
        showError("There is no draft waiting for approval.");
        return;
    }

    // "Request Changes" needs a feedback text -> ask the user to type it in chat
    if (!approved && !feedback.trim()) {
        const input = $("userInput");
        addMessage("assistant", "Sure! Tell me what you'd like to change (type it below and press send).");
        input.focus();
        return;
    }

    hideError();
    setLoading(true);
    setApprovalVisible(false);
    const typing = addTyping(
        approved ? "Finalizing your travel plan…" : "Updating the plan with your feedback…"
    );

    try {
        const data = await postJSON("/api/travel/approve", {
            thread_id: currentThreadId,
            approved: approved,
            feedback: feedback.trim(),
        });
        removeEl(typing);
        handleAgentResult(data);
    } catch (err) {
        removeEl(typing);
        pendingApproval = true;
        setApprovalVisible(true);
        addMessage("assistant", "Sorry, something went wrong: " + err.message);
        showError(err.message);
    } finally {
        setLoading(false);
    }
}

/* ---------- user actions ---------- */

function buildTripMessage() {
    const from = $("fromCity").value.trim();
    const dest = $("destination").value.trim();
    const when = $("travelMonth").value.trim();
    const duration = $("duration").value;
    const travellers = $("travellers").value;
    const budget = $("budget").value.trim();

    let msg = `Plan a ${duration} trip from ${from} to ${dest}. `;
    msg += `Travel dates: ${when}. Travellers: ${travellers}. `;
    msg += budget
        ? `Total budget: ₹${budget}. `
        : "No fixed budget, suggest a realistic mid-range plan. ";
    msg += "Include flight info, hotel suggestions, weather, estimated budget and a day-by-day itinerary.";
    return msg;
}

function handleFormSubmit(event) {
    event.preventDefault();
    if (isBusy) return;

    const message = buildTripMessage();
    addMessage("user", message);
    startPlan(message);

    $("assistant").scrollIntoView({ behavior: "smooth", block: "start" });
}

function sendMessage() {
    if (isBusy) return;

    const input = $("userInput");
    const text = input.value.trim();

    if (!text) {
        showError("Please type a message first.");
        return;
    }

    hideError();
    input.value = "";
    addMessage("user", text);

    if (pendingApproval) {
        // While a draft is waiting, chat text = revision feedback
        submitApproval(false, text);
    } else {
        startPlan(text);
    }
}

function setPrompt(text) {
    $("userInput").value = text;
}

function newTrip() {
    if (isBusy) return;

    currentThreadId = null;
    pendingApproval = false;
    latestAnswerMarkdown = "";
    hideError();
    setApprovalVisible(false);

    $("tripForm").reset();
    $("userInput").value = "";
    $("threadInfo").textContent = "Your generated plan will appear here.";
    $("resultBox").innerHTML =
        '<div class="empty-result"><div class="empty-icon">✈</div>' +
        "<h3>Your adventure starts here</h3>" +
        "<p>Fill in your trip details and generate your personalized travel plan.</p></div>";

    $("conversationMessages").innerHTML = "";
    addMessage(
        "assistant",
        "Hello! I'm your AI travel assistant. Enter your trip details above and I'll create your personalized travel plan."
    );

    $("planner").scrollIntoView({ behavior: "smooth", block: "start" });
}

function copyResult() {
    const text = $("resultBox").innerText.trim();
    if (!latestAnswerMarkdown || !text) {
        showError("There is no travel plan to copy yet.");
        return;
    }

    const btn = document.querySelector(".copy-btn");
    const old = btn.textContent;

    const done = () => {
        btn.textContent = "Copied!";
        setTimeout(() => (btn.textContent = old), 1400);
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done).catch(() => showError("Could not copy result."));
    } else {
        // fallback for non-HTTPS
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand("copy");
            done();
        } catch (_) {
            showError("Could not copy result.");
        }
        document.body.removeChild(ta);
    }
}

function downloadPDF() {
    const pdfContent = $("pdfContent");

    if (!latestAnswerMarkdown) {
        showError("No travel plan available to download.");
        return;
    }
    if (typeof html2pdf === "undefined") {
        showError("PDF library failed to load. Check your internet connection.");
        return;
    }

    const btn = document.querySelector(".download-btn");
    const old = btn.textContent;
    btn.textContent = "Preparing PDF...";
    btn.disabled = true;

    html2pdf()
        .set({
            margin: 0.5,
            filename: "ai-travel-plan.pdf",
            image: { type: "jpeg", quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
            jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
            pagebreak: { mode: ["css", "legacy"] },
        })
        .from(pdfContent)
        .save()
        .then(() => {
            btn.textContent = old;
            btn.disabled = false;
        })
        .catch(() => {
            btn.textContent = old;
            btn.disabled = false;
            showError("Could not download PDF.");
        });
}

/* ---------- wiring ---------- */

document.addEventListener("DOMContentLoaded", () => {
    $("tripForm").addEventListener("submit", handleFormSubmit);
    $("newTripBtn").addEventListener("click", newTrip);

    $("userInput").addEventListener("keydown", (event) => {
        // Enter = send, Shift+Enter = new line (Ctrl+Enter also works)
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
});