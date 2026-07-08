import { mockSubmitReport, mockGetHotspots, mockGetPriorities } from "../mocks/api";

// Once the FastAPI backend has a real URL, set VITE_API_BASE_URL in a
// .env.local file and this switches over automatically — no component
// changes needed, since submitReport() is the only thing pages call.
const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function submitReport(formData) {
  if (!BASE_URL) {
    return mockSubmitReport(formData);
  }

  const response = await fetch(`${BASE_URL}/api/submit`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`submit_failed_${response.status}`);
  }

  return response.json();
}

export async function getHotspots(filters = {}) {
  if (!BASE_URL) {
    return mockGetHotspots(filters);
  }

  const params = new URLSearchParams(
    Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
  );
  const response = await fetch(`${BASE_URL}/api/hotspots?${params}`);

  if (!response.ok) {
    throw new Error(`hotspots_failed_${response.status}`);
  }

  return response.json();
}

export async function getPriorities() {
  if (!BASE_URL) {
    return mockGetPriorities();
  }

  const response = await fetch(`${BASE_URL}/api/priorities`);

  if (!response.ok) {
    throw new Error(`priorities_failed_${response.status}`);
  }

  return response.json();
}
