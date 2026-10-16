/** Latitude and longitude of the airports the route map can place, by IATA code. Monty's
 *  travel backend is simulated and accepts any code; the map draws only the ones listed here. */
export const AIRPORTS: Record<string, [lat: number, lon: number]> = {
  ATL: [33.64, -84.43], AUS: [30.19, -97.67], BNA: [36.12, -86.68], BOS: [42.36, -71.01],
  BUR: [34.2, -118.36], BWI: [39.18, -76.67], CLE: [41.41, -81.85], CLT: [35.21, -80.94],
  CMH: [39.99, -82.89], CVG: [39.05, -84.66], DCA: [38.85, -77.04], DEN: [39.86, -104.67],
  DFW: [32.9, -97.04], DTW: [42.21, -83.35], EWR: [40.69, -74.17], HNL: [21.32, -157.92],
  IAD: [38.95, -77.46], IAH: [29.98, -95.34], IND: [39.72, -86.29], JFK: [40.64, -73.78],
  LAS: [36.08, -115.15], LAX: [33.94, -118.41], LGA: [40.78, -73.87], LGB: [33.82, -118.15],
  MCI: [39.3, -94.71], MCO: [28.43, -81.31], MIA: [25.79, -80.29], MSP: [44.88, -93.22],
  MSY: [29.99, -90.26], OAK: [37.72, -122.22], ORD: [41.97, -87.91], PDX: [45.59, -122.6],
  PHL: [39.87, -75.24], PHX: [33.43, -112.01], PIT: [40.49, -80.23], RDU: [35.88, -78.79],
  SAN: [32.73, -117.19], SAT: [29.53, -98.47], SEA: [47.45, -122.31], SFO: [37.62, -122.38],
  SJC: [37.36, -121.93], SLC: [40.79, -111.98], SMF: [38.7, -121.59], STL: [38.75, -90.37],
  TPA: [27.98, -82.53], ANC: [61.17, -149.99], SNA: [33.68, -117.87], FLL: [26.07, -80.15],
  MDW: [41.79, -87.75], HOU: [29.65, -95.28], DAL: [32.85, -96.85], OGG: [20.9, -156.43],
  SJU: [18.44, -66.0], YYC: [51.13, -114.01],
  YYZ: [43.68, -79.63], YVR: [49.19, -123.18], YUL: [45.47, -73.74], MEX: [19.44, -99.07],
  CUN: [21.04, -86.87],
  LHR: [51.47, -0.45], LGW: [51.15, -0.19], CDG: [49.01, 2.55], AMS: [52.31, 4.76],
  FRA: [50.04, 8.56], MUC: [48.35, 11.79], MAD: [40.49, -3.57], BCN: [41.3, 2.08],
  FCO: [41.8, 12.25], ZRH: [47.46, 8.55], DUB: [53.42, -6.27], LIS: [38.77, -9.13],
  CPH: [55.62, 12.66], ARN: [59.65, 17.92], OSL: [60.19, 11.1], IST: [41.26, 28.74],
  GVA: [46.24, 6.11], BSL: [47.59, 7.53], VIE: [48.11, 16.57], PRG: [50.1, 14.26],
  BRU: [50.9, 4.48], ATH: [37.94, 23.94], EDI: [55.95, -3.37], MAN: [53.35, -2.27],
  NCE: [43.66, 7.21], HEL: [60.32, 24.96], WAW: [52.17, 20.97], BUD: [47.44, 19.26],
  KEF: [63.99, -22.61], TLV: [32.01, 34.89],
  DXB: [25.25, 55.36], DOH: [25.27, 51.61], CAI: [30.12, 31.41],
  HND: [35.55, 139.78], NRT: [35.77, 140.39], ICN: [37.46, 126.44], PEK: [40.08, 116.58],
  PVG: [31.14, 121.81], HKG: [22.31, 113.91], SIN: [1.36, 103.99], BKK: [13.69, 100.75],
  DEL: [28.56, 77.1], BOM: [19.09, 72.87], SYD: [-33.95, 151.18], MEL: [-37.67, 144.84],
  AKL: [-37.01, 174.79], GRU: [-23.43, -46.47], EZE: [-34.82, -58.54], BOG: [4.7, -74.15],
  LIM: [-12.02, -77.11], SCL: [-33.39, -70.79], JNB: [-26.14, 28.24], CPT: [-33.97, 18.6],
};

/** Each city's main airport, so a hotel searched by city name lands in the right place. */
const CITY_AIRPORTS: Record<string, string> = {
  "new york": "JFK", "new york city": "JFK", nyc: "JFK", manhattan: "JFK", brooklyn: "JFK",
  london: "LHR", paris: "CDG", zurich: "ZRH", "zürich": "ZRH", geneva: "GVA", basel: "BSL",
  "san francisco": "SFO", "los angeles": "LAX", chicago: "ORD", boston: "BOS", seattle: "SEA",
  atlanta: "ATL", miami: "MIA", denver: "DEN", dallas: "DFW", houston: "IAH", "las vegas": "LAS",
  orlando: "MCO", washington: "DCA", "washington dc": "DCA", "washington, dc": "DCA",
  philadelphia: "PHL", austin: "AUS", nashville: "BNA", "new orleans": "MSY", honolulu: "HNL",
  "san diego": "SAN", portland: "PDX", phoenix: "PHX", "salt lake city": "SLC",
  minneapolis: "MSP", detroit: "DTW", "san jose": "SJC", oakland: "OAK", charlotte: "CLT",
  toronto: "YYZ", vancouver: "YVR", montreal: "YUL", "mexico city": "MEX", cancun: "CUN",
  amsterdam: "AMS", frankfurt: "FRA", munich: "MUC", madrid: "MAD", barcelona: "BCN",
  rome: "FCO", dublin: "DUB", lisbon: "LIS", copenhagen: "CPH", stockholm: "ARN", oslo: "OSL",
  vienna: "VIE", prague: "PRG", brussels: "BRU", athens: "ATH", edinburgh: "EDI",
  manchester: "MAN", nice: "NCE", helsinki: "HEL", warsaw: "WAW", budapest: "BUD",
  reykjavik: "KEF", istanbul: "IST", "tel aviv": "TLV", dubai: "DXB", doha: "DOH", cairo: "CAI",
  tokyo: "HND", seoul: "ICN", beijing: "PEK", shanghai: "PVG", "hong kong": "HKG",
  singapore: "SIN", bangkok: "BKK", delhi: "DEL", "new delhi": "DEL", mumbai: "BOM",
  sydney: "SYD", melbourne: "MEL", auckland: "AKL", "sao paulo": "GRU", "são paulo": "GRU",
  "buenos aires": "EZE", bogota: "BOG", lima: "LIM", santiago: "SCL", johannesburg: "JNB",
  "cape town": "CPT",
};

/** The airport for a city name, ignoring case, accents in the table, and a trailing region
 *  ("Zurich, Switzerland"). Undefined for a city the map doesn't know. */
export function airportForCity(city: string): string | undefined {
  const name = city.toLowerCase().trim();
  return CITY_AIRPORTS[name] ?? CITY_AIRPORTS[name.split(",")[0].trim()];
}
