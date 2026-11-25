/* API client.
 *
 * The shell runs in two modes:
 *   live — same origin as the FastAPI app (`/v1/...`), real data
 *   demo — no server reachable (opened as a file, or the API is down): seeded demo
 *          data so the screen can be reviewed without the stack running
 *
 * Nothing in the UI changes between modes except the small status toast and the
 * "demo" marker on the build stamp.
 */
(function () {
  const DEMO_ORIGIN = { lat: 29.9562, lon: 78.1707 }; // Har Ki Pauri area, used for demo distances

  const DEMO = {
    alerts: [
      {
        id: "a1",
        kind: "critical",
        category: "crowd",
        title_i18n: {
          hi: "हर की पौड़ी पर अत्यधिक भीड़",
          en: "Very heavy crowd at Har Ki Pauri",
          bn: "হর কি পৌড়িতে অতিরিক্ত ভিড়"
        },
        body_i18n: {
          hi: "कृपया कुशावर्त घाट की ओर जाएँ। शाही स्नान तक प्रवेश सीमित है।",
          en: "Please use Kushavart Ghat instead. Entry is restricted until the shahi snan ends.",
          bn: "অনুগ্রহ করে কুশাবর্ত ঘাটে যান। শাহি স্নান পর্যন্ত প্রবেশ সীমিত।"
        },
        zones: ["Z1"],
        requires_ack: true,
        created_at: new Date(Date.now() - 22 * 60000).toISOString()
      },
      {
        id: "a2",
        kind: "info",
        category: "service",
        title_i18n: {
          hi: "मुफ़्त पीने का पानी",
          en: "Free drinking water",
          bn: "বিনামূল্যে পানীয় জল"
        },
        body_i18n: {
          hi: "सभी घाटों पर जल स्टेशन खुले हैं। अपनी बोतल भरें।",
          en: "Water stations are open at every ghat. Refill your bottle.",
          bn: "সব ঘাটে জল স্টেশন খোলা। বোতল ভরে নিন।"
        },
        zones: [],
        requires_ack: false,
        created_at: new Date(Date.now() - 3 * 3600000).toISOString()
      }
    ],
    zones: [
      { zone_code: "Z1", name: "Har Ki Pauri", is_ghat: true, level: "red", capacity: 40000, estimated_persons: 37200, occupancy_ratio: 0.93, inflow_per_min: 410, outflow_per_min: 120, one_way_flow: "inward", is_closed: false },
      { zone_code: "Z2", name: "Kushavart Ghat", is_ghat: true, level: "amber", capacity: 22000, estimated_persons: 14800, occupancy_ratio: 0.67, inflow_per_min: 160, outflow_per_min: 140, one_way_flow: null, is_closed: false },
      { zone_code: "Z3", name: "Asthi Pravah Ghat", is_ghat: true, level: "green", capacity: 12000, estimated_persons: 4300, occupancy_ratio: 0.36, inflow_per_min: 60, outflow_per_min: 70, one_way_flow: null, is_closed: false },
      { zone_code: "Z4", name: "Pant Deep Parking", is_ghat: false, level: "amber", capacity: 900, estimated_persons: 610, occupancy_ratio: 0.68, inflow_per_min: 12, outflow_per_min: 9, one_way_flow: null, is_closed: false }
    ],
    snan: [
      { id: "s1", date: "2026-11-21", ghat_code: "Z1", ghat_name: "Har Ki Pauri", start_time: "04:00", end_time: "09:00", is_shahi: true, note: "Shahi snan — akhara processions" },
      { id: "s2", date: "2026-11-21", ghat_code: "Z2", ghat_name: "Kushavart Ghat", start_time: "05:30", end_time: "11:00", is_shahi: false, note: null },
      { id: "s3", date: "2026-11-21", ghat_code: "Z3", ghat_name: "Asthi Pravah Ghat", start_time: "05:30", end_time: "12:00", is_shahi: false, note: null }
    ],
    weather: { temperature_c: 18.5, rain_mm: 0, river_level_m: 2.9, river_level_warning: "normal", condition: "clear", recorded_at: new Date().toISOString() },
    facilities: [
      { id: "f1", category: "toilet", name: "Toilet block — Har Ki Pauri north", lat: 29.9571, lon: 78.1712, status: "open", owner_agency: "municipal" },
      { id: "f2", category: "toilet", name: "Toilet block — Kushavart", lat: 29.9538, lon: 78.1690, status: "full", owner_agency: "municipal" },
      { id: "f3", category: "water", name: "Jal station — Clock Tower", lat: 29.9549, lon: 78.1699, status: "open", owner_agency: "jal_sansthan" },
      { id: "f4", category: "water", name: "Jal station — Pant Deep", lat: 29.9602, lon: 78.1755, status: "open", owner_agency: "jal_sansthan" },
      { id: "f5", category: "medical", name: "First-aid post — Har Ki Pauri", lat: 29.9566, lon: 78.1701, status: "open", owner_agency: "health" },
      { id: "f6", category: "medical", name: "Base hospital camp — Bhupatwala", lat: 29.9721, lon: 78.1902, status: "open", owner_agency: "health" },
      { id: "f7", category: "police", name: "Police outpost — Har Ki Pauri", lat: 29.9558, lon: 78.1706, status: "open", owner_agency: "police" },
      { id: "f8", category: "police", name: "Lost & found centre — Mela office", lat: 29.9585, lon: 78.1668, status: "open", owner_agency: "police" },
      { id: "f9", category: "food", name: "Annakshetra — Sector 3", lat: 29.9520, lon: 78.1680, status: "open", owner_agency: "mela_admin" },
      { id: "f10", category: "food", name: "Langar — Sector 5", lat: 29.9610, lon: 78.1642, status: "open", owner_agency: "mela_admin" }
    ]
  };

  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000, toRad = Math.PI / 180;
    const dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  const API = {
    mode: "demo",
    version: null,
    token: localStorage.getItem("kumbh.token") || null,
    position: { lat: DEMO_ORIGIN.lat, lon: DEMO_ORIGIN.lon },

    async _fetch(path, options) {
      const opts = Object.assign({ headers: {} }, options || {});
      opts.headers["Accept"] = "application/json";
      if (this.token) opts.headers["Authorization"] = "Bearer " + this.token;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 4000);
      opts.signal = controller.signal;
      try {
        const response = await fetch(path, opts);
        if (!response.ok) throw new Error("HTTP " + response.status);
        return await response.json();
      } finally {
        clearTimeout(timer);
      }
    },

    async init() {
      if (location.protocol === "file:") return this.mode;
      try {
        const info = await this._fetch("/version");
        this.version = info;
        this.mode = "live";
      } catch (err) {
        this.mode = "demo";
      }
      return this.mode;
    },

    /* --------------------------------------------------------------- reads */
    async home() {
      if (this.mode !== "live") {
        return { alerts: DEMO.alerts, zones: DEMO.zones, snan: DEMO.snan, weather: DEMO.weather };
      }
      const lang = window.I18N.lang;
      const [alerts, zones, snan, weather] = await Promise.all([
        this._fetch("/v1/alerts?language=" + lang).catch(() => []),
        this._fetch("/v1/crowd/zones").catch(() => []),
        this._fetch("/v1/schedule/snan").catch(() => []),
        this._fetch("/v1/weather").catch(() => null)
      ]);
      return { alerts: alerts, zones: zones, snan: snan, weather: weather };
    },

    async nearby(category) {
      const query = category && category !== "all" ? "&category=" + encodeURIComponent(category) : "";
      if (this.mode !== "live") {
        const rows = DEMO.facilities
          .filter((f) => !category || category === "all" || f.category === category)
          .map((f) => {
            const distance = haversine(this.position.lat, this.position.lon, f.lat, f.lon);
            return { facility: f, distance_m: Math.round(distance), walk_minutes: Math.max(1, Math.round(distance / 75)) };
          })
          .sort((a, b) => a.distance_m - b.distance_m)
          .slice(0, 8);
        return rows;
      }
      const url = "/v1/map/nearby?lat=" + this.position.lat + "&lon=" + this.position.lon +
        "&radius_m=3000" + query;
      return this._fetch(url).catch(() => []);
    },

    async transportFacilities(layerKey) {
      if (this.mode !== "live") throw new Error("Transport information requires the live backend");
      return this._fetch("/v1/map/facilities?layer_key=" + encodeURIComponent(layerKey) + "&limit=200");
    },

    async stayFacilities(layerKey) {
      if (this.mode !== "live") throw new Error("Stay information requires the live backend");
      return this._fetch("/v1/map/facilities?layer_key=" + encodeURIComponent(layerKey) + "&limit=200");
    },

    async lostLocations() {
      if (this.mode !== "live") {
        const ghats = DEMO.zones.filter((zone) => zone.is_ghat)
          .map((zone) => ({ name: zone.name, category: "ghat", lat: null, lon: null }));
        const centres = DEMO.facilities.filter((facility) => facility.name.toLowerCase().includes("lost"));
        return ghats.concat(centres);
      }
      return this._fetch("/v1/map/facilities?category=ghat&limit=200").catch(() => []);
    },

    async createLostPerson(payload) {
      if (this.mode === "live") {
        return this._fetch("/v1/lost-persons", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      }
      const cases = JSON.parse(localStorage.getItem("kumbh.lostCases") || "{}");
      const caseNo = "LP-" + new Date().getFullYear() + "-" + Math.random().toString(36).slice(2, 8).toUpperCase();
      const result = Object.assign({}, payload, { photo_ref: null, case_no: caseNo, status: "Reported", created_at: new Date().toISOString() });
      cases[caseNo] = result;
      localStorage.setItem("kumbh.lostCases", JSON.stringify(cases));
      return result;
    },

    async trackLostPerson(caseNo, phone) {
      if (this.mode === "live") {
        return this._fetch("/v1/lost-persons/track?case_no=" + encodeURIComponent(caseNo) + "&phone=" + encodeURIComponent(phone));
      }
      const cases = JSON.parse(localStorage.getItem("kumbh.lostCases") || "{}");
      const found = cases[caseNo.toUpperCase()];
      if (!found || found.reporter_phone !== phone) throw new Error("Case or mobile number was not found");
      return { case_no: found.case_no, subject_name: found.subject_name, status: found.status,
        last_seen_place: found.last_seen_place, created_at: found.created_at };
    },

    async idCard() {
      if (this.mode !== "live" || !this.token) return null;
      return this._fetch("/v1/visitors/me/id-card").catch(() => null);
    },

    async me() {
      if (this.mode !== "live" || !this.token) return null;
      return this._fetch("/v1/visitors/me").catch(() => null);
    },

    async lostReports(filters) {
      const query = new URLSearchParams(filters || {}).toString();
      return this._fetch("/v1/lost-persons?" + query);
    },

    async lostReport(id) { return this._fetch("/v1/lost-persons/" + encodeURIComponent(id)); },

    async updateLostStatus(id, status) {
      return this._fetch("/v1/lost-persons/" + encodeURIComponent(id) + "/status", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: status })
      });
    },

    /* -------------------------------------------------------------- writes */
    async requestOtp(phone) {
      return this._fetch("/v1/auth/otp/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: phone })
      });
    },

    async verifyOtp(requestId, phone, otp) {
      const data = await this._fetch("/v1/auth/otp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, phone: phone, otp: otp })
      });
      this.token = data.access_token;
      localStorage.setItem("kumbh.token", data.access_token);
      return data;
    },

    async raiseSos(category, silent) {
      if (this.mode !== "live" || !this.token) {
        // Demo: the real app falls back to SMS when data fails.
        return { reference: "SOS-DEMO", channel: "demo", offline: true };
      }
      return this._fetch("/v1/sos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: category,
          lat: this.position.lat,
          lon: this.position.lon,
          silent: silent,
          channel: "data",
          client_ref: "app-" + Date.now()
        })
      });
    },

    /* Device position; falls back to the demo origin when permission is refused. */
    locate() {
      return new Promise((resolve) => {
        if (!navigator.geolocation) return resolve(this.position);
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            this.position = { lat: pos.coords.latitude, lon: pos.coords.longitude };
            resolve(this.position);
          },
          () => resolve(this.position),
          { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 }
        );
      });
    }
  };

  window.API = API;
})();
