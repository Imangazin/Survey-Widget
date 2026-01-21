let currentIndex = 1;
let surveysData = [];
let widgetId = ;
let orgUnitId = ;


// In-memory state for this widget load
let state = { generalData: [], userData: [] };

// In Brightspace domain we can update the current user's mydata directly via LP API
const updateMyDataApi = () => getUserUrl();

function getGeneralUrl() {
    return `/d2l/api/lp/1.49/${orgUnitId}/widgetdata/${widgetId}`;
}
function getUserUrl() {
    return `/d2l/api/lp/1.49/${orgUnitId}/widgetdata/${widgetId}/mydata`;
}

// Build the Brightspace "double JSON" payload expected by widgetdata endpoints
function buildMyDataPayload(userItems) {
    return { Data: JSON.stringify({ Items: userItems }) };
}

// Hides the widget
function hideTheWidget(){
	var parentDocument = window.parent.document;
	var parentIframe =  parentDocument.querySelector('[title="'+surveyWidgetTitle+'"]');
	parentIframe.parentNode.parentNode.parentNode.parentNode.style.display='none';
}

// Called when a user clicks a survey link.
// 1) Removes the clicked survey from userData (in-memory) and re-renders immediately.
// 2) Updates user data in the widget
async function handleSurveyClick(e, surveyId, url) {
    const token = await getToken();
    try {
        if (e) e.preventDefault();

        // Remove clicked survey from in-memory userData
        state.userData = (state.userData || []).filter(u => Number(u.surveyId) !== Number(surveyId));

        // Re-render immediately so UI reflects removal even if backend is slow
        loadWidgetData(state.generalData, state.userData);

        // Ask backend to persist updated userData to Brightspace /mydata
        // (Browser cannot reliably PUT to D2L APIs due to auth/CSRF; backend must do it.)
        // const updatedPayload ={
        //     Data: JSON.stringify({Items:state.userData})
        // };
        const updatedPayload = buildMyDataPayload(state.userData);
        await fetch(updateMyDataApi(), {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json", "X-Csrf-Token": token.referrerToken},
            body: JSON.stringify(updatedPayload)
        });
    } catch (err) {
        console.error("Failed to update user data on click:", err);
    } finally {
        // Always open the survey link
        window.open(url, "_blank", "noopener");
    }
}

function createListItem(item) {
    const el = document.createElement("li");
    el.className = "survey-item";

    const safeUrl = String(item.url || "");
    const safeName = String(item.name || "");
    const safeDesc = String(item.description || "");

    el.innerHTML = `
        <strong>
            <a href="${safeUrl}" target="_blank" rel="noopener">
                ${safeName}
            </a>
        </strong>: ${safeDesc}
    `;

    const link = el.querySelector("a");
    if (link) {
        link.addEventListener("click", (e) => handleSurveyClick(e, item.surveyId, safeUrl));
    }

    return el;
}

function loadSurveys(surveys) {
    let container = document.getElementById("survey-container");
    if (!container) {
        console.error("Target container #survey-container not found.");
        return;
    }

    let wrapper = container.querySelector(".survey-list");
    if (!wrapper) {
        wrapper = document.createElement("ul");
        wrapper.className = "survey-list";
        container.appendChild(wrapper);
    }

    wrapper.innerHTML = "";

    if (!surveys || surveys.length === 0) {
        //hideTheWidget();
        // wrapper.innerHTML = `<li>No surveys available at the moment.</li>`;
        // return;
        container.parentNode.parentNode.parentNode.parentNode.parentNode.parentNode.parentNode.parentNode.parentNode.style.display='none';
        return;
    }

    surveys.forEach(s => {
        wrapper.appendChild(createListItem(s));
    });
}

// Helper function assumed present
function parseWrappedData(response) {
    if (!response || !response.Data) return [];
    try {
        const parsed = JSON.parse(response.Data);
        return parsed.Items || [];
    } catch (e) {
        console.error("Failed to parse wrapped API data:", e);
        return [];
    }
}

async function getWidgetData() {
    try {
        if (!widgetId) {
            console.error("widgetId is not set.");
            return { generalData: [], userData: [] };
        }
        const generalUrl = getGeneralUrl();
        const userUrl = getUserUrl();

        // Fetch both in parallel
        const [generalResp, userResp] = await Promise.all([
            fetch(generalUrl),
            fetch(userUrl)
        ]);

        const generalRes = await generalResp.json();
        const userRes = await userResp.json();

        const generalData = parseWrappedData(generalRes) || [];
        const userData = parseWrappedData(userRes) || [];

        return { generalData, userData };
    } catch (e) {
        console.error("Error loading widget data:", e);
        return { generalData: [], userData: [] };
    }
}

function loadWidgetData(generalData, userData) {
    // Build map of surveyId → url coming from user-specific data
    const urlMap = new Map(userData.map(u => [u.surveyId, u.url]));

    const filtered = generalData
        .filter(s => urlMap.has(s.surveyId))
        .map(s => ({
            ...s,
            url: urlMap.get(s.surveyId)
        }));

    loadSurveys(filtered);
}

async function getToken() {
    const res = await fetch('/d2l/lp/auth/xsrf-tokens', { credentials: "include" });
    if (!res.ok) throw new Error(`xsrf-tokens failed: ${res.status}`);
    return await res.json(); // { referrerToken, ... }
}

(async () => {
    const { generalData, userData } = await getWidgetData();
    state.generalData = generalData;
    state.userData = userData;
    loadWidgetData(generalData, userData);
})();