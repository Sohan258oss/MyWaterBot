import { useState, useEffect, useRef } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

function App() {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState([]) // Stores the whole chat
  const scrollRef = useRef(null)

  // Auto-scroll to the bottom when a new message arrives
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg = { role: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = input;
    setInput("");

    try {
      const res = await fetch("https://ingres-api.onrender.com/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: currentInput })
      })
      const data = await res.json()
      
      const botMsg = { 
        role: 'bot', 
        text: data.text, 
        chart: data.chartData 
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'bot', text: "Connection error!" }]);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#f0f9ff', fontFamily: 'sans-serif' }}>
      {/* Header */}
      <div style={{ padding: '15px', backgroundColor: '#0284c7', color: 'white', textAlign: 'center', boxShadow: '0 2px 5px rgba(0,0,0,0.1)', borderBottom: '4px solid #0ea5e9' }}>
        <h2 style={{ margin: 0 }}>💧 INGRES AI Assistant</h2>
      </div>

      {/* Chat Window */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: '20px', textAlign: m.role === 'user' ? 'right' : 'left' }}>
            <div style={{ 
              display: 'inline-block', 
              padding: '12px 18px', 
              borderRadius: '15px', 
              maxWidth: '70%',
              backgroundColor: m.role === 'user' ? '#0284c7' : 'white',
              color: m.role === 'user' ? 'white' : '#1e293b',
              boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
            }}>
              <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
              
              {/* Show chart inside the bot bubble if it exists */}
              {m.chart && m.chart.length > 0 && (
                <div style={{ width: '300px', height: '220px', marginTop: '15px', backgroundColor: '#f8fafc', padding: '10px', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={m.chart} margin={{ top: 5, right: 5, left: -30, bottom: 5 }}>
                      <XAxis dataKey="name" hide />
                      <YAxis tick={{fontSize: 12}} />
                      <Tooltip 
                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 2px 5px rgba(0,0,0,0.1)' }}
                        cursor={{fill: 'rgba(0,0,0,0.05)'}}
                      />
                      <Bar dataKey="extraction" radius={[4, 4, 0, 0]}>
                        {m.chart.map((entry, index) => (
                          <Cell 
                            key={`cell-${index}`} 
                            fill={entry.extraction > 100 ? '#ef4444' : '#22c55e'} 
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p style={{ fontSize: '10px', color: '#64748b', textAlign: 'center', marginTop: '5px' }}>
                    Red: Over-exploited | Green: Safe/Critical
                  </p>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={scrollRef} />
      </div>

      {/* Input Bar */}
      <div style={{ padding: '20px', backgroundColor: 'white', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', alignItems: 'center' }}>
        <input 
          style={{ flex: 1, padding: '12px', borderRadius: '8px', border: '1px solid #cbd5e1', outline: 'none', fontSize: '16px' }}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSend()}
          placeholder="e.g. Compare Jaipur and Gurugram..."
        />
        <button 
          onClick={handleSend} 
          style={{ padding: '12px 25px', backgroundColor: '#0284c7', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          Send
        </button>
      </div>
    </div>
  )
}

export default App