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

last_data_cache = {"data": []}

# -------------------- KNOWLEDGE --------------------
KNOWLEDGE_BASE = {
    "groundwater": "Groundwater is water stored beneath the Earth’s surface in soil and rock formations called aquifers.",
    "extraction": "Groundwater extraction refers to pumping water from underground sources for agriculture, drinking, and industry.",
    "recharge": "Recharge is the process by which rainfall replenishes underground aquifers.",
    "over-exploited": "An over-exploited region extracts more groundwater than it naturally recharges.",
    "safe": "A 'Safe' category means groundwater extraction is below 70% of available recharge.",
    "critical": "A 'Critical' category indicates extraction is between 90% and 100% of recharge capacity.",
    "stage": "Stage of Extraction is the ratio of groundwater used to groundwater available."
}

# -------------------- WHY MAP --------------------
WHY_MAP = {
    "punjab": "High dependence on groundwater for water-intensive crops like paddy and wheat; subsidized electricity leads to over-pumping.",
    "haryana": "Intensive agricultural practices and high irrigation demand for cereal crops beyond natural recharge levels.",
    "delhi": "Massive population density, rapid urbanization, and high concretization preventing rainwater from recharging aquifers.",
    "uttar pradesh": "Heavy agricultural extraction in western districts for sugarcane; industrial pollution in areas like Kanpur (tanneries).",
    "rajasthan": "Arid climate, extremely low rainfall, and high evaporation rates; historic reliance on deep fossil water.",
    "gujarat": "Industrial demand and high salinity ingress in coastal areas; intensive irrigation in districts like Mehsana.",
    "maharashtra": "Hard rock (Basalt) terrain with low storage capacity; over-extraction for sugarcane in the Marathwada/Vidarbha belts.",
    "karnataka": "Hard rock terrain (Deccan Trap) with low storage; high borewell density for IT hubs and agriculture.",
    "tamil nadu": "Over-reliance on groundwater due to surface water scarcity and frequent failures of the monsoon.",
    "bengaluru": "Rapid expansion into peripheral zones without piped water; over-reliance on private tankers and deep borewells.",
    "chennai": "Coastal location leading to seawater intrusion; high domestic demand following reservoir failures.",
    "gurugram": "Extremely high construction demand and deep extraction for high-rise residential complexes.",
    "jaipur": "Semi-arid climate coupled with tourism and luxury residential demand exceeding replenishment."
}

# -------------------- EXPLANATION ENGINE --------------------
def explain_extraction(name, value):
    if value <= 70:
        status = "relatively safe"
        meaning = "groundwater use is within sustainable limits"
    elif value <= 100:
        status = "stressed"
        meaning = "water usage is close to or exceeding recharge capacity"
    else:
        status = "over-exploited"
        meaning = "groundwater is being extracted much faster than it can recharge"

    return (
        f"**{name}** has an average groundwater extraction of **{value}%**. "
        f"This places it in a **{status}** category, meaning {meaning}."
    )

# -------------------- MAIN API --------------------
@app.post("/ask")
async def ask_bot(item: WaterQuery):
    user_input = item.message.strip().lower()

    # Normalize terms
    if "overexploited" in user_input or "over exploited" in user_input:
        user_input = user_input.replace("overexploited", "over-exploited").replace("over exploited", "over-exploited")

    SYNONYMS = {"usage": "extraction", "withdrawal": "extraction", "consumption": "extraction"}
    is_usage_query = any(w in user_input for w in ["usage", "extraction"])
    for k, v in SYNONYMS.items():
        user_input = user_input.replace(k, v)

    # YES/NO flow
    if user_input in ["yes", "show chart", "sure", "ok"]:
        if last_data_cache["data"]:
            data = last_data_cache["data"]
            last_data_cache["data"] = []
            return {"text": "Here’s a visual breakdown of the data 📊", "chartData": data}
        return {"text": "I don’t have any prepared data yet.", "chartData": []}

    found_data = []
    text_prefix = "the comparison"

    try:
        with sqlite3.connect("./ingres.db") as conn:
            cursor = conn.cursor()

            # --- DYNAMIC COLUMN DETECTION ---
            cursor.execute("PRAGMA table_info(assessments)")
            cols = [info[1] for info in cursor.fetchall()]
            
            # This finds the actual name used in your DB regardless of case or spaces
            state_col = next((c for c in cols if "state" in c.lower()), "State")
            dist_col = next((c for c in cols if "district" in c.lower()), "District")
            block_col = next((c for c in cols if "block" in c.lower() or "taluka" in c.lower()), "Block/Taluka")
            extract_col = next((c for c in cols if "extraction" in c.lower() or "stage" in c.lower()), "Stage of Ground Water Extraction (%)")

            # 1. Top States logic
            if any(w in user_input for w in ["top", "highest", "over-exploited"]):
                cursor.execute(f'SELECT "{state_col}", AVG("{extract_col}") FROM assessments GROUP BY "{state_col}" ORDER BY AVG("{extract_col}") DESC LIMIT 5')
                rows = cursor.fetchall()
                found_data = [{"name": r[0], "extraction": round(r[1], 2)} for r in rows]
                text_prefix = "the top 5 states by extraction"

            # 2. Search / Comparison Logic
            else:
                cursor.execute(f'SELECT DISTINCT "{state_col}" FROM assessments')
                states_list = [r[0] for r in cursor.fetchall() if r[0]]
                cursor.execute(f'SELECT DISTINCT "{dist_col}" FROM assessments')
                districts_list = [r[0] for r in cursor.fetchall() if r[0]]
                cursor.execute(f'SELECT DISTINCT "{block_col}" FROM assessments')
                blocks_list = [r[0] for r in cursor.fetchall() if r[0]]

                all_entities = states_list + districts_list + blocks_list
                words = user_input.replace("compare", "").replace("vs", " ").replace("and", " ").replace(",", " ").split()
                seen = set()

                for w in words:
                    if len(w) < 3: continue
                    best, score = process.extractOne(w, all_entities, scorer=fuzz.token_sort_ratio)
                    
                    if score > 80 and best.lower() not in seen:
                        seen.add(best.lower())
                        if best in states_list:
                            cursor.execute(f'SELECT AVG("{extract_col}") FROM assessments WHERE "{state_col}" = ?', (best,))
                        elif best in districts_list:
                            cursor.execute(f'SELECT AVG("{extract_col}") FROM assessments WHERE "{dist_col}" = ?', (best,))
                        else:
                            cursor.execute(f'SELECT "{extract_col}" FROM assessments WHERE "{block_col}" = ?', (best,))
                        
                        val = cursor.fetchone()[0]
                        if val is not None:
                            found_data.append({"name": best, "extraction": round(val, 2)})

    except Exception as e:
        return {"text": f"Database error: {str(e)}", "chartData": []}

    # -------------------- RESPONSE --------------------
    if found_data:
        last_data_cache["data"] = found_data
        explanations = "\n\n".join([explain_extraction(d["name"], d["extraction"]) for d in found_data])
        intro = "Groundwater extraction measures usage relative to natural recharge.\n\n" if is_usage_query else ""
        
        return {
            "text": f"{intro}Results for {text_prefix}:\n\n{explanations}\n\nWould you like a chart? (Yes/No)",
            "chartData": []
        }

    # WHY logic
    if "why" in user_input:
        for key, reason in WHY_MAP.items():
            if key in user_input:
                return {"text": f"### Why is **{key.title()}** stressed?\n\n{reason}", "chartData": []}

    # Knowledge Base fallback
    for key, value in KNOWLEDGE_BASE.items():
        if key in user_input:
            return {"text": value, "chartData": []}

    return {"text": "I couldn't find those regions. Try 'Compare Jaipur and Patna'.", "chartData": []}