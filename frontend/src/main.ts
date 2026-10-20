import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";

// OpenMS needs a cross-origin isolated page (threads). Where the server does
// not send the headers, a service worker adds them; it takes over after one
// reload.
async function isolate(): Promise<boolean> {
  if (crossOriginIsolated || !("serviceWorker" in navigator) || !isSecureContext) return true;
  try {
    await navigator.serviceWorker.register(`${import.meta.env.BASE_URL}coi-sw.js`);
    await navigator.serviceWorker.ready;
  } catch {
    return true;
  }
  if (sessionStorage.getItem("coi-reload")) return true; // reloaded once already: go on without
  sessionStorage.setItem("coi-reload", "1");
  location.reload();
  return false;
}

if (await isolate()) {
  sessionStorage.removeItem("coi-reload");
  mount(App, { target: document.getElementById("app")! });
}
