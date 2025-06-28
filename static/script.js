document.addEventListener("DOMContentLoaded", () => {
    const messageInput = document.getElementById("message-input");
    const sendButton = document.getElementById("send-button");

    const panels = {
        intermediary: {
            speech: document.getElementById("intermediary-speech")
        },
        bot_alpha: {
            thought: document.getElementById("bot-alpha-thought"),
            speech: document.getElementById("bot-alpha-speech")
        },
        bot_bravo: {
            thought: document.getElementById("bot-bravo-thought"),
            speech: document.getElementById("bot-bravo-speech")
        }
    };

    let ws;

    function connect() {
        ws = new WebSocket(`ws://${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("Connected to WebSocket");
            sendButton.disabled = false;
            sendButton.textContent = "Start Debate";
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            const { target_panel, message_type, content } = message;

            const targetElement = panels[target_panel]?.[message_type];
            if (targetElement) {
                // For streaming, we replace the content.
                targetElement.textContent = content;
                targetElement.scrollTop = targetElement.scrollHeight;
            }
        };

        ws.onclose = () => {
            console.log("WebSocket disconnected. Reconnecting...");
            sendButton.disabled = true;
            sendButton.textContent = "Connecting...";
            setTimeout(connect, 3000); // Attempt to reconnect every 3 seconds
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            ws.close();
        };
    }

    const startDebate = () => {
        const messageContent = messageInput.value;
        if (messageContent.trim() !== "" && ws.readyState === WebSocket.OPEN) {
            // Clear all panels for the new debate
            Object.values(panels).forEach(panel => {
                Object.values(panel).forEach(element => {
                    element.textContent = "";
                });
            });

            ws.send(JSON.stringify({ content: messageContent }));
            messageInput.value = "";
        }
    };

    sendButton.addEventListener("click", startDebate);
    messageInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            startDebate();
        }
    });

    // Initial connection
    connect();
});