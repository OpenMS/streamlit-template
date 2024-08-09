import { Streamlit, RenderData } from "streamlit-component-lib"

declare var klaro: any;

declare global {
    interface Window {
        klaro: any;
    }
}


// Async function to wait for the Klaro manager
async function waitForKlaroManager (maxWaitTime: number = 5000, interval: number = 100): Promise<any> {
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
        const klaroManager = getKlaroManager()
        if (klaroManager) {
            return klaroManager;
        }
        await new Promise(resolve => setTimeout(resolve, interval));
    }

    throw new Error("Klaro manager did not become available within the allowed time.");
}

// Helper function to handle unknown errors
function handleError(error: unknown): void {
    if (error instanceof Error) {
        console.error("Error:", error.message);
    } else {
        console.error("Unknown error:", error);
    }
}

// Tracking was accepted
async function onAcceptCallback(): Promise<void> {
    try {
        const manager = await waitForKlaroManager();
        if (manager.confirmed) {
            Streamlit.setComponentValue("accepted");
        }
    } catch (error) {
        handleError(error);
    }
}

// Tracking was declined
async function onDeclineCallback(): Promise<void> {
    try {
        const manager = await waitForKlaroManager();
        if (manager.confirmed) {
            Streamlit.setComponentValue("declined");
        }
    } catch (error) {
        handleError(error);
    }
}

function onChange(): void {
    changed = true;
}

interface KlaroService {
    name: string;
    cookies: RegExp[];
    purposes: string[];
    onAccept: () => void;
    onDecline: () => void;
}

interface KlaroConfig {
    mustConsent: boolean;
    acceptAll: boolean;
    services: KlaroService[];
}

interface klaroManager {
    confirmed : boolean
}

const klaroConfig = {
    mustConsent: true,
    acceptAll: true,
    services: [
        {
            // In GTM, you should define a custom event trigger named `klaro-google-analytics-accepted` which should trigger the Google Analytics integration.
            name: 'google-analytics',
            cookies: [
                /^_ga(_.*)?/ // we delete the Google Analytics cookies if the user declines its use
            ],
            purposes: ['analytics'],
            onAccept: onAcceptCallback,
            onDecline: onDeclineCallback,
        },
    ]
};

let rendered = false;
let changed = false;

function onRender(event: Event): void {
    if (rendered) {
        return
    }
    rendered = true
    // Create a new script element
    var script = document.createElement('script');

    // Set the necessary attributes
    script.defer = true;
    script.type = 'application/javascript';
    script.src = 'https://cdn.kiprotect.com/klaro/v0.7/klaro.js';

    // Set the data-config attribute
    script.setAttribute('data-config', 'klaroConfig');

    script.onload = function() {
        const klaroManager = getKlaroManager();
        if (klaroManager) {
            console.log("Klaro loaded successfully");
            console.log(klaroManager)
        } else {
            console.error("Failed to initialize Klaro manager");
        }
    };

    // Append the script to the head or body
    document.head.appendChild(script); 
}

// Function to safely access the Klaro manager
function getKlaroManager() : klaroManager {
    return window.klaro?.getManager ? window.klaro.getManager() : null;
}

// This will make klaroConfig globally accessible
(window as any).klaroConfig = klaroConfig;

// Attach our `onRender` handler to Streamlit's render event.
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender)

// Tell Streamlit we're ready to start receiving data. We won't get our
// first RENDER_EVENT until we call this function.
Streamlit.setComponentReady();

// Finally, tell Streamlit to update our initial height. We omit the
// `height` parameter here to have it default to our scrollHeight.
Streamlit.setFrameHeight(1000);

