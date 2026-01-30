import React, { useState } from "react";
import IndiaMap from "@react-map/india";
import { groundwaterData } from "./data/groundwater";

const getColor = (depth) => {
  if (depth <= 2) return "#2ecc71"; // Green
  if (depth <= 5) return "#00b894"; // Tropical Green
  if (depth <= 10) return "#f1c40f"; // Yellow
  if (depth <= 20) return "#e67e22"; // Orange
  if (depth <= 40) return "#e74c3c"; // Red
  return "#8b0000"; // Dark Red for >40
};

const GroundwaterMap = () => {
  const [selectedState, setSelectedState] = useState(null);

  const cityColors = {};
  Object.keys(groundwaterData).forEach((state) => {
    cityColors[state] = getColor(groundwaterData[state]);
  });

  const handleSelect = (state) => {
    setSelectedState(state);
  };

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

      <div className="map-legend">
        <h3>Depth to Water Level (mbgl)</h3>
        <div className="legend-items">
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#2ecc71" }}></span>
            <span>Very Shallow (0-2 mbgl)</span>
          </div>
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#00b894" }}></span>
            <span>Shallow (2-5 mbgl)</span>
          </div>
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#f1c40f" }}></span>
            <span>Moderate (5-10 mbgl)</span>
          </div>
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#e67e22" }}></span>
            <span>Moderately Deep (10-20 mbgl)</span>
          </div>
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#e74c3c" }}></span>
            <span>Deep (20-40 mbgl)</span>
          </div>
          <div className="legend-item">
            <span className="box" style={{ backgroundColor: "#8b0000" }}></span>
            <span>Very Deep (&gt;40 mbgl)</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GroundwaterMap;
