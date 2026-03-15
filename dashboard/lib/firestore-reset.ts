import { getDb } from "./firebase";
import {
  collection,
  getDocs,
  writeBatch,
  doc,
  deleteField,
} from "firebase/firestore";

const COLLECTIONS = [
  "snooplog-logs",
  "snooplog-incidents",
  "snooplog-agent-calls",
];

const STATS_COLLECTION = "snooplog-stats";
const STATS_DOC = "current";

/**
 * Delete all documents across all SnoopLog Firestore collections
 * and reset the stats counters to zero.
 *
 * Firestore batches are limited to 500 operations, so we chunk.
 */
export async function resetFirestore(): Promise<void> {
  const db = getDb();

  for (const name of COLLECTIONS) {
    const snap = await getDocs(collection(db, name));
    const chunks: typeof snap.docs[] = [];
    for (let i = 0; i < snap.docs.length; i += 450) {
      chunks.push(snap.docs.slice(i, i + 450));
    }
    for (const chunk of chunks) {
      const batch = writeBatch(db);
      for (const d of chunk) {
        batch.delete(d.ref);
      }
      await batch.commit();
    }
  }

  // Reset stats document to zeroes
  const statsRef = doc(db, STATS_COLLECTION, STATS_DOC);
  const batch = writeBatch(db);
  batch.set(statsRef, {
    logs_scored: 0,
    triaged_batches: 0,
    incidents_raised: 0,
    tool_calls: 0,
    logs_suppressed: 0,
  });
  await batch.commit();
}
