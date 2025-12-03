import { Streamlit, RenderData } from "streamlit-component-lib"

// Define service
type Service = {
    name: string;
    purposes: string[];
    onAccept: () => Promise<void>;
    onDecline: () => Promise<void>;
    cookies?: (string | RegExp)[];
};

// Defines the configuration for Klaro
let klaroConfig: {
    mustConsent: boolean;
    acceptAll: boolean;
    services: Service[];
} = {
    mustConsent: true,
    acceptAll: true,
    services: []
};

// This will make klaroConfig globally accessible
(window as any).klaroConfig = klaroConfig

// Klaro creates global variable for access to manager
declare global {
    interface Window {
        klaro: any
    }
}

// The confirmed field in the Klaro Manager shows if the callback is 
// based on user generated data
interface klaroManager {
    confirmed : boolean
}

// Function to safely access the Klaro manager
function getKlaroManager() : klaroManager {
    return window.klaro?.getManager ? window.klaro.getManager() : null
}

// Waits until Klaro Manager is available
async function waitForKlaroManager (maxWaitTime: number = 5000, interval: number = 100): Promise<any> {
    const startTime = Date.now()
    while (Date.now() - startTime < maxWaitTime) {
        const klaroManager = getKlaroManager()
        if (klaroManager) {
            return klaroManager
        }
        await new Promise(resolve => setTimeout(resolve, interval))
    }
    throw new Error("Klaro manager did not become available within the allowed time.")
}

// Helper function to handle unknown errors
function handleError(error: unknown): void {
    if (error instanceof Error) {
        console.error("Error:", error.message)
    } else {
        console.error("Unknown error:", error)
    }
}

// Tracking was accepted
async function callback(): Promise<void> {
    try {
        const manager = await waitForKlaroManager()
        if (manager.confirmed) {
            let return_vals :  Record<string, boolean> = {}
            for (const service of klaroConfig.services) {
                return_vals[service.name] = manager.getConsent(service.name)
            }            
            Streamlit.setComponentValue(return_vals)
        }
    } catch (error) {
        handleError(error)
    }
}

// Stores if the component has been rendered before
let rendered = false

function onRender(event: Event): void {
    // Klaro does not work if embedded multiple times
    if (rendered) {
        return
    }
    rendered = true

    const data = (event as CustomEvent<RenderData>).detail

    if (data.args['google_analytics']) {
        klaroConfig.services.push(
            {
                name: 'google-analytics',
                cookies: [
                    /^_ga(_.*)?/ // we delete the Google Analytics cookies if the user declines its use
                ],
                purposes: ['analytics'],
                onAccept: callback,
                onDecline: callback,
            }
        )
    }
    if (data.args['piwik_pro']) {
        klaroConfig.services.push(
            {
                name: 'piwik-pro',
                purposes: ['analytics'],
                onAccept: callback,
                onDecline: callback,
            }
        )
    }

    // Create a new script element
    var script = document.createElement('script')

    // Set the necessary attributes
    script.defer = true
    script.type = 'application/javascript'
    script.src = 'https://cdn.kiprotect.com/klaro/v0.7/klaro.js'

    // Set the klaro config
    script.setAttribute('data-config', 'klaroConfig')

    // Append the script to the head or body
    document.head.appendChild(script)

}

// Attach our `onRender` handler to Streamlit's render event.
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender)

// Tell Streamlit we're ready to start receiving data. We won't get our
// first RENDER_EVENT until we call this function.
Streamlit.setComponentReady()

// Finally, tell Streamlit to update the initial height.
Streamlit.setFrameHeight(1000)

