import { useState, useRef, useEffect } from "react";
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
  const bottomRef = useRef(null);

  // Auto-scroll to bottom whenever a new message or chart arrives
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg = input;
    setMessages((m) => [...m, { type: "user", text: userMsg }]);
    setInput("");
    setLoading(true);

    try {
      // NOTE: Update this URL to your Render Backend URL before you leave tomorrow!
      const res = await fetch("http://127.0.0.1:8000/ask", {
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
        { type: "bot", text: "❌ Backend not responding." }
      ]);
    }

    setLoading(false);
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
        💧 INGRES AI Groundwater Assistant
      </header>

      <div className="chat">
        
        {/* --- WELCOME BOX SECTION --- */}
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
                <ul>
                  <li>"Compare usage in Punjab and Bihar"</li>
                  <li>"Why is Rajasthan over-exploited?"</li>
                  <li>"Overall situation in India"</li>
                </ul>
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
                        y: {
                          beginAtZero: true
                        }
                      }
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="msg bot">
            <div className="bubble loading">Analyzing groundwater data…</div>
          </div>
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
        />
        <button onClick={sendMessage} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  );
}