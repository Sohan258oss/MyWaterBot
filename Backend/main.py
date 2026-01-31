from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import sqlite3
import requests
import re
import os
from bs4 import BeautifulSoup
import json
import math

class SemanticSearch:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticSearch, cls).__new__(cls)
            cls._instance.api_url = "https://api-inference.huggingface.co/models/sentence-transformers/paraphrase-MiniLM-L3-v2"
            cls._instance.hf_token = os.getenv("HF_TOKEN")
            cls._instance.entities = []
            cls._instance.embeddings = None
            cls._instance.embeddings_path = os.path.join(os.path.dirname(__file__), "embeddings.json")
        return cls._instance

    def _query_api(self, payload):
        headers = {"Authorization": f"Bearer {self.hf_token}"} if self.hf_token else {}
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"HF API Error: {response.status_code} - {response.text}")
                return None
            return response.json()
        except Exception as e:
            print(f"HF API Request Exception: {e}")
            return None

    def encode_entities(self, entities):
        self.entities = entities
        payload = {
            "inputs": entities,
            "options": {"wait_for_model": True}
        }
        response = self._query_api(payload)
        if isinstance(response, list):
            self.embeddings = response
            with open(self.embeddings_path, "w") as f:
                json.dump({"entities": self.entities, "embeddings": self.embeddings}, f)
        else:
            print(f"Error encoding entities: {response}")

    def load_embeddings(self):
        if os.path.exists(self.embeddings_path):
            try:
                with open(self.embeddings_path, "r") as f:
                    data = json.load(f)
                self.entities = data["entities"]
                self.embeddings = data["embeddings"]
                return True
            except Exception as e:
                print(f"Error loading embeddings: {e}")
                return False
        return False

    def search(self, query, threshold=0.6):
        if self.embeddings is None or not self.entities:
            return []

        payload = {
            "inputs": query,
            "options": {"wait_for_model": True}
        }
        query_embedding = self._query_api(payload)

        if not isinstance(query_embedding, list):
            return []

        # Feature Extraction returns List[float] for a single string or List[List[float]]
        if len(query_embedding) > 0 and isinstance(query_embedding[0], list):
            query_embedding = query_embedding[0]

        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(y * y for y in b))
            return dot_product / (mag_a * mag_b) if mag_a * mag_b > 0 else 0

        results = []
        for i, emb in enumerate(self.embeddings):
            score = cosine_similarity(query_embedding, emb)
            if score >= threshold:
                results.append({"name": self.entities[i], "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

from contextlib import asynccontextmanager

semantic_search = SemanticSearch()

# Database path configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "ingres.db")
if not os.path.exists(DB_PATH):
    DB_PATH = "./ingres.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize semantic search and cache locations
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(assessments)")
            cols = [info[1] for info in cursor.fetchall()]
            state_col = next((c for c in cols if "state" in c.lower()), "State")
            dist_col = next((c for c in cols if "district" in c.lower()), "District")
            block_col = next((c for c in cols if "block" in c.lower() or "taluka" in c.lower()), "Block/Taluka")

            cursor.execute(f'SELECT DISTINCT "{state_col}" FROM assessments')
            app.state.states_list = [r[0] for r in cursor.fetchall() if r[0]]
            cursor.execute(f'SELECT DISTINCT "{dist_col}" FROM assessments')
            app.state.districts_list = [r[0] for r in cursor.fetchall() if r[0]]
            cursor.execute(f'SELECT DISTINCT "{block_col}" FROM assessments')
            blocks = [r[0] for r in cursor.fetchall() if r[0]]

            if not semantic_search.load_embeddings():
                # Unified corpus: locations + dictionary keys
                knowledge_keys = list(KNOWLEDGE_BASE.keys())
                tips_keys = list(TIPS.keys())
                why_keys = list(WHY_MAP.keys())
                all_entities = list(set(app.state.states_list + app.state.districts_list + blocks + knowledge_keys + tips_keys + why_keys))
                if all_entities:
                    semantic_search.encode_entities(all_entities)
    except Exception as e:
        print(f"Error initializing: {e}")
    yield

app = FastAPI(lifespan=lifespan)

# -------------------- SCRAPER SERVICE --------------------
def get_latest_news():
    query = "groundwater levels India"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=nws"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Check for 403 or other non-200 responses
        if response.status_code != 200:
            return get_cached_news()

        soup = BeautifulSoup(response.text, 'html.parser')
        headlines = []

        # Google News headlines in search results are typically in <h3> tags
        for item in soup.find_all('h3'):
            text = item.get_text().strip()
            if text:
                headlines.append(text)
            if len(headlines) == 3:
                break

        if not headlines:
            return get_cached_news()

        return headlines

    except Exception:
        # Fallback mechanism for request failures or parsing errors
        return get_cached_news()

def get_cached_news():
    return [
        "Groundwater levels in India showing signs of improvement in some regions due to better monsoon.",
        "New CGWB report highlights critical depletion in northwestern states.",
        "Government announces new initiatives for community-led groundwater management."
    ]

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
    "master plan": "The Master Plan for Artificial Recharge to Groundwater-2020 envisages construction of about 1.42 crore rain water harvesting and artificial recharge structures.",
    "gujarat salinity": "Coastal Gujarat faces seawater intrusion due to over-pumping, leading to increased salinity in groundwater.",
    "paddy water": "Rice (paddy) is a water-intensive crop, often requiring 3,000 to 5,000 liters of water to produce 1 kg of grain.",
    "sugarcane": "Sugarcane is another high water-consuming crop, contributing significantly to groundwater depletion in Maharashtra and UP.",
    "millets": "Millets are climate-smart crops that require significantly less water than rice or wheat, making them ideal for water-stressed regions.",
    "atal bhujal yojana": "Atal Bhujal Yojana (ATAL JAL) is a Central Sector Scheme for sustainable groundwater management with community participation.",
    "cgwb": "The Central Ground Water Board (CGWB) is the apex organization in India for providing scientific inputs for management, exploration, and monitoring of groundwater.",
    "pmksy": "Pradhan Mantri Krishi Sinchayee Yojana (PMKSY) focuses on 'Har Khet Ko Pani' and 'Per Drop More Crop'.",
    "drip irrigation": "Drip irrigation delivers water directly to the plant's root zone, reducing evaporation and runoff, saving up to 40-70% water.",
    "arsenic": "Arsenic contamination is a major health concern in the Ganga-Brahmaputra fluvial plains, including West Bengal, Bihar, and UP.",
    "fluoride": "Excessive fluoride in groundwater can lead to dental and skeletal fluorosis; it is common in states like Rajasthan and Telangana.",
    "nitrate": "Nitrate pollution in groundwater often results from excessive use of fertilizers in agriculture and improper sewage disposal.",
    "jal shakti abhiyan": "Jal Shakti Abhiyan is a campaign for water conservation and water security in India.",
    "national aquifer mapping": "The NAQUIM program aims to delineate aquifers, their characterization and develop plans for sustainable management.",
    "virtual water": "Virtual water is the hidden flow of water if food or other commodities are traded from one place to another.",
    "over-pumping": "Over-pumping occurs when groundwater is withdrawn faster than the rate of recharge, causing water tables to drop.",
    "seawater intrusion": "In coastal areas, over-extraction of groundwater can cause seawater to flow into freshwater aquifers.",
    "check dam": "A check dam is a small, sometimes temporary, dam constructed across a swale, drainage ditch, or waterway to counteract erosion by reducing water velocity.",
    "percolation tank": "Percolation tanks are artificially created surface water bodies, submerging a highly permeable land area so that surface runoff is made to percolate and recharge the ground water storage.",
    "dug well": "Dug wells are shallow wells excavated into the ground, usually with a diameter of several meters.",
    "greywater": "Greywater is gently used water from bathroom sinks, showers, tubs, and washing machines. It is not water that has come into contact with feces.",
    "blackwater": "Blackwater is wastewater from toilets, which likely contains pathogens.",
    "infiltration": "Infiltration is the process by which water on the ground surface enters the soil.",
    "transpiration": "Transpiration is the process by which moisture is carried through plants from roots to small pores on the underside of leaves, where it changes to vapor and is released to the atmosphere.",
    "evapotranspiration": "Evapotranspiration is the sum of evaporation and plant transpiration from the Earth's land and ocean surface to the atmosphere.",
    "water table": "The water table is the upper surface of the zone of saturation. The zone of saturation is where the pores and fractures of the ground are saturated with water.",
    "confined aquifer": "A confined aquifer is an aquifer below the land surface that is saturated with water. Layers of impermeable material are both above and below the aquifer, causing it to be under pressure.",
    "unconfined aquifer": "An unconfined aquifer is an aquifer whose upper water surface (water table) is at atmospheric pressure, and thus is able to rise and fall.",
    "hydrogeology": "Hydrogeology is the area of geology that deals with the distribution and movement of groundwater in the soil and rocks of the Earth’s crust.",
    "specific yield": "Specific yield is the ratio of the volume of water that, after being saturated, can be drained by gravity to its own volume.",
    "permeability": "Permeability is a measure of the ability of a material (such as rocks) to transmit fluids.",
    "porosity": "Porosity is a measure of the void spaces in a material, and is a fraction of the volume of voids over the total volume.",
    "drawdown": "Drawdown is the reduction in the hydraulic head observed at a well in an aquifer, typically due to pumping a well as part of an aquifer test or well test.",
    "cone of depression": "A cone of depression occurs in an aquifer when groundwater is pumped from a well. In an unconfined aquifer, this is an actual depression of the water levels.",
    "baseflow": "Baseflow is the portion of streamflow that comes from 'the sum of deep subsurface flow and delayed shallow subsurface flow'.",
    "catchment area": "The catchment area is the area from which rainfall flows into a particular river or lake.",
    "siltation": "Siltation is a process by which water becomes dirty as a result of fine mineral particles in the water.",
    "desalination": "Desalination is a process that takes away mineral components from saline water.",
    "fecal coliform": "Fecal coliforms are a group of bacteria that are passed through the fecal excrement of humans, livestock and wildlife.",
    "hard water": "Hard water is water that has high mineral content. Hard water is formed when water percolates through deposits of limestone, chalk or gypsum.",
    "soft water": "Soft water is surface water that contains low concentrations of ions and in particular is low in ions of calcium and magnesium.",
    "turbidity": "Turbidity is the cloudiness or haziness of a fluid caused by large numbers of individual particles that are generally invisible to the naked eye.",
    "ph value": "The pH of water is a measure of how acidic/basic water is.",
    "tds": "Total Dissolved Solids (TDS) is a measure of the dissolved combined content of all inorganic and organic substances present in a liquid.",
    "dissolved oxygen": "Dissolved oxygen (DO) is the amount of gaseous oxygen (O2) dissolved in the water.",
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
    "pollution": "Prevent pollution by: 1. Reducing fertilizer and pesticide use. 2. Proper disposal of hazardous waste. 3. Ensuring septic systems are well-maintained.",
    "crop choice": "Switch from water-intensive crops like paddy to millets or pulses in water-stressed regions.",
    "mulching": "Use organic mulch in fields to reduce evaporation from the soil surface.",
    "smart irrigation": "Adopt sensors and automated systems to provide water to crops only when needed.",
    "community participation": "Form Water User Associations to collectively manage and monitor groundwater usage in villages.",
    "well recharging": "Redirect surplus monsoon runoff into defunct dug wells to recharge local aquifers.",
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
        f"{name.title()} has an average groundwater extraction of {value}%. "
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
async def ask_bot(item: WaterQuery, request: Request):
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

    # 3. UNIFIED SEMANTIC SEARCH (Priority 1)
    results = semantic_search.search(user_input, threshold=0.65)

    if results:
        best_match = results[0]["name"]

        # 4. Direct Answer: Knowledge/Tips (Priority 2)
        match_key = best_match.lower()
        if match_key in KNOWLEDGE_BASE:
            return {
                "text": f"### {best_match.title()}\n\n{KNOWLEDGE_BASE[match_key]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

        if match_key in TIPS:
            return {
                "text": f"### {best_match.title()} Tip\n\n{TIPS[match_key]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

        if match_key in WHY_MAP and "why" in user_input:
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{WHY_MAP[match_key]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

        # 5. Data Lookup: Location (Priority 3)
        found_data = []
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(assessments)")
                cols = [info[1] for info in cursor.fetchall()]
                state_col = next((c for c in cols if "state" in c.lower()), "State")
                dist_col = next((c for c in cols if "district" in c.lower()), "District")
                block_col = next((c for c in cols if "block" in c.lower() or "taluka" in c.lower()), "Block/Taluka")
                extract_col = next((c for c in cols if "extraction" in c.lower() or "stage" in c.lower()), "Stage of Ground Water Extraction (%)")

                states_list = getattr(request.app.state, "states_list", [])
                districts_list = getattr(request.app.state, "districts_list", [])
                states_map = {s.lower(): s for s in states_list}
                districts_map = {d.lower(): d for d in districts_list}

                seen = set()
                for res in results:
                    name = res["name"]
                    name_low = name.lower()
                    if name_low in seen: continue
                    seen.add(name_low)

                    if name_low in states_map:
                        cursor.execute(f'SELECT AVG("{extract_col}") FROM assessments WHERE "{state_col}" = ?', (states_map[name_low],))
                    elif name_low in districts_map:
                        cursor.execute(f'SELECT AVG("{extract_col}") FROM assessments WHERE "{dist_col}" = ?', (districts_map[name_low],))
                    elif name_low in KNOWLEDGE_BASE or name_low in TIPS or name_low in WHY_MAP:
                        # If it's a key in our dicts, we might have already handled it as Priority 2.
                        # We skip it here if it doesn't match a location.
                        continue
                    else:
                        cursor.execute(f'SELECT "{extract_col}" FROM assessments WHERE "{block_col}" = ?', (name,))

                    val = cursor.fetchone()
                    if val and val[0] is not None:
                        found_data.append({"name": name, "extraction": round(val[0], 2)})

                    if len(found_data) >= 5: break

            if found_data:
                last_data_cache["data"] = found_data
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
                    "text": f"{intro}Results for your search:\n\n{explanations}{warning_text}\n\nWould you like a chart? (Yes/No)",
                    "chartData": [],
                    "suggestions": get_suggestions(user_input, found_data)
                }

        except Exception as e:
            return {"text": f"Database error: {str(e)}", "chartData": [], "suggestions": get_suggestions(user_input)}

        # Fallback for WHY_MAP if "why" wasn't in query but it's the best match and not a location
        if match_key in WHY_MAP:
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{WHY_MAP[match_key]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input)
            }

    # 6. Confidence Threshold Fallback: News Scraper (Priority 4)
    news = await run_in_threadpool(get_latest_news)
    news_str = "\n".join([f"• {item}" for item in news])
    return {
        "text": f"I couldn't find specific data for your query, but here are the latest groundwater updates:\n\n{news_str}",
        "chartData": [],
        "suggestions": get_suggestions(user_input)
    }
@app.get("/get-news")
async def get_news():
    """Returns top 3 groundwater news headlines."""
    news = await run_in_threadpool(get_latest_news)
    return {"news": news}

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "message": "INGRES AI Groundwater API is running",
        "endpoints": {
            "ask": "/ask (POST)",
            "get-news": "/get-news (GET)",
            "health": "/ (GET)"
        }
    }
