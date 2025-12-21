from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from thefuzz import process, fuzz

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WaterQuery(BaseModel):
    message: str

# Global cache for the Yes/No flow
last_data_cache = {"data": []}

KNOWLEDGE_BASE = {
    "groundwater": "Groundwater is the water found underground in the cracks and spaces in soil, sand and rock.",
    "extraction": "Groundwater extraction is the process of taking water from underground sources for irrigation, drinking, or industrial use.",
    "recharge": "Recharge is the primary method through which water enters an aquifer, usually through rainfall soaking into the ground.",
    "over-exploited": "A region is 'over-exploited' when pumping exceeds the natural rainfall recharge.",
    "safe": "A 'Safe' category means extraction is less than 70% of the available recharge.",
    "critical": "A 'Critical' category means extraction is between 90% and 100% of the resource.",
    "stage": "The 'Stage of Extraction' is the percentage of groundwater used compared to what is available."
}

WHY_MAP = {
    "punjab": "High dependence on groundwater for water-intensive crops like paddy and wheat.",
    "rajasthan": "Low rainfall, arid climate, and high evaporation rates.",
    "delhi": "Urban over-extraction and limited natural recharge zones.",
    "karnataka": "Erratic rainfall and dependence on borewells for agriculture.",
    "tamil nadu": "High urban and agricultural demand with frequent droughts."
}

@app.post("/ask")
async def ask_bot(item: WaterQuery):
    # --- 1. PRE-PROCESSING (Cleaning & Synonyms) ---
    user_input = item.message.strip().lower()
    
    SYNONYMS = {
        "usage": "extraction",
        "withdrawal": "extraction",
        "consumption": "extraction",
        "water use": "extraction",
        "graph": "chart",
        "plot": "chart"
    }
    for k, v in SYNONYMS.items():
        user_input = user_input.replace(k, v)

    # --- 2. YES/NO CHART LOGIC ---
    if user_input in ["yes", "show chart", "give me chart", "yup", "sure", "ok"]:
        if last_data_cache["data"]:
            chart_to_send = last_data_cache["data"]
            last_data_cache["data"] = [] 
            return {"text": "Here is the chart you requested! 📊", "chartData": chart_to_send}
        return {"text": "I don't have any data ready for a chart. What would you like to compare?", "chartData": []}

    # --- 3. IDENTITY & HELP ---
    if any(q in user_input for q in ["what is ingres", "who are you", "help", "how to use"]):
        return {
            "text": "I am the INGRES AI assistant. Try asking 'Compare Punjab and Kerala', 'Which states have the highest usage?', or 'Overall situation in India'.",
            "chartData": []
        }

    # --- 4. INDIA SUMMARY LOGIC ---
    summary_triggers = ["overall", "situation in india", "how bad", "india summary", "summary of india"]
    if any(q in user_input for q in summary_triggers):
        try:
            with sqlite3.connect("./ingres.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT AVG(extraction) FROM assessments")
                national_avg = round(cursor.fetchone()[0], 2)
                cursor.execute("SELECT category, COUNT(*) FROM assessments GROUP BY category")
                cat_counts = cursor.fetchall()
                
                last_data_cache["data"] = [{"name": c[0], "extraction": c[1]} for c in cat_counts if c[0]]
                return {
                    "text": f"Overall, India's average groundwater extraction is **{national_avg}%**. There are many 'Safe' regions, but several areas are 'Critical'. Would you like to see a chart of the national category distribution?",
                    "chartData": []
                }
        except: pass

    # --- 5. DATA QUERIES (Trends, Categories, Multi-State) ---
    found_data = []
    text_prefix = ""

    try:
        with sqlite3.connect("./ingres.db") as conn:
            cursor = conn.cursor()

            # A. Trends/Thresholds
            if any(word in user_input for word in ["top", "highest", "above", "more than", "over-exploited", "critical"]):
                if "above" in user_input or "more than" in user_input:
                    cursor.execute("SELECT state, AVG(extraction) FROM assessments GROUP BY state HAVING AVG(extraction) > 100 ORDER BY AVG(extraction) DESC")
                    text_prefix = "states with extraction above 100%"
                elif "top" in user_input or "highest" in user_input:
                    cursor.execute("SELECT state, AVG(extraction) FROM assessments GROUP BY state ORDER BY AVG(extraction) DESC LIMIT 5")
                    text_prefix = "the top 5 states by extraction"
                else:
                    cat = "Over-Exploited" if "over" in user_input else "Critical"
                    cursor.execute("SELECT state, COUNT(*) FROM assessments WHERE category LIKE ? GROUP BY state ORDER BY COUNT(*) DESC LIMIT 5", (f"%{cat}%",))
                    text_prefix = f"the top 5 {cat} states"
                
                rows = cursor.fetchall()
                found_data = [{"name": r[0].capitalize(), "extraction": round(r[1], 2)} for r in rows]

            # B. Multi-State Comparison
            else:
                cursor.execute("SELECT DISTINCT state FROM assessments")
                all_states = [row[0] for row in cursor.fetchall() if row[0]]
                words = user_input.replace("compare", "").replace("vs", " ").replace(",", " ").replace("and", " ").split()
                seen = set()
                for w in words:
                    if len(w) < 3: continue
                    best, score = process.extractOne(w, all_states, scorer=fuzz.token_sort_ratio)
                    if score > 80 and best not in seen:
                        seen.add(best)
                        cursor.execute("SELECT extraction FROM assessments WHERE state = ?", (best,))
                        rows = cursor.fetchall()
                        if rows:
                            avg = sum(r[0] for r in rows) / len(rows)
                            found_data.append({"name": best.capitalize(), "extraction": round(avg, 2)})
                text_prefix = "the comparison"

    except Exception as e:
        return {"text": f"Error: {str(e)}", "chartData": []}

    # --- 6. RESPONSE FLOW ---
    if found_data:
        last_data_cache["data"] = found_data
        names = ", ".join([d['name'] for d in found_data])
        return {
            "text": f"I've found the data for {text_prefix} ({names}). Would you like me to generate a chart? (Yes/No)",
            "chartData": [] 
        }

    # Why & KB Fallbacks
    if "why" in user_input:
        for state, reason in WHY_MAP.items():
            if state in user_input:
                return {"text": f"**{state.capitalize()}**: {reason}", "chartData": []}

    for key, value in KNOWLEDGE_BASE.items():
        if key in user_input:
            return {"text": value, "chartData": []}

    return {"text": "I couldn't identify those states. Try 'Compare Punjab and Bihar'.", "chartData": []}

@app.get("/")
def read_root():
    return {"status": "INGRES API is running"}