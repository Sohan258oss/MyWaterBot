import React, { useState } from "react";
import IndiaMap from "@react-map/india";
import KarnatakaMap from "./KarnatakaMap";
import MapLegend from "./components/MapLegend";
import { groundwaterData } from "./data/groundwater";
import { getColor } from "./utils/mapUtils";

const GroundwaterMap = () => {
  const [selectedState, setSelectedState] = useState(null);
  const [view, setView] = useState("india"); // "india" or "karnataka"

  const cityColors = {};
  Object.keys(groundwaterData).forEach((state) => {
    cityColors[state] = getColor(groundwaterData[state]);
  });

  const handleSelect = (state) => {
    setSelectedState(state);
    if (state === "Karnataka") {
      setView("karnataka");
    }
  };

  if (view === "karnataka") {
    return <KarnatakaMap onBack={() => setView("india")} />;
  }

  return (
    <div className="map-container" role="region" aria-label="India Groundwater Depth Map">
      {selectedState ? (
        <div className="state-details">
          <span className="state-name">{selectedState}</span>
          <span className="state-value">{groundwaterData[selectedState] || "Data not available"} mbgl</span>
        </div>
      ) : (
        <div className="state-details placeholder">
          Click on a state to view depth details
        </div>
      )}
      <div className="map-wrapper">
        <IndiaMap
          type="select-single"
          size={600}
          mapColor="#eee"
          strokeColor="#fff"
          strokeWidth={0.5}
          cityColors={cityColors}
          hints={true}
          hintBackgroundColor="white"
          hintTextColor="black"
          onSelect={handleSelect}
        />
      </div>

      <MapLegend />
    </div>
  );
};

export default GroundwaterMap;
