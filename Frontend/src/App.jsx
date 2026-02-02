import { useState, useRef, useEffect } from "react";
import GroundwaterMap from "./GroundwaterMap";
import WebGLWaves from "./components/WebGLWaves";
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
  const [displayedMain, setDisplayedMain] = useState("");
  const [displayedSuffix, setDisplayedSuffix] = useState("");
  const [isRetreating, setIsRetreating] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const mainText = "MyWaterBot";
    const suffixText = " - AI Groundwater Assistant";
    let i = 0;
    let typeSuffixInterval;

    const typeMainInterval = setInterval(() => {
      if (i < mainText.length) {
        setDisplayedMain(mainText.slice(0, i + 1));
        i++;
      } else {
        clearInterval(typeMainInterval);
        let j = 0;
        typeSuffixInterval = setInterval(() => {
          if (j < suffixText.length) {
            setDisplayedSuffix(suffixText.slice(0, j + 1));
            j++;
          } else {
            clearInterval(typeSuffixInterval);
            setTimeout(() => {
              setIsRetreating(true);
            }, 1500);
          }
        }, 40);
      }
    }, 60);

    return () => {
      clearInterval(typeMainInterval);
      clearInterval(typeSuffixInterval);
    };
  }, []);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (explicitMsg = null) => {
    const userMsg = typeof explicitMsg === "string" ? explicitMsg : input;
    if (!userMsg.trim()) return;

    if (userMsg.toLowerCase().includes("show india map")) {
      setShowMap(true);
      return;
    }

    setMessages((m) => [...m, { type: "user", text: userMsg }]);
    setInput("");
    setLoading(true);

    const apiBase = window.location.hostname === "localhost"
      ? "http://localhost:8000"
      : "https://ingres-api.onrender.com";

    try {
      const res = await fetch(`${apiBase}/ask`, {
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
          chartData: data.chartData || [],
          imageUrl: data.imageUrl || null,
          suggestions: data.suggestions || []
        }
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { type: "bot", text: "Backend not responding. Please check your connection." }
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

  const formatText = (text) => {
    // Remove Markdown-style formatting: **, ###, etc.
    return text
      .replace(/\*\*(.*?)\*\*/g, "$1") // Bold
      .replace(/###\s*(.*?)(\n|$)/g, "$1$2") // Headers
      .replace(/\n\n/g, "\n") // Reduce extra spacing
      .trim();
  };

  return (
    <div className="app">
      <WebGLWaves />
      <header className="header">
        <div className="header-title">
          <span className="brand-main">{displayedMain}</span>
          <span className={`brand-suffix ${isRetreating ? "retreat" : ""}`}>
            {displayedSuffix}
          </span>
        </div>
        <button
          className="map-toggle-btn"
          onClick={() => setShowMap(!showMap)}
          aria-label={showMap ? "Back to Chat" : "View Groundwater Map"}
        >
          {showMap ? "Back to Chat" : "View India Map"}
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
                  <h2>Hello! I am the MyWaterBot AI Chatbot</h2>
                  <p>
                    I am here to help you analyze and understand <b>India's Groundwater Resources</b>.
                    I can provide data, explain causes of water stress, and generate comparison charts.
                  </p>

                  <div className="suggestions-box">
                    <p><b>Try asking me:</b></p>
                    <div className="suggestions-list">
                      {[
                        "Compare Punjab and Bihar",
                        "Why is Rajasthan stressed?",
                        "Check water quality in Rajasthan"
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
                        View India Map with Levels
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* --- CHAT MESSAGES --- */}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.type}`}>
                <div className="bubble">
                  {m.type === "bot" ? formatText(m.text) : m.text}
                </div>

                {m.type === "bot" && m.imageUrl && (
                  <div className="bot-image-container">
                    <img src={m.imageUrl} alt="Relevant groundwater visual" className="bot-image" />
                  </div>
                )}

                {m.type === "bot" && m.suggestions && m.suggestions.length > 0 && (
                  <div className="bot-suggestions">
                    {m.suggestions.map((s, si) => (
                      <button
                        key={si}
                        className="suggestion-btn small"
                        onClick={() => sendMessage(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}

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
                              label: "Extraction (%)",
                              data: m.chartData.map((d) => d.extraction),
                              backgroundColor: m.chartData.map((d) =>
                                d.extraction <= 70
                                  ? "rgba(46, 204, 113, 0.8)"
                                  : d.extraction <= 100
                                  ? "rgba(241, 196, 15, 0.8)"
                                  : "rgba(231, 76, 60, 0.8)"
                              ),
                              borderColor: m.chartData.map((d) =>
                                d.extraction <= 70 ? "#27ae60" : d.extraction <= 100 ? "#f39c12" : "#c0392b"
                              ),
                              borderWidth: 1,
                              borderRadius: 8,
                              hoverBackgroundColor: m.chartData.map((d) =>
                                d.extraction <= 70 ? "#2ecc71" : d.extraction <= 100 ? "#f1c40f" : "#e74c3c"
                              )
                            }
                          ]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: {
                            legend: { display: false },
                            tooltip: {
                              backgroundColor: "rgba(0, 0, 0, 0.8)",
                              padding: 12,
                              titleFont: { size: 14 },
                              bodyFont: { size: 13 },
                              displayColors: false
                            }
                          },
                          scales: {
                            y: {
                              beginAtZero: true,
                              max: Math.max(...m.chartData.map(d => d.extraction)) > 100 ? undefined : 110,
                              grid: { color: "rgba(0, 0, 0, 0.05)" },
                              ticks: { callback: (val) => `${val}%` }
                            },
                            x: {
                              grid: { display: false }
                            }
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
                <div className="bubble">
                  <div className="water-loader-container">
                    <div className="water-loader"></div>
                    <span className="loading-text">Analyzing groundwater data...</span>
                  </div>
                </div>
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
          className="send-btn"
          onClick={sendMessage}
          disabled={loading}
          aria-label={loading ? "Sending message" : "Send message"}
        >
          {loading ? (
            <span className="btn-loader"></span>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="19" x2="12" y2="5"></line>
              <polyline points="5 12 12 5 19 12"></polyline>
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
