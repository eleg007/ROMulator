// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-app.js";

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyA09v1eEdM230nXKrIsIjOuDk0zsNyA7hg",
    authDomain: "cubanrev.firebaseapp.com",
    projectId: "cubanrev",
    storageBucket: "cubanrev.firebasestorage.app",
    messagingSenderId: "332879055074",
    appId: "1:332879055074:web:bdeb8121f407e8fc1f76bb"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

import { startGame } from "./game.js";

const PIN = "194756"; // The secret PIN to unlock the unblocker
const GAME_PIN = "GAME123"; // The secret PIN to start the game

const searchBar = document.getElementById("searchBar");
const contentDiv = document.getElementById("content");
const unblockerDiv = document.getElementById("unblocker");
const urlInput = document.getElementById("urlInput");
const goButton = document.getElementById("goButton");
const proxyFrame = document.getElementById("proxyFrame");
const gameContainer = document.getElementById("gameContainer"); // Reference to game container
const headerTitle = document.querySelector("header h1 a"); // Assuming the 'a' tag inside h1 for the panic button

let lastClickTime = 0;
let clickCount = 0;
const TRIPLE_CLICK_INTERVAL = 500; // ms

if (headerTitle) {
    headerTitle.addEventListener('click', (event) => {
        const currentTime = new Date().getTime();
        if (currentTime - lastClickTime < TRIPLE_CLICK_INTERVAL) {
            clickCount++;
        } else {
            clickCount = 1;
        }
        lastClickTime = currentTime;

        if (clickCount === 3) {
            event.preventDefault(); // Prevent default link behavior for triple click
            const url = new URL(window.location.href);
            url.searchParams.set("v", new Date().getTime()); // Add cache-busting parameter
            window.location.href = url.toString(); // Reload page
            clickCount = 0; // Reset click count
        }
    });
}

// Cache-busting logic
let loadCount = parseInt(localStorage.getItem("pageLoadCount") || "0", 10);
loadCount++;
localStorage.setItem("pageLoadCount", loadCount);

if (loadCount % 3 === 0) {
    const url = new URL(window.location.href);
    // Check if a cache-busting parameter is already present to prevent infinite reloads
    if (!url.searchParams.has("v")) {
        url.searchParams.set("v", new Date().getTime());
        window.location.href = url.toString();
    }
}

searchBar.addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        const query = searchBar.value.trim();
        if (query === PIN) {
            contentDiv.classList.add("hidden");
            gameContainer.classList.add("hidden"); // Hide game if visible
            unblockerDiv.classList.remove("hidden");
            searchBar.value = ""; // Clear the search bar
            searchBar.placeholder = "Unblocker Activated!";
        } else if (query === GAME_PIN) {
            contentDiv.classList.add("hidden");
            unblockerDiv.classList.add("hidden"); // Hide unblocker if visible
            gameContainer.classList.remove("hidden");
            searchBar.value = ""; // Clear the search bar
            searchBar.placeholder = "Game On!";
            startGame('gameContainer'); // Start the game
        } else {
            alert("No result. Feature coming soon.");
        }
    }
});

// Enhanced proxy loading with error handling and data optimization
goButton.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) {
        alert("Please enter a URL to unblock.");
        return;
    }
    
    // Basic URL validation: ensure it starts with http:// or https://
    let formattedUrl = url;
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        formattedUrl = "https://" + url; // Default to https
    }
    
    // Validate URL format
    try {
        new URL(formattedUrl);
    } catch (e) {
        alert("Invalid URL format. Please enter a valid website address.");
        return;
    }
    
    // FIX: Use btoa() to encode, but DON'T use encodeURIComponent on the base64 string
    // The base64 string is already URL-safe
    const encodedUrl = btoa(formattedUrl);
    
    // Set iframe src to Firebase proxy endpoint
    proxyFrame.src = `/proxy?url=${encodedUrl}`;
    
    // Show loading indicator
    proxyFrame.style.opacity = "0.5";
    
    // Clear loading indicator when loaded
    proxyFrame.addEventListener('load', function onLoad() {
        proxyFrame.style.opacity = "1";
        proxyFrame.removeEventListener('load', onLoad);
    }, { once: true });
    
    // Handle errors
    proxyFrame.addEventListener('error', function onError() {
        alert("Failed to load the website. The site may be blocking access or your proxy may be down.");
        proxyFrame.removeEventListener('error', onError);
    }, { once: true });
});

// Allow Enter key in URL input for better UX
urlInput.addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        goButton.click();
    }
});

// Optional: Add iframe message listener for cross-origin communication
window.addEventListener('message', (event) => {
    // Only accept messages from your Firebase domain
    if (event.origin === 'https://cubanrev.firebaseapp.com' || 
        event.origin === window.location.origin) {
        console.log('Received message from proxy:', event.data);
        
        // Handle specific message types if your backend sends them
        if (event.data.type === 'error') {
            alert(`Proxy Error: ${event.data.message}`);
        } else if (event.data.type === 'loaded') {
            console.log('Page loaded successfully in proxy');
        }
    }
});
