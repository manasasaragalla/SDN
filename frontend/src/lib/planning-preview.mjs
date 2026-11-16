const STORAGE_KEY = "intentflow.latest-planning-preview.v1";
const CHANGE_EVENT = "intentflow:planning-preview";

/**
 * @typedef {{
 *   naturalLanguage: string,
 *   savedAt: string,
 *   response: import("../types/api").IntentPreviewResponse
 * }} StoredPlanningPreview
 */

/**
 * @param {string} naturalLanguage
 * @param {import("../types/api").IntentPreviewResponse} response
 */
export function savePlanningPreview(
  naturalLanguage,
  response,
) {
  if (typeof window === "undefined") return false;
  const value = {
    naturalLanguage,
    savedAt: new Date().toISOString(),
    response,
  };
  const raw = JSON.stringify(value);
  lastRaw = raw;
  lastValue = value;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, raw);
    storageFallback = false;
  } catch {
    storageFallback = true;
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return !storageFallback;
}

export function clearPlanningPreview() {
  if (typeof window === "undefined") return;
  lastRaw = null;
  lastValue = null;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    storageFallback = false;
  } catch {
    storageFallback = true;
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

let lastRaw;
let lastValue = null;
let storageFallback = false;

/** @returns {StoredPlanningPreview | null} */
export function getPlanningPreviewSnapshot() {
  if (typeof window === "undefined") return null;
  let raw;
  try {
    raw = window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return lastValue;
  }
  if (storageFallback) return lastValue;
  if (raw === lastRaw) return lastValue;
  lastRaw = raw;
  if (!raw) {
    lastValue = null;
    return null;
  }

  try {
    const value = JSON.parse(raw);
    if (
      typeof value.naturalLanguage !== "string"
      || typeof value.savedAt !== "string"
      || !value.response
      || !value.response.canonical_intent
    ) {
      lastValue = null;
    } else {
      lastValue = value;
    }
  } catch {
    lastValue = null;
  }
  return lastValue;
}

/** @param {() => void} onChange */
export function subscribePlanningPreview(onChange) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
