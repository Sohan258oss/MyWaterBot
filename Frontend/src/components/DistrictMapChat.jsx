import React, { useState } from "react";
import MapLegend from "./MapLegend";
import { karnatakaDistrictPaths } from "../data/karnataka_paths";

// Color scale for Extraction Percentage (%)
const getExtractionColor = (extraction) => {
  if (extraction <= 70) return "#2ecc71"; // Safe - Green
  if (extraction <= 90) return "#f1c40f"; // Semi-Critical - Yellow
  if (extraction <= 100) return "#e67e22"; // Critical - Orange
  return "#e74c3c"; // Over-Exploited - Red
};

const DistrictMapChat = ({ stateName, districtData }) => {
  const [hoveredDistrict, setHoveredDistrict] = useState(null);

  // For now, we only have paths for Karnataka
  const hasPaths = stateName?.toLowerCase() === "karnataka";
  const paths = hasPaths ? karnatakaDistrictPaths : null;

  // Convert districtData array to a map for easy lookup
  const dataMap = (districtData || []).reduce((acc, curr) => {
    acc[curr.name.toLowerCase()] = curr.extraction;
    return acc;
  }, {});

  if (!districtData || districtData.length === 0) {
    return null;
  }

  return (
    <div className="district-map-chat">
      <h4 className="map-title-chat">{stateName} - District Wise Extraction</h4>

      {hasPaths ? (
        <div className="map-wrapper-chat">
          <svg
            viewBox="0 0 600 800"
            className="state-svg-chat"
            preserveAspectRatio="xMidYMid meet"
          >
            {Object.entries(paths).map(([name, path]) => {
              const val = dataMap[name.toLowerCase()];
              return (
                <path
                  key={name}
                  d={path}
                  fill={val !== undefined ? getExtractionColor(val) : "#eee"}
                  stroke="#fff"
                  strokeWidth="1"
                  onMouseEnter={() => setHoveredDistrict({ name, val })}
                  onMouseLeave={() => setHoveredDistrict(null)}
                  className="district-path-chat"
                >
                  <title>{`${name}: ${val !== undefined ? val + '%' : 'No data'}`}</title>
                </path>
              );
            })}
          </svg>

          {hoveredDistrict && (
            <div className="district-info-overlay">
              <strong>{hoveredDistrict.name}</strong>: {hoveredDistrict.val !== undefined ? hoveredDistrict.val + '%' : 'No data'}
            </div>
          )}
        </div>
      ) : (
        <div className="no-map-fallback">
          <p className="fallback-text">Interactive map for {stateName} is coming soon! Here is the data:</p>
          <div className="district-list-chat">
            {districtData.map((d, i) => (
              <div key={i} className="district-item-chat">
                <span className="dot" style={{ backgroundColor: getExtractionColor(d.extraction) }}></span>
                <span className="name">{d.name}</span>
                <span className="value">{d.extraction}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="chat-legend-mini">
        <div className="legend-item-mini">
          <span className="box safe"></span> <span>Safe (&le;70%)</span>
        </div>
        <div className="legend-item-mini">
          <span className="box semi"></span> <span>Semi-Critical (70-90%)</span>
        </div>
        <div className="legend-item-mini">
          <span className="box critical"></span> <span>Critical (90-100%)</span>
        </div>
        <div className="legend-item-mini">
          <span className="box over"></span> <span>Over-Exploited (&gt;100%)</span>
        </div>
      </div>
    </div>
  );
};

export default DistrictMapChat;
