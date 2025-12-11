let currentIndex = 1;
let surveysData = [];
let widgetId = 590;
let orgUnitId = 6606;

function createListItem(item) {
    const el = document.createElement("li");
    el.className = "survey-item";
    el.innerHTML = `
        <strong><a href="${item.url}" target="_blank">${item.name}</a></strong>: ${item.description || ""}
    `;
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
        wrapper.innerHTML = `<p>No surveys available at the moment (Should I be hidden if there no surveys at the moment?).</p>`;
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

async function loadWidgetData(orgUnitId, widgetId) {

    try {
        if (!widgetId) {
            console.error("Widget ID not found on body element.");
            loadSurveys([]);
            return;
        }

        // API endpoints
        const generalUrl = `/d2l/api/lp/1.46/${orgUnitId}/widgetdata/${widgetId}`;
        const userUrl = `/d2l/api/lp/1.46/${orgUnitId}/widgetdata/${widgetId}/mydata`;

        const [generalRes, userRes] = await Promise.all([
            fetch(generalUrl).then(r => r.json()),
            fetch(userUrl).then(r => r.json())
        ]);

        const generalData = parseWrappedData(generalRes) || [];
        const userData = parseWrappedData(userRes) || [];

        // Build map of surveyId → url coming from user-specific data
        const urlMap = new Map(
            userData.map(u => [u.surveyId, u.url])
        );

        const filtered = generalData
            .filter(s => urlMap.has(s.surveyId))     // keep only those user can access
            .map(s => ({
                ...s,
                url: urlMap.get(s.surveyId)         // inject user-specific URL
            }));

        loadSurveys(filtered);

    } catch (e) {
        console.error("Error loading widget data:", e);
        loadSurveys([]);
    }
}

loadWidgetData(orgUnitId, widgetId)