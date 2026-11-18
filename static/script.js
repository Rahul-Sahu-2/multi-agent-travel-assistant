let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswer = "";
let latestPlanText = "";
let lastUserMessage = "";

const travelForm = document.getElementById("travelForm");

const originInput = document.getElementById("origin");
const destinationInput = document.getElementById("destination");
const durationInput = document.getElementById("duration");
const budgetInput = document.getElementById("budget");
const extraInput = document.getElementById("extra");

const submitBtn = document.getElementById("submitBtn");

const loadingSection = document.getElementById("loadingSection");
const errorSection = document.getElementById("errorSection");
const errorMessage = document.getElementById("errorMessage");
const resultsContent = document.getElementById("resultsContent");

const finalAnswer = document.getElementById("finalAnswer");
const flightResults = document.getElementById("flightResults");
const hotelResults = document.getElementById("hotelResults");
const itineraryResults = document.getElementById("itineraryResults");

const threadId = document.getElementById("threadId");

const retryBtn = document.getElementById("retryBtn");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const newTripBtn = document.getElementById("newTripBtn");

const pdfContent = document.getElementById("pdfContent");


function setButtonText(text) {
    const textNode = Array.from(submitBtn.childNodes).find(
        node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
    );

    if (textNode) {
        textNode.textContent = ` ${text} `;
    }
}


function setLoading(isLoading) {
    submitBtn.disabled = isLoading;

    if (isLoading) {
        setButtonText("Planning Your Trip...");
    } else {
        setButtonText("Plan My Trip");
    }
}


function hideAllSections() {
    loadingSection.hidden = true;
    errorSection.hidden = true;
    resultsContent.hidden = true;
}


function showLoading() {
    hideAllSections();

    loadingSection.hidden = false;

    loadingSection.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function showError(message) {
    hideAllSections();

    errorMessage.textContent = message;
    errorSection.hidden = false;

    errorSection.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function formatMarkdown(content) {
    if (!content || !content.trim()) {
        return "No information available.";
    }

    if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
        return content;
    }

    const html = marked.parse(content);

    return DOMPurify.sanitize(html);
}


function showResults(data) {
    hideAllSections();

    latestAnswer = data.answer || "";

    finalAnswer.innerHTML = formatMarkdown(data.answer);
    flightResults.innerHTML = formatMarkdown(data.flight_results);
    hotelResults.innerHTML = formatMarkdown(data.hotel_results);
    itineraryResults.innerHTML = formatMarkdown(data.itinerary);

    currentThreadId = data.thread_id || null;

    if (currentThreadId) {
        localStorage.setItem("travel_thread_id", currentThreadId);
    }

    threadId.textContent = currentThreadId || "Not available";

    latestPlanText = [
        "TRAVEL AGENT - YOUR TRAVEL PLAN",
        "",
        "FINAL TRAVEL RECOMMENDATION",
        data.answer || "",
        "",
        "FLIGHT INFORMATION",
        data.flight_results || "",
        "",
        "HOTEL SUGGESTIONS",
        data.hotel_results || "",
        "",
        "DAY-BY-DAY ITINERARY",
        data.itinerary || ""
    ].join("\n");

    resultsContent.hidden = false;

    resultsContent.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


function createTravelMessage() {
    const origin = originInput.value.trim();
    const destination = destinationInput.value.trim();
    const duration = durationInput.value.trim();
    const budget = budgetInput.value.trim();
    const extra = extraInput.value.trim();

    let message = `Plan a complete ${duration} days trip from ${origin} to ${destination}.`;

    message += ` My total travel budget is ₹${budget}.`;

    if (extra) {
        message += ` Additional preferences: ${extra}`;
    }

    return message;
}


async function sendMessage() {
    if (!travelForm.reportValidity()) {
        return;
    }

    const userInput = createTravelMessage();

    lastUserMessage = userInput;

    showLoading();
    setLoading(true);

    try {
        const response = await fetch("/api/travel", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: userInput,
                thread_id: currentThreadId
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(
                data.error ||
                data.detail ||
                "Unable to generate your travel plan."
            );
        }

        showResults(data);

    } catch (error) {
        console.error("Travel API Error:", error);

        showError(
            error.message || "Something went wrong. Please try again."
        );

    } finally {
        setLoading(false);
    }
}


travelForm.addEventListener("submit", function (event) {
    event.preventDefault();

    sendMessage();
});


retryBtn.addEventListener("click", function () {
    if (lastUserMessage) {
        sendMessage();
    }
});


copyBtn.addEventListener("click", async function () {
    if (!latestPlanText) {
        return;
    }

    try {
        await navigator.clipboard.writeText(latestPlanText);

        copyBtn.textContent = "Copied!";

        setTimeout(function () {
            copyBtn.textContent = "Copy Plan";
        }, 2000);

    } catch (error) {
        console.error("Copy Error:", error);

        showError("Unable to copy the travel plan. Please try again.");
    }
});


downloadBtn.addEventListener("click", function () {
    if (typeof html2pdf === "undefined") {
        showError("PDF library could not load. Please refresh the page.");
        return;
    }

    const options = {
        margin: 10,

        filename: "Travel-Agent-Trip-Plan.pdf",

        image: {
            type: "jpeg",
            quality: 0.98
        },

        html2canvas: {
            scale: 2,
            useCORS: true
        },

        jsPDF: {
            unit: "mm",
            format: "a4",
            orientation: "portrait"
        },

        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    downloadBtn.disabled = true;
    downloadBtn.textContent = "Generating PDF...";

    html2pdf()
        .set(options)
        .from(pdfContent)
        .save()
        .then(function () {
            downloadBtn.disabled = false;
            downloadBtn.textContent = "Download PDF ↓";
        })
        .catch(function (error) {
            console.error("PDF Error:", error);

            downloadBtn.disabled = false;
            downloadBtn.textContent = "Download PDF ↓";

            showError("Unable to generate PDF. Please try again.");
        });
});


newTripBtn.addEventListener("click", function () {
    currentThreadId = null;
    latestAnswer = "";
    latestPlanText = "";
    lastUserMessage = "";

    localStorage.removeItem("travel_thread_id");

    travelForm.reset();

    finalAnswer.textContent = "";
    flightResults.textContent = "";
    hotelResults.textContent = "";
    itineraryResults.textContent = "";

    threadId.textContent = "";

    hideAllSections();

    setLoading(false);

    travelForm.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

    originInput.focus();
});


document.addEventListener("keydown", function (event) {
    if (event.ctrlKey && event.key === "Enter") {
        if (!submitBtn.disabled) {
            sendMessage();
        }
    }
});