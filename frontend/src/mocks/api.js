// Mock backend for Phase 1–2. Every function here mirrors the shape of a
// real fetch() call — same async signature, same thrown-error-on-failure
// pattern — so swapping to the FastAPI backend later is a one-file change
// in src/lib/api.js, not a rewrite of any component.

import hotspotsData from "./hotspots.json";

const STORAGE_KEY = "citizenpriority_mock_submissions";

function readStore() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? [];
  } catch {
    return [];
  }
}

function writeStore(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function generateTicketNumber() {
  const year = new Date().getFullYear();
  const random = Math.floor(10000 + Math.random() * 90000);
  return `CP-${year}-${random}`;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mirrors POST /api/submit.
 * @param {FormData} formData - name, constituency, type, language, and
 *   either `text`, or a `file` blob (for voice/photo).
 * @returns {Promise<{ticket: string, status: string}>}
 */
export async function mockSubmitReport(formData) {
  await delay(900 + Math.random() * 600);

  // Simulate an occasional server hiccup so the UI's error state gets
  // exercised during testing — remove this once a real backend is wired up.
  if (Math.random() < 0.05) {
    throw new Error("network_error");
  }

  const ticket = generateTicketNumber();
  const record = {
    ticket,
    name: formData.get("name") || null,
    constituency: formData.get("constituency"),
    type: formData.get("type"),
    language: formData.get("language"),
    text: formData.get("text") || null,
    fileName: formData.get("file")?.name || null,
    status: "received",
    submitted_at: new Date().toISOString(),
  };

  writeStore([...readStore(), record]);

  return { ticket, status: "received" };
}

/**
 * Mirrors GET /api/hotspots?category=&constituency=&from=&to=
 * Filtering is done here to mimic what the real backend will do server-side
 * — the component just passes a filters object and gets back a filtered
 * FeatureCollection, no client-side filtering logic to port over later.
 * @param {{category?: string, constituency?: string, from?: string, to?: string}} filters
 */
export async function mockGetHotspots(filters = {}) {
  await delay(500 + Math.random() * 400);

  const features = hotspotsData.features.filter((f) => {
    const p = f.properties;
    if (filters.category && p.category !== filters.category) return false;
    if (filters.constituency && p.constituency !== filters.constituency) return false;
    if (filters.from && p.last_report_date < filters.from) return false;
    if (filters.to && p.last_report_date > filters.to) return false;
    return true;
  });

  return { type: "FeatureCollection", features };
}
