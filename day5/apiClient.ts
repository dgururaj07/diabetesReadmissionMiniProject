// Typed client for the FastAPI backend. Only exports functions; importing it runs nothing.
import type { CareQueueItem, CareQueueParams, Encounter, EncounterDetail, EncounterParams } from "./types.ts";

const BASE_URL = "http://127.0.0.1:8000";

// Turns { risk_level: "HIGH", limit: 5 } into "?risk_level=HIGH&limit=5", skipping params that were left out
function toQuery(params: object): string {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) {
            query.append(key, String(value));
        }
    }
    const text = query.toString();
    return text ? `?${text}` : "";
}

// Every request goes through here: one place for the base URL and error handling.
// <T> is the type the caller expects back.
async function getJson<T>(path: string): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`);
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ? `${response.status}: ${JSON.stringify(body.detail)}` : `Request failed with status ${response.status}`);
    }
    return await response.json();
}

export function getEncounters(params: EncounterParams = {}): Promise<Encounter[]> {
    return getJson<Encounter[]>(`/encounters${toQuery(params)}`);
}

// Returns null when the encounter does not exist (404) instead of throwing
export async function getEncounter(encounterId: number): Promise<EncounterDetail | null> {
    try {
        return await getJson<EncounterDetail>(`/encounters/${encounterId}`);
    } catch (error) {
        if (error instanceof Error && error.message.startsWith("404")) {
            return null;
        }
        throw error;
    }
}

export function getCareQueue(params: CareQueueParams = {}): Promise<CareQueueItem[]> {
    return getJson<CareQueueItem[]>(`/care-queue${toQuery(params)}`);
}
