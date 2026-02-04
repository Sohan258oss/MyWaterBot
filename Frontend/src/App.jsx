import { useState, useRef, useEffect } from "react";
import GroundwaterMap from "./GroundwaterMap";
import WebGLWaves from "./components/WebGLWaves";
import MapLegend from "./components/MapLegend";
import { Bar, Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend
} from "chart.js";
import "./App.css";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend);

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

    const apiBase = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
      ? "http://localhost:8000"
      : "https://ingres-api.onrender.com";

    try {
      const response = await fetch(`${apiBase}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, stream: true })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      // Initialize bot message
      const botMessageId = messages.length + 1;
      setMessages((m) => [
        ...m,
        {
          type: "bot",
          text: "",
          chartData: [],
          visualType: null,
          visualData: null,
          imageUrl: null,
          showLegend: false,
          suggestions: []
        }
      ]);

      let accumulatedText = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;

          const jsonStr = part.substring(6);
          try {
            const data = JSON.parse(jsonStr);

            if (data.t) {
              accumulatedText += data.t;
              setMessages((m) => {
                const newMessages = [...m];
                newMessages[newMessages.length - 1].text = accumulatedText;
                return newMessages;
              });
            } else if (data.m) {
              setMessages((m) => {
                const newMessages = [...m];
                const last = newMessages[newMessages.length - 1];
                last.chartData = data.m.chartData || [];
                last.visualType = data.m.visualType || null;
                last.visualData = data.m.visualData || null;
                last.imageUrl = data.m.imageUrl || null;
                last.showLegend = data.m.showLegend || false;
                last.suggestions = data.m.suggestions || [];
                return newMessages;
              });
            }
          } catch (e) {
            console.error("Error parsing stream chunk", e, "jsonStr:", jsonStr);
          }
        }
      }
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
                    {m.showLegend && (
                      <div className="chat-legend-wrapper">
                        <MapLegend />
                      </div>
                    )}
                  </div>
                )}

                {m.visualType === "status_card" && m.visualData && (
                  <div className="status-card">
                    <div className="status-header">
                      <h3>{m.visualData.name}</h3>
                      <span className={`category-badge ${m.visualData.category.toLowerCase().replace(" ", "-")}`}>
                        {m.visualData.category}
                      </span>
                    </div>
                    <div className="status-grid">
                      <div className="status-item">
                        <label>Extraction</label>
                        <span>{m.visualData.extraction}%</span>
                      </div>
                      <div className="status-item">
                        <label>Trend</label>
                        <span>{m.visualData.trend}</span>
                      </div>
                    </div>
                    <div className="status-info">
                      <p><strong>Cause:</strong> {m.visualData.mainCause}</p>
                      <p><strong>Risk:</strong> {m.visualData.topRisk}</p>
                    </div>
                    <div className="status-action">
                      <strong>Recommended Action:</strong> {m.visualData.recommendedAction}
                    </div>
                  </div>
                )}

                {m.visualType === "comparison_bars" && m.visualData && (
                  <div className="comparison-container">
                    <h3>Regional Comparison</h3>
                    <div className="comparison-bars-list">
                      {m.visualData.map((d, di) => (
                        <div key={di} className="comparison-bar-row">
                          <div className="bar-label">{d.name}</div>
                          <div className="bar-wrapper">
                            <div
                              className={`bar-fill ${d.category.toLowerCase().replace(" ", "-")}`}
                              style={{ width: `${Math.min(d.extraction, 100)}%` }}
                            ></div>
                            <span className="bar-value">{d.extraction}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {m.visualType === "risk_alert" && m.visualData && (
                  <div className="risk-alert-card">
                    <div className="alert-header">
                      <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" strokeWidth="2" fill="none">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                        <line x1="12" y1="9" x2="12" y2="13"></line>
                        <line x1="12" y1="17" x2="12.01" y2="17"></line>
                      </svg>
                      <h4>Water Quality Alert</h4>
                    </div>
                    <div className="alert-content">
                      <p><strong>Contaminants:</strong> {m.visualData.contaminantList.join(", ")}</p>
                      <p>{m.visualData.healthRisk}</p>
                    </div>
                    <div className="alert-footer">
                      <strong>Suggested Mitigation:</strong> {m.visualData.suggestedMitigation}
                    </div>
                  </div>
                )}

                {m.visualType === "trend_line" && m.visualData && (
                  <div className="chart-card trend-card">
                    <h3>{m.visualData.name} Extraction Trend</h3>
                    <div className="chart-container">
                      <Line
                        data={{
                          labels: m.visualData.labels,
                          datasets: [{
                            label: "Extraction (%)",
                            data: m.visualData.values,
                            fill: false,
                            borderColor: "#011627",
                            backgroundColor: "#011627",
                            tension: 0.3,
                            pointRadius: 6,
                            pointHoverRadius: 8
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: {
                            legend: { display: false }
                          },
                          scales: {
                            y: {
                              beginAtZero: false,
                              ticks: { callback: (val) => `${val}%` }
                            }
                          }
                        }}
                      />
                    </div>
                    <div className={`trend-diagnostic ${m.visualData.diagnostic}`}>
                      Status: {m.visualData.diagnostic.charAt(0).toUpperCase() + m.visualData.diagnostic.slice(1)}
                    </div>
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
                                  ? "rgba(46, 204, 113, 0.85)"
                                  : d.extraction <= 100
                                  ? "rgba(241, 196, 15, 0.85)"
                                  : "rgba(231, 76, 60, 0.85)"
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
                          animation: {
                            duration: 2000,
                            easing: 'easeOutQuart'
                          },
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
