import { initializeApp, type FirebaseApp } from "firebase/app";
import { getFirestore, type Firestore } from "firebase/firestore";

let _app: FirebaseApp | null = null;
let _db: Firestore | null = null;

export function getDb(): Firestore {
  if (_db) return _db;

  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;

  console.log("[SnoopLog] Firebase init — apiKey:", apiKey ? "set" : "MISSING", "projectId:", projectId ?? "MISSING");

  if (!apiKey || !projectId) {
    throw new Error(
      `Firebase config missing: apiKey=${apiKey ? "set" : "MISSING"}, projectId=${projectId ? "set" : "MISSING"}`,
    );
  }

  _app = initializeApp({ apiKey, projectId });
  _db = getFirestore(_app);
  console.log("[SnoopLog] Firestore initialized successfully for project:", projectId);
  return _db;
}
