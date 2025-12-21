from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from thefuzz import process, fuzz

app = FastAPI()

# 1. CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Data Model
class WaterQuery(BaseModel):
    message: str

# 3. Knowledge Base for FAQ
KNOWLEDGE_BASE = {
    "groundwater": "Groundwater is the water found underground in the cracks and spaces in soil, sand and rock.",
    "extraction": "Groundwater extraction is the process of taking water from underground sources for irrigation, drinking, or industrial use.",
    "recharge": "Recharge is the primary method through which water enters an aquifer, usually through rainfall soaking into the ground.",
    "over-exploited": "A region is 'over-exploited' when the amount of water being pumped out is more than the amount of rain soaking back into the ground.",
    "safe": "A 'Safe' category means the groundwater extraction is less than 70% of the available annual recharge.",
    "critical": "A 'Critical' category means extraction is between 90% and 100% of the annual replenishable resource.",
    "stage": "The 'Stage of Extraction' is the percentage of groundwater used compared to what is available."
}

# 4. WHY_MAP for Explanations
WHY_MAP = {
    "andhra pradesh": "Extensive use of groundwater for irrigation, especially for paddy and commercial crops.",
    "arunachal pradesh": "Low groundwater stress due to high rainfall and low population density.",
    "assam": "Abundant rainfall and surface water reduce dependence on groundwater.",
    "bihar": "High agricultural dependence and increasing use of shallow tube wells.",
    "chhattisgarh": "Agriculture-driven extraction with limited recharge infrastructure.",
    "goa": "Tourism-driven demand and limited freshwater aquifers.",
    "gujarat": "Low rainfall, arid regions, and heavy agricultural and industrial use.",
    "haryana": "Intensive irrigation practices and water-intensive cropping patterns.",
    "himachal pradesh": "Mountainous terrain with limited aquifer storage but relatively low demand.",
    "jharkhand": "Uneven rainfall distribution and increasing rural groundwater usage.",
    "karnataka": "Erratic rainfall and dependence on borewells for agriculture and urban supply.",
    "kerala": "High rainfall but localized over-extraction in urban and coastal areas.",
    "madhya pradesh": "Large agricultural area relying on groundwater for irrigation.",
    "maharashtra": "Recurring droughts, sugarcane cultivation, and uneven rainfall.",
    "manipur": "Low industrial use but increasing domestic groundwater dependence.",
    "meghalaya": "High rainfall and low extraction keep groundwater stress low.",
    "mizoram": "Low groundwater usage due to hilly terrain and surface water availability.",
    "nagaland": "Limited groundwater development and reliance on rainfall.",
    "odisha": "Agriculture-driven groundwater use with seasonal variability.",
    "punjab": "High dependence on groundwater for water-intensive crops like paddy and wheat.",
    "rajasthan": "Low rainfall, arid climate, and high evaporation rates.",
    "sikkim": "Abundant natural springs and low groundwater dependency.",
    "tamil nadu": "High urban and agricultural demand with frequent drought conditions.",
    "telangana": "Rapid expansion of borewells and irrigation-intensive farming.",
    "tripura": "Moderate groundwater use supported by consistent rainfall.",
    "uttar pradesh": "Large population and extensive agricultural groundwater withdrawal.",
    "uttarakhand": "Mountainous regions rely more on springs than deep groundwater.",
    "west bengal": "High population density and agricultural extraction in plains.",
    "andaman and nicobar islands": "Limited freshwater aquifers and dependence on rainfall.",
    "chandigarh": "Urban groundwater extraction with limited recharge areas.",
    "dadra and nagar haveli and daman and diu": "Industrial and domestic demand with limited aquifers.",
    "delhi": "Urban over-extraction and limited natural recharge zones.",
    "jammu and kashmir": "Seasonal recharge from snowmelt with localized groundwater use.",
    "ladakh": "Cold desert conditions with extremely limited groundwater availability.",
    "lakshadweep": "Fragile freshwater lenses threatened by over-extraction and saline intrusion.",
    "puducherry": "Coastal aquifers affected by over-extraction and saline intrusion."
}

# 5. The Chatbot Logic
@app.post("/ask")
async def ask_bot(item: WaterQuery):
    user_input = item.message.strip().lower()

    # --- A. Identity & Help ---
    help_triggers = ["what is ingres", "who are you", "help", "how to use"]
    if any(q in user_input for q in help_triggers):
        return {
            "text": "I am the INGRES AI assistant. “INDIA-Groundwater Resource Estimation System (IN-GRES)” is a software/web based application developed by Central Ground Water Board (CGWB) in collaboration with Indian Institute of Technology-Hyderabad (IIT-H) for assessment of ground water resources.Try asking:\n\n"
                    "🔹 Why: 'Why is Punjab over-exploited?'\n"
                    "🔹 Trends: 'Which states have the highest extraction?'\n"
                    "🔹 Compare: 'Compare Delhi and Goa'\n"
                    "🔹 Status: 'Which states are safe?'",
            "chartData": []
        }

    # --- B. "Why" Explanation Logic ---
    if "why" in user_input:
        # Check which state is mentioned in the "why" question
        for state, reason in WHY_MAP.items():
            if state in user_input:
                return {"text": f"**{state.capitalize()}**: {reason}", "chartData": []}

    # --- C. Trends & Top Questions ---
    if "top" in user_input or "highest" in user_input:
        try:
            with sqlite3.connect("./ingres.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT state, AVG(extraction) as avg_ext 
                    FROM assessments 
                    GROUP BY state 
                    ORDER BY avg_ext DESC LIMIT 5
                """)
                rows = cursor.fetchall()
                top_data = [{"name": r[0].capitalize(), "extraction": round(r[1], 2)} for r in rows]
                return {
                    "text": f"The top 5 states with the highest extraction are: {', '.join([d['name'] for d in top_data])}.",
                    "chartData": top_data
                }
        except Exception as e:
            return {"text": f"Error: {str(e)}", "chartData": []}

    # --- D. Category & Threshold Queries ---
    if any(word in user_input for word in ["over-exploited", "critical", "safe", "above", "more than"]):
        try:
            with sqlite3.connect("./ingres.db") as conn:
                cursor = conn.cursor()
                if "above" in user_input or "more than" in user_input:
                    cursor.execute("SELECT state, AVG(extraction) as avg_ext FROM assessments GROUP BY state HAVING avg_ext > 100 ORDER BY avg_ext DESC")
                    rows = cursor.fetchall()
                    text_prefix = "States with extraction above 100%:"
                else:
                    cat = "Over-Exploited" if "over" in user_input else "Critical" if "critical" in user_input else "Safe"
                    cursor.execute("SELECT state, COUNT(*) FROM assessments WHERE category LIKE ? GROUP BY state ORDER BY COUNT(*) DESC LIMIT 5", (f"%{cat}%",))
                    rows = cursor.fetchall()
                    text_prefix = f"States with the most {cat} blocks:"

                data = [{"name": r[0].capitalize(), "extraction": round(r[1], 2)} for r in rows]
                return {"text": f"{text_prefix} {', '.join([d['name'] for d in data])}.", "chartData": data}
        except Exception as e:
            return {"text": f"Error: {str(e)}", "chartData": []}

    # --- E. Knowledge Base Check ---
    for key, value in KNOWLEDGE_BASE.items():
        if key in user_input:
            return {"text": value, "chartData": []}

    # --- F. Database Logic (Fuzzy Matching) ---
    try:
        with sqlite3.connect("./ingres.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT state FROM assessments")
            all_states = [row[0] for row in cursor.fetchall() if row[0]]
            cursor.execute("SELECT DISTINCT district_name FROM assessments")
            all_districts = [row[0] for row in cursor.fetchall() if row[0]]

            raw_entities = user_input.replace("compare", "").replace("and", " ").replace("vs", " ").split()
            raw_entities = [e.strip() for e in raw_entities if len(e) > 2]
            comparison_data = []

            for entity in raw_entities:
                best_state, state_score = process.extractOne(entity, all_states, scorer=fuzz.token_sort_ratio)
                best_dist, dist_score = process.extractOne(entity, all_districts, scorer=fuzz.token_sort_ratio)

                if state_score > 80:
                    cursor.execute("SELECT extraction FROM assessments WHERE state = ?", (best_state,))
                    rows = cursor.fetchall()
                    avg_val = sum(r[0] for r in rows) / len(rows)
                    comparison_data.append({"name": best_state.capitalize(), "extraction": round(avg_val, 2)})
                elif dist_score > 80:
                    cursor.execute("SELECT extraction FROM assessments WHERE district_name = ?", (best_dist,))
                    row = cursor.fetchone()
                    if row:
                        comparison_data.append({"name": best_dist.capitalize(), "extraction": row[0]})
            
            if comparison_data:
                return {"text": f"Comparing: {', '.join([d['name'] for d in comparison_data])}", "chartData": comparison_data}
    except Exception as e:
        return {"text": f"Error: {str(e)}", "chartData": []}

    return {"text": "I'm not sure about that. Try asking 'Why is Punjab over-exploited?'", "chartData": []}

@app.get("/")
def read_root():
    return {"status": "INGRES API is running"}