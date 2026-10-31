import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

// Firebase web settings identify the project and are public by design.
const app = initializeApp({
  apiKey: "AIzaSyAwFvPsniNAXLdhDMurBdqstwOsiN3IxPg",
  authDomain: "grocery-app-71cfd.firebaseapp.com",
  projectId: "grocery-app-71cfd",
  appId: "1:182626729648:web:98fd203a180ae6101e4575",
});

/** Opens Google's own sign-in window and returns proof of the account for our server. */
export async function googleIdToken(): Promise<string> {
  const result = await signInWithPopup(getAuth(app), new GoogleAuthProvider());
  return result.user.getIdToken();
}
