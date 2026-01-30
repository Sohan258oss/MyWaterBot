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
    "groundwater": "Groundwater is water that has found its way down from the Earth’s surface into the cracks and spaces in soil, sand and rock.The largest use for groundwater is to irrigate crops.",
    "extraction": "Ground water overuse or overexploitation is defined as a situation in which, over a period of time, theaverage extraction rate from aquifers is greater than the average recharge rate. This leads to a decline in the groundwater levels and may also result in other adverse consequences such as land subsidence, reduced water quality, and ecological damage.",
    "recharge": "Recharge is the process by which rainfall replenishes underground aquifers.",
    "over-exploited": "An over-exploited region extracts more groundwater than it naturally recharges.",
    "safe": "A 'Safe' category means groundwater extraction is below 70% of available recharge.",
    "critical": "A 'Critical' category indicates extraction is between 90% and 100% of recharge capacity.",
    "stage": "Stage of Extraction is the ratio of groundwater used to groundwater available.",
    "aquifer": "An aquifer is an underground layer of water-bearing permeable rock, Aquifers are typically made up of gravel, sand, sandstone, or fractured rock, like limestone. Water can move through these materials because they have large connected spaces that make them permeable. The speed at which groundwater flows depends on the size of the spaces in the soil or rock and how well the spaces are connected.",
    "borewell": "A borewell is a deep, narrow hole drilled into the ground to access groundwater from aquifers.",
    "watershed": "A watershed is an area of land where all the water that falls in it and drains off it goes to a common outlet, such as a river or lake.",
    "salinity": "Salinity refers to the concentration of dissolved salts in water. High salinity can make groundwater unsuitable for drinking or irrigation.",
}

# -------------------- CONTAMINANTS --------------------
CONTAMINANT_DATA = {
    "rajasthan": ["Fluoride", "Nitrate"],
    "punjab": ["Nitrate", "Arsenic"],
    "haryana": ["Fluoride", "Nitrate"],
    "west bengal": ["Arsenic", "Fluoride"],
    "bihar": ["Arsenic", "Iron"],
    "uttar pradesh": ["Fluoride", "Arsenic"],
    "karnataka": ["Fluoride", "Nitrate"],
    "tamil nadu": ["Fluoride", "Salinity"],
    "gujarat": ["Salinity", "Fluoride"],
    "andhra pradesh": ["Fluoride"],
    "delhi": ["Nitrate", "Fluoride"],
    "kolar": ["Fluoride"],
    "bangalore": ["Nitrate"],
    "tumkur": ["Fluoride"],
    "chikkaballapura": ["Fluoride"],
    "raichur": ["Arsenic"],
    "gulbarga": ["Fluoride"]
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
    "jaipur": "Semi-arid climate coupled with tourism and luxury residential demand exceeding replenishment.",
    "odisha": "Coastal districts face salinity ingress due to proximity to the sea, while inland areas have limited storage in hard rock aquifers.",
    "bihar": "High levels of arsenic and fluoride contamination in certain belts; seasonal flooding can also impact groundwater quality.",
    "assam": "Despite abundant rainfall, certain regions face high iron and arsenic content in shallow aquifers.",
    "kerala": "Laterite soil has high permeability but low storage, leading to seasonal water scarcity despite high annual rainfall."
}

# -------------------- CONSERVATION TIPS --------------------
TIPS = {
    "conservation": "To conserve groundwater: 1. Install rainwater harvesting systems. 2. Use drip or sprinkler irrigation. 3. Recycle greywater for gardening. 4. Fix leaks promptly.",
    "harvesting": "Rainwater harvesting involves collecting and storing rainwater from rooftops or ground surfaces to recharge aquifers or for direct use.",
    "farming": "Sustainable farming tips: 1. Adopt crop rotation. 2. Grow less water-intensive crops like millets. 3. Use mulch to retain soil moisture.",
    "pollution": "Prevent pollution by: 1. Reducing fertilizer and pesticide use. 2. Proper disposal of hazardous waste. 3. Ensuring septic systems are well-maintained."
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
        f"{name} has an average groundwater extraction of {value}%. "
        f"This places it in a **{status}** category, meaning {meaning}."
    )

# -------------------- SUGGESTION ENGINE --------------------
def get_suggestions(user_input, found_data=None):
    suggestions = ["Conservation tips", "What is an aquifer?", "Show India map"]
    if found_data:
        suggestions.insert(0, "Show chart")
        for d in found_data[:2]:
            suggestions.append(f"Why is {d['name']} stressed?")
    elif "why" in user_input:
        suggestions.insert(0, "Compare Punjab and Bihar")
    elif any(k in user_input for k in ["tip", "conservation", "harvesting", "farming"]):
        suggestions.insert(0, "Search a state like Punjab")

    seen = set()
    unique = []
    for s in suggestions:
        if s.lower() not in seen:
            unique.append(s)
            seen.add(s.lower())
    return unique[:3]

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
            return {
                "text": "Here’s a visual breakdown of the data 📊",
                "chartData": data,
                "suggestions": get_suggestions(user_input, data)
            }
        return {
            "text": "I don’t have any prepared data yet.",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }
    
    elif user_input in ["no", "n", "nope", "not now", "stop"]:
        last_data_cache["data"] = [] # Optional: clear cache if they decline
        return {
            "text": "No problem! 😊 What would you like to do next? You can ask me:\n\n"
                    "* **'Why is [State] stressed?'** to learn the causes.\n"
                    "* **'What is an aquifer?'** for a definition.\n"
                    "* **'Compare [District A] and [District B]'** for more data.",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }

    # 1. WHY logic (Explicit)
    if "why" in user_input:
        for key, reason in WHY_MAP.items():
            if key in user_input:
                return {
                    "text": f"### Why is **{key.title()}** stressed?\n\n{reason}",
                    "chartData": [],
                    "suggestions": get_suggestions(user_input)
                }

    # 2. Definition logic (Explicit)
    if any(w in user_input for w in ["what is", "define", "meaning of"]):
        for key, value in KNOWLEDGE_BASE.items():
            if key in user_input:
                return {
                    "text": f"### {key.title()}\n\n{value}",
                    "chartData": [],
                    "suggestions": get_suggestions(user_input)
                }

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
        return {
            "text": f"Database error: {str(e)}",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }

    # -------------------- RESPONSE --------------------
    if found_data:
        text_prefix = "the comparison" if len(found_data) > 1 else "your search"
        last_data_cache["data"] = found_data

        # Add contaminant warnings
        contaminant_warnings = []
        for d in found_data:
            name_lower = d["name"].lower()
            if name_lower in CONTAMINANT_DATA:
                cons = ", ".join(CONTAMINANT_DATA[name_lower])
                contaminant_warnings.append(f"⚠️ Note: {d['name']} has reported high levels of {cons}.")

        explanations = "\n\n".join([explain_extraction(d["name"], d["extraction"]) for d in found_data])
        warning_text = "\n\n" + "\n".join(contaminant_warnings) if contaminant_warnings else ""
        intro = "Groundwater extraction measures usage relative to natural recharge.\n\n" if is_usage_query else ""
        
        return {
            "text": f"{intro}Results for {text_prefix}:\n\n{explanations}{warning_text}\n\nWould you like a chart? (Yes/No)",
            "chartData": [],
            "suggestions": get_suggestions(user_input, found_data)
        }

    # 3. Fallback logic (Implicit keyword matches)
    for key, tip in TIPS.items():
        if key in user_input:
            return {
                "text": f"### Groundwater {key.title()} Tip\n\n{tip}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

    for key, value in KNOWLEDGE_BASE.items():
        if key in user_input:
            return {
                "text": f"### {key.title()}\n\n{value}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

    for key, reason in WHY_MAP.items():
        if key in user_input:
             return {
                 "text": f"### Why is **{key.title()}** stressed?\n\n{reason}",
                 "chartData": [],
                 "suggestions": get_suggestions(user_input)
             }

    return {
        "text": "I couldn't find that information. Try asking about 'conservation tips', 'recharge', or compare two regions like 'Jaipur and Patna'.",
        "chartData": [],
        "suggestions": get_suggestions(user_input)
    }
@app.get("/")
def read_root():
    return {
        "status": "Online",
        "message": "INGRES AI Groundwater API is running",
        "endpoints": {
            "ask": "/ask (POST)",
            "health": "/ (GET)"
        }
    }
