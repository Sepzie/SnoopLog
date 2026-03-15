import { getDb } from "./firebase";
import {
  collection,
  query,
  orderBy,
  limit,
  getDocs,
  doc,
  getDoc,
} from "firebase/firestore";

export async function fetchHistoricalLogs(max = 200) {
  const db = getDb();
  const q = query(
    collection(db, "snooplog-logs"),
    orderBy("timestamp", "desc"),
    limit(max),
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => d.data()).reverse();
}

export async function fetchHistoricalIncidents(max = 50) {
  const db = getDb();
  const q = query(
    collection(db, "snooplog-incidents"),
    orderBy("timestamp", "desc"),
    limit(max),
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => d.data());
}

export async function fetchStats() {
  const db = getDb();
  const ref = doc(db, "snooplog-stats", "current");
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data();
}
