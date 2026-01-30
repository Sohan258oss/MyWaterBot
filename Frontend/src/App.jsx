import { useState, useRef, useEffect } from "react";
import GroundwaterMap from "./GroundwaterMap";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend
} from "chart.js";
import "./App.css";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export default function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const bottomRef = useRef(null);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (explicitMsg = null) => {
    const userMsg = typeof explicitMsg === "string" ? explicitMsg : input;
    if (!userMsg.trim()) return;

    setMessages((m) => [...m, { type: "user", text: userMsg }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("https://ingres-api.onrender.com/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg })
      });

      const data = await res.json();

      setMessages((m) => [
        ...m,
        {
          type: "bot",
          text: data.text,
          chartData: data.chartData || []
        }
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { type: "bot", text: "❌ Backend not responding. Please check your connection." }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">💧 INGRES AI Groundwater Assistant</div>
        <button
          className="map-toggle-btn"
          onClick={() => setShowMap(!showMap)}
          aria-label={showMap ? "Back to Chat" : "View Groundwater Map"}
        >
          {showMap ? "💬 Back to Chat" : "🗺️ View India Map"}
        </button>
      </header>

      <div className="chat">
        {showMap ? (
          <div className="map-view">
            <GroundwaterMap />
          </div>
        ) : (
          <>
            {/* --- WELCOME BOX --- */}
            {messages.length === 0 && (
              <div className="welcome-container">
                <div className="welcome-box">
                  <h2>👋 Hello! I am the INGRES AI Chatbot</h2>
                  <p>
                    I am here to help you analyze and understand <b>India's Groundwater Resources</b>.
                    I can provide data, explain causes of water stress, and generate comparison charts.
                  </p>

                  <div className="suggestions-box">
                    <p><b>Try asking me:</b></p>
                    <div className="suggestions-list">
                      {[
                        "Compare usage in Punjab and Bihar",
                        "Why is Rajasthan over-exploited?",
                        "Overall situation in India"
                      ].map((s, i) => (
                        <button
                          key={i}
                          className="suggestion-btn"
                          onClick={() => sendMessage(s)}
                        >
                          {s}
                        </button>
                      ))}
                      <button
                        className="suggestion-btn highlight"
                        onClick={() => setShowMap(true)}
                      >
                        🗺️ View India Map with Levels
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* --- CHAT MESSAGES --- */}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.type}`}>
            <div className="bubble">{m.text}</div>

                {m.chartData && m.chartData.length > 0 && (
                  <div className="chart-card">
                    <div className="chart-container">
                      <Bar
                        role="img"
                        aria-label="Groundwater extraction comparison chart"
                        data={{
                          labels: m.chartData.map((d) => d.name),
                          datasets: [
                            {
                              label: "Groundwater Extraction (%)",
                              data: m.chartData.map((d) => d.extraction),
                              backgroundColor: m.chartData.map((d) =>
                                d.extraction <= 70
                                  ? "#2ecc71"
                                  : d.extraction <= 100
                                  ? "#f1c40f"
                                  : "#e74c3c"
                              ),
                              borderRadius: 10
                            }
                          ]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          scales: {
                            y: { beginAtZero: true }
                          }
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* --- LOADING INDICATOR --- */}
            {loading && (
              <div className="msg bot">
                <div className="bubble loading">Analyzing groundwater data...</div>
              </div>
            )}
          </>
        )}

        <div ref={bottomRef} />
      </div>

      {/* --- INPUT AREA --- */}
      <div className="input-box">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask me about India's groundwater..."
          aria-label="Chat message input"
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          aria-label={loading ? "Sending message" : "Send message"}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}