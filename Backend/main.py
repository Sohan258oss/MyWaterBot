import os
import requests
import json
import math
import sqlite3
from huggingface_hub import InferenceClient
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from duckduckgo_search import DDGS

# -------------------- CORRECTED SEMANTIC SEARCH --------------------
class SemanticSearch:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticSearch, cls).__new__(cls)
            # Initialize InferenceClient with the router base URL as required for Render
            cls._instance.model_id = "sentence-transformers/all-mpnet-base-v2"
            cls._instance.hf_token = os.getenv("HF_TOKEN")
            cls._instance.client = InferenceClient(
                token=cls._instance.hf_token,
                base_url="https://router.huggingface.co/hf-inference",
                headers={"X-Wait-For-Model": "true"}
            )
            cls._instance.entities = []
            cls._instance.embeddings = None
            cls._instance.embeddings_path = os.path.join(os.path.dirname(__file__), "embeddings.json")
        return cls._instance

    def _query_api(self, inputs):
        try:
            # InferenceClient.feature_extraction explicitly requests the feature-extraction task
            response = self.client.feature_extraction(inputs, model=self.model_id)
            # Convert to list if it's a numpy array (InferenceClient may return numpy if installed)
            if hasattr(response, "tolist"):
                return response.tolist()
            return response
        except Exception as e:
            print(f"HF API Error via InferenceClient: {e}")
            return None

    def encode_entities(self, entities, batch_size=32):
        new_embeddings = []
        for i in range(0, len(entities), batch_size):
            batch = entities[i : i + batch_size]
            
            response = self._query_api(batch)
            if isinstance(response, list):
                for item in response:
                    # Logic to flatten: ensure we get a 1D vector per sentence
                    # API sometimes returns [[v1, v2...]] (3D) instead of [v1, v2...] (2D)
                    temp = item
                    while isinstance(temp, list) and len(temp) > 0 and isinstance(temp[0], list):
                        temp = temp[0]
                    new_embeddings.append(temp)
            else:
                print(f"Error encoding batch starting at {i}. Response: {response}")
                return
        if len(new_embeddings) == len(entities):
            self.entities = entities
            self.embeddings = new_embeddings
            with open(self.embeddings_path, "w") as f:
                json.dump({
                    "entities": self.entities,
                    "embeddings": self.embeddings,
                    "model": self.model_id
                }, f)
            print(f"Successfully cached {len(entities)} embeddings.")
    def load_embeddings(self):
        if os.path.exists(self.embeddings_path):
            try:
                with open(self.embeddings_path, "r") as f:
                    data = json.load(f)
                # Check if cached for the same model
                if data.get("model") != self.model_id:
                    return False
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

        query_embedding_list = self._query_api([query])
        if not isinstance(query_embedding_list, list) or not query_embedding_list:
            return []
        # Extract and flatten query embedding
        query_embedding = query_embedding_list[0]
        while isinstance(query_embedding, list) and len(query_embedding) > 0 and isinstance(query_embedding[0], list):
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

# -------------------- SERVICES --------------------
def get_wikipedia_image(query):
    """Fallback to fetch image from Wikipedia if search fails."""
    try:
        # Simple heuristic: capitalize first letter for Wikipedia
        term = query.title().replace(' ', '_')
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{term}"
        headers = {"User-Agent": "MyWaterBot_AI_Bot/1.0 (support@mywaterbot.ai)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "thumbnail" in data:
                return data["thumbnail"]["source"]
    except Exception:
        pass
    return None

def get_image_url(query):
    """Fetches a relevant image URL using DuckDuckGo search with Wikipedia fallback."""
    try:
        with DDGS() as ddgs:
            # We add 'groundwater' or similar context to refine results if needed,
            # but for specific terms like 'aquifer', 'borewell', it should be fine.
            results = ddgs.images(query, max_results=1)
            if results:
                return results[0]['image']
    except Exception as e:
        print(f"Image search error for '{query}': {e}")

    return get_wikipedia_image(query)

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

# -------------------- LAYERED RESPONSES --------------------
LAYERED_METADATA = {
    "groundwater": {
        "why": "It's the primary source of water for half of the world's population and essential for agriculture.",
        "impact": "Depletion threatens food security and domestic water supply.",
        "tip": "Reduce wastage in households and adopt rainwater harvesting."
    },
    "aquifer": {
        "why": "Acts as a natural underground reservoir for storing water.",
        "impact": "Over-extraction can cause land subsidence and permanent loss of storage capacity.",
        "tip": "Protect recharge areas from urban sprawl and pollution."
    },
    "recharge": {
        "why": "It's the natural process that keeps our groundwater levels stable.",
        "impact": "Low recharge leads to dropping water tables and drying wells.",
        "tip": "Use check dams and percolation tanks to enhance natural recharge."
    },
    "extraction": {
        "why": "High extraction rates indicate we are using water faster than nature can replenish it.",
        "impact": "Leads to water stress, saline ingress in coastal areas, and higher pumping costs.",
        "tip": "Switch to water-efficient irrigation methods like drip or sprinklers."
    }
}

def format_layered_response(term, definition):
    meta = LAYERED_METADATA.get(term.lower(), {
        "why": "Crucial for understanding water sustainability and resource management.",
        "impact": "Directly affects long-term water availability and quality for future generations.",
        "tip": "Support local water conservation initiatives and stay informed about water levels."
    })
    return (
        f"**Definition:** {definition}\n\n"
        f"**Why it matters:** {meta['why']}\n\n"
        f"**Impact/Interpretation:** {meta['impact']}\n\n"
        f"**Actionable Tip:** {meta['tip']}"
    )

# -------------------- EXPLANATION ENGINE --------------------
def explain_extraction(name, value):
    if value <= 70:
        status = "relatively safe"
        meaning = "groundwater use is within sustainable limits"
        impact = "Minimal impact on water table; sustainable for future use."
        tip = "Maintain current practices and consider rainwater harvesting to stay safe."
    elif value <= 100:
        status = "stressed"
        meaning = "water usage is close to or exceeding recharge capacity"
        impact = "Lowering water tables; increased pumping costs; potential for seasonal scarcity."
        tip = "Reduce water-intensive crops; adopt drip irrigation; implement community-led recharge."
    else:
        status = "over-exploited"
        meaning = "groundwater is being extracted much faster than it can recharge"
        impact = "Rapidly falling water levels; drying borewells; long-term ecological damage; potential land subsidence."
        tip = "Urgent: Stop new borewells; shift to millets; mandatory rainwater harvesting; artificial recharge."

    return (
        f"**Definition:** Average groundwater extraction of {value}% for {name.title()}.\n\n"
        f"**Why it matters:** It indicates the balance between usage and natural replenishment.\n\n"
        f"**Impact/Interpretation:** This places it in a **{status}** category. {meaning}. {impact}\n\n"
        f"**Actionable Tip:** {tip}"
    )

def generate_data_explanation(data):
    if not data:
        return "I don't have enough data to provide an explanation."

    if len(data) == 1:
        return explain_extraction(data[0]['name'], data[0]['extraction'])

    # Comparison logic for multiple items
    sorted_data = sorted(data, key=lambda x: x['extraction'], reverse=True)
    highest = sorted_data[0]
    lowest = sorted_data[-1]

    explanation = f"### Data Comparison & Explanation\n\n"
    explanation += f"This chart compares the groundwater extraction levels of {len(data)} regions. "
    explanation += f"**{highest['name'].title()}** shows the highest extraction rate at **{highest['extraction']}%**, "

    if highest['extraction'] > 100:
        explanation += "which is categorized as **over-exploited**. "
    elif highest['extraction'] > 70:
        explanation += "which is **stressed**. "
    else:
        explanation += "which is still within **relatively safe** limits. "

    explanation += f"Meanwhile, **{lowest['name'].title()}** has the lowest rate among those shown at **{lowest['extraction']}%**. "

    gap = highest['extraction'] - lowest['extraction']
    if gap > 30:
        explanation += f"The gap of {round(gap, 2)}% highlights a significant regional disparity in water usage and recharge balance. "

    explanation += "\n\n**Actionable Insight:** Regions with extraction above 70% should prioritize water conservation and crop diversification to ensure long-term sustainability."

    return explanation

# -------------------- SUGGESTION ENGINE --------------------
def get_suggestions(user_input, found_data=None):
    suggestions = ["Conservation tips", "What is an aquifer?", "Show India map"]

    if found_data:
        # Contextual next-steps for locations
        loc_name = found_data[0]['name'].title()
        suggestions = [
            f"Why is {loc_name} stressed?",
            f"Show trend for {loc_name}",
            f"How to reduce extraction in {loc_name}"
        ]
        if len(found_data) > 1:
            suggestions.append("Show chart")
    elif "why" in user_input:
        suggestions.insert(0, "Compare Punjab and Bihar")
    elif any(k in user_input for k in ["tip", "conservation", "harvesting", "farming"]):
        suggestions.insert(0, "Search a state like Punjab")
    elif "aquifer" in user_input:
        suggestions.insert(0, "What is a water table?")
    elif "groundwater" in user_input:
        suggestions.insert(0, "How is groundwater recharged?")

    seen = set()
    unique = []
    for s in suggestions:
        if s.lower() not in seen:
            unique.append(s)
            seen.add(s.lower())
    return unique[:3]

# -------------------- VISUAL UTILS --------------------
def detect_map_request(user_input):
    map_keywords = ["map", "show map", "india map", "visualize on map"]
    return any(k in user_input for k in map_keywords)

def get_visual_data(visual_type, data, context=None):
    if visual_type == "status_card":
        # data is a single location dict: {"name": "...", "extraction": ...}
        name = data["name"]
        val = data["extraction"]
        category = "Safe"
        if val > 100: category = "Over-exploited"
        elif val > 70: category = "Stressed"

        name_lower = name.lower()
        return {
            "name": name.title(),
            "extraction": val,
            "category": category,
            "trend": "Stable",
            "mainCause": WHY_MAP.get(name_lower, "Intensive agricultural and domestic usage."),
            "topRisk": f"{CONTAMINANT_DATA[name_lower][0]} contamination" if name_lower in CONTAMINANT_DATA else "Water table decline",
            "recommendedAction": "Implement rainwater harvesting and switch to drip irrigation." if val > 70 else "Maintain sustainable usage and monitor levels."
        }

    elif visual_type == "comparison_bars":
        # data is a list of location dicts
        res = []
        for d in data:
            val = d["extraction"]
            cat = "Safe"
            if val > 100: cat = "Over-exploited"
            elif val > 70: cat = "Stressed"
            res.append({
                "name": d["name"].title(),
                "extraction": val,
                "category": cat
            })
        # Sort by extraction descending
        return sorted(res, key=lambda x: x["extraction"], reverse=True)

    elif visual_type == "risk_alert":
        # data is a list of contaminants
        return {
            "contaminantList": data,
            "healthRisk": f"Long-term exposure to {', '.join(data)} can cause serious health issues like fluorosis or arsenicosis.",
            "safeForDrinking": False,
            "suggestedMitigation": "Use RO filtration, activated alumina for fluoride removal, or seek alternative safe water sources."
        }

    elif visual_type == "action_panel":
        return {
            "householdActions": [
                "Install low-flow fixtures and dual-flush toilets.",
                "Harvest rooftop rainwater for non-potable use.",
                "Fix all leaks in pipes and faucets immediately."
            ],
            "farmingActions": [
                "Switch to drip or sprinkler irrigation systems.",
                "Grow climate-resilient crops like millets and pulses.",
                "Use organic mulching to retain soil moisture."
            ],
            "communityActions": [
                "Construct check dams and percolation tanks.",
                "Participate in local Water User Associations.",
                "Protect and restore local traditional water bodies."
            ]
        }
    return None

# -------------------- MAIN API --------------------
@app.post("/ask")
async def ask_bot(item: WaterQuery, request: Request):
    user_input = item.message.strip().lower()
    is_map_requested = detect_map_request(user_input)

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
            explanation = generate_data_explanation(data)
            v_type = "comparison_bars" if len(data) > 1 else "status_card"
            v_data = get_visual_data(v_type, data if len(data) > 1 else data[0])
            last_data_cache["data"] = []
            return {
                "text": f"Here’s a visual breakdown of the data:\n\n{explanation}",
                "chartData": data,
                "visualType": v_type,
                "visualData": v_data,
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
            "text": "No problem! What would you like to do next? You can ask me:\n\n"
                    "* **'Why is [State] stressed?'** to learn the causes.\n"
                    "* **'What is an aquifer?'** for a definition.\n"
                    "* **'Compare [District A] and [District B]'** for more data.",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }

    # 3. UNIFIED SEMANTIC SEARCH (Priority 1)
    results = semantic_search.search(user_input, threshold=0.65)

    # Keyword fallback if semantic search fails or is uninitialized
    if not results:
        states_list = getattr(request.app.state, "states_list", [])
        districts_list = getattr(request.app.state, "districts_list", [])
        # Simple match
        for s in states_list:
            if s.lower() in user_input:
                results.append({"name": s, "score": 1.0})
        for d in districts_list:
            if d.lower() in user_input:
                results.append({"name": d, "score": 1.0})

    if results:
        best_match = results[0]["name"]
        match_key = best_match.lower()

        # --- A. CHECK FOR "WHY" INTENT FIRST ---
        # This ensures "Why is Punjab stressed?" doesn't just return a data table.
        if "why" in user_input and match_key in WHY_MAP:
            img_url = await run_in_threadpool(get_image_url, f"{best_match} groundwater depth map district wise") if is_map_requested else None
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{WHY_MAP[match_key]}",
                "chartData": [],
                "visualType": "action_panel",
                "visualData": get_visual_data("action_panel", None),
                "imageUrl": img_url,
                "showLegend": True if img_url else False,
                "suggestions": get_suggestions(user_input)
            }

        # --- B. CHECK KNOWLEDGE BASE (Definitions) ---
        if match_key in KNOWLEDGE_BASE:
            img_url = await run_in_threadpool(get_image_url, best_match) if is_map_requested else None
            layered_text = format_layered_response(best_match, KNOWLEDGE_BASE[match_key])
            return {
                "text": f"### {best_match.title()}\n\n{layered_text}",
                "chartData": [],
                "imageUrl": img_url,
                "suggestions": get_suggestions(user_input)
            }

        # --- C. CHECK CONSERVATION TIPS ---
        if match_key in TIPS:
            img_url = await run_in_threadpool(get_image_url, best_match) if is_map_requested else None
            return {
                "text": f"### {best_match.title()} Tip\n\n{TIPS[match_key]}",
                "chartData": [],
                "visualType": "action_panel",
                "visualData": get_visual_data("action_panel", None),
                "imageUrl": img_url,
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

                unified_responses = []
                for d in found_data:
                    name_lower = d["name"].lower()

                    # 1. Extraction Explanation (Layered)
                    explanation = explain_extraction(d["name"], d["extraction"])

                    # 2. Root Causes from WHY_MAP
                    cause_text = ""
                    if name_lower in WHY_MAP:
                        cause_text = f"\n\n**Root Causes:** {WHY_MAP[name_lower]}"

                    # 3. Contaminant Warnings
                    contaminant_text = ""
                    if name_lower in CONTAMINANT_DATA:
                        cons = ", ".join(CONTAMINANT_DATA[name_lower])
                        contaminant_text = f"\n\n**Note:** {d['name']} has reported high levels of {cons}."

                    unified_responses.append(f"### {d['name'].title()}\n{explanation}{cause_text}{contaminant_text}")

                full_response = "\n\n---\n\n".join(unified_responses)
                intro = "Groundwater extraction measures usage relative to natural recharge.\n\n" if is_usage_query else ""

                # Fetch image for the locations found
                img_url = None
                if is_map_requested:
                    if len(found_data) > 1:
                        # Comparison query for multiple states/districts
                        names = [d['name'] for d in found_data]
                        img_query = f"{' and '.join(names[:2])} groundwater depth comparison map"
                    else:
                        img_query = f"{found_data[0]['name']} groundwater depth map district wise"
                    img_url = await run_in_threadpool(get_image_url, img_query)

                v_type = "comparison_bars" if len(found_data) > 1 else "status_card"
                v_data = get_visual_data(v_type, found_data if len(found_data) > 1 else found_data[0])

                # Override with risk_alert if it's a single location and has contaminants
                if len(found_data) == 1 and found_data[0]["name"].lower() in CONTAMINANT_DATA:
                    v_type = "risk_alert"
                    v_data = get_visual_data("risk_alert", CONTAMINANT_DATA[found_data[0]["name"].lower()])

                return {
                    "text": f"{intro}{full_response}\n\nWould you like a chart? (Yes/No)",
                    "chartData": [],
                    "visualType": v_type,
                    "visualData": v_data,
                    "imageUrl": img_url,
                    "showLegend": True if img_url else False,
                    "suggestions": get_suggestions(user_input, found_data)
                }

        except Exception as e:
            return {"text": f"Database error: {str(e)}", "chartData": [], "suggestions": get_suggestions(user_input)}

        # Fallback for WHY_MAP if "why" wasn't in query but it's the best match and not a location
        if match_key in WHY_MAP:
            img_url = await run_in_threadpool(get_image_url, f"{best_match} groundwater stress") if is_map_requested else None
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{WHY_MAP[match_key]}",
                "chartData": [],
                "visualType": "action_panel",
                "visualData": get_visual_data("action_panel", None),
                "imageUrl": img_url,
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
        "message": "MyWaterBot AI Groundwater API is running",
        "endpoints": {
            "ask": "/ask (POST)",
            "get-news": "/get-news (GET)",
            "health": "/ (GET)"
        }
    }
