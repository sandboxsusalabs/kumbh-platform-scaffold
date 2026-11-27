/* Kumbh Sahayak — visitor app shell logic.
 *
 * Everything on screen reads from window.API, which is the shared backend in live mode
 * and seeded demo data otherwise. No screen keeps its own copy of a fact, so a change
 * broadcast from the command dashboard appears here on the next load or SSE event.
 */
(function () {
  const t = (key, vars) => window.I18N.t(key, vars);
  const $ = (sel) => document.querySelector(sel);
  const esc = (value) =>
    String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (ch) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[ch],
    );

  const LOCALES = { hi: "hi-IN", en: "en-IN", bn: "bn-IN" };

  const state = {
    screen: "home",
    data: { alerts: [], zones: [], snan: [], weather: null },
    nearby: [],
    category: "all",
    profile: JSON.parse(localStorage.getItem("kumbh.profile") || "null"),
    idCard: null,
    sosCategory: "medical",
    readAlerts: new Set(JSON.parse(localStorage.getItem("kumbh.read") || "[]")),
    offlineTiles: localStorage.getItem("kumbh.offlineTiles") === "1",
    lostCase: null,
    lostSubmitting: false,
    lostPhoto: null,
    lostLocations: [],
  };

  /* ------------------------------------------------------------------ tiles */
  const TILES = [
    {
      key: "register",
      icon: "i-register",
      label: "tile.register",
      action: () => openRegister(),
    },
    {
      key: "map",
      icon: "i-map",
      label: "tile.map",
      tone: "calm",
      action: () => switchScreen("map"),
    },
    {
      key: "nearby",
      icon: "i-pin",
      label: "tile.nearby",
      tone: "calm",
      action: () => {
        switchScreen("map");
        setCategory("all");
      },
    },
    {
      key: "snan",
      icon: "i-water",
      label: "tile.snan",
      tone: "green",
      action: () => scrollTo("snanTitle"),
    },
    {
      key: "alerts",
      icon: "i-alert",
      label: "tile.alerts",
      tone: "alert-tile",
      action: () => switchScreen("alerts"),
    },
    {
      key: "lost",
      icon: "i-lost",
      label: "tile.lost",
      tone: "alert-tile",
      action: () => openLostReport(),
    },
    {
      key: "transport",
      icon: "i-bus",
      label: "tile.transport",
      action: () => navigateTransport(),
    },
    {
      key: "stay",
      icon: "i-stay",
      label: "tile.stay",
      action: () => navigateStay(),
    },
    {
      key: "food",
      icon: "i-food",
      label: "tile.food",
      tone: "green",
      action: () => {
        switchScreen("map");
        setCategory("food");
      },
    },
    {
      key: "medical",
      icon: "i-medical",
      label: "tile.medical",
      tone: "alert-tile",
      action: () => {
        switchScreen("map");
        setCategory("medical");
      },
    },
    {
      key: "helpline",
      icon: "i-phone",
      label: "tile.helpline",
      action: () => {
        window.location.href = "tel:112";
      },
    },
    {
      key: "crowd",
      icon: "i-crowd",
      label: "tile.crowd",
      action: () => scrollTo("crowdTitle"),
    },
  ];

  const SOS_CATEGORIES = [
    { key: "medical", icon: "i-medical" },
    { key: "police", icon: "i-police" },
    { key: "fire", icon: "i-alert" },
    { key: "lost_child", icon: "i-lost" },
    { key: "other", icon: "i-helpline" },
  ];

  const FACILITY_ICON = {
    toilet: "i-toilet",
    water: "i-water",
    medical: "i-medical",
    police: "i-police",
    food: "i-food",
    parking: "i-bus",
    bus_stop: "i-bus",
    railway: "i-bus",
    accommodation: "i-stay",
    info: "i-helpline",
    lost_found: "i-lost",
    fire: "i-alert",
    ghat: "i-water",
    temple: "i-stay",
    camp: "i-stay",
  };

  const HELP_ROWS = [
    { icon: "i-phone", label: "help.helpline", right: "112", href: "tel:112" },
    {
      icon: "i-helpline",
      label: "help.mela",
      right: "1800-000-000",
      href: "tel:1800000000",
    },
    { icon: "i-lost", label: "help.lost", action: () => openLostReport() },
    {
      icon: "i-flag",
      label: "help.complaint",
      action: () => stub("help.complaint", "POST /v1/feedback"),
    },
    { icon: "i-map", label: "help.language", action: () => openLang() },
    { icon: "i-register", label: "help.text", action: toggleLargeText },
  ];

  /* ------------------------------------------------------------- rendering */
  function renderChrome() {
    document.documentElement.lang = window.I18N.lang;
    document.title = t("app.name") + " — " + t("app.sub");
    $("#appName").textContent = t("app.name");
    $("#appSub").textContent = t("app.sub");
    $("#langBtn").textContent =
      { hi: "हिं", en: "EN", bn: "বাং" }[window.I18N.lang] || "हिं";
    $("#quickTitle").textContent = t("sec.quick");
    $("#snanTitle").textContent = t("sec.snan");
    $("#crowdTitle").textContent = t("sec.crowd");
    $("#tickerLabel").textContent = t("ticker.label");
    $("#mapTitle").textContent = t("map.title");
    $("#alertsTitle").textContent = t("alerts.title");
    $("#idTitle").textContent = t("id.title");
    $("#helpTitle").textContent = t("help.title");
    $("#sosLabel").textContent = t("sos.label");
    $("#sosSheetTitle").textContent = t("sos.title");
    $("#sosSheetSub").textContent = t("sos.sub");
    $("#sosConfirm").textContent = t("sos.confirm");
    $("#sosSilentLabel").textContent = t("sos.silent");
    $("#sosCancel").textContent = t("sos.cancel");
    $("#langTitle").textContent = t("lang.title");
    $("#navHome").textContent = t("nav.home");
    $("#navMap").textContent = t("nav.map");
    $("#navAlerts").textContent = t("nav.alerts");
    $("#navId").textContent = t("nav.id");
    $("#navHelp").textContent = t("nav.help");
    $("#mapPanelTitle").textContent = t("map.panel.title");
    $("#mapPanelSub").textContent = t("map.panel.sub");
    $("#mapHint").textContent = t("map.hint");
    $("#offlineBtn").textContent = state.offlineTiles
      ? t("map.offline.done")
      : t("map.offline");
    $("#helpNoteTitle").textContent = t("help.note.title");
    $("#helpNoteBody").textContent = t("help.note.body");

    const build =
      "v0.1.0 · " +
      (API.version ? API.version.env : "shell") +
      " · " +
      (API.mode === "live" ? "live" : "demo");
    $("#buildStamp").textContent = build;
    $("#buildStamp2").textContent = build;
  }

  function renderStatus() {
    const ghats = state.data.zones.filter((z) => z.is_ghat);
    const worst = ghats.some((z) => z.level === "red")
      ? "red"
      : ghats.some((z) => z.level === "amber")
        ? "amber"
        : "green";
    const hot =
      ghats.find((z) => z.level === "red") ||
      ghats.find((z) => z.level === "amber");
    const dot = $("#stripDot");
    dot.className = "dot" + (worst === "green" ? "" : " " + worst);
    const text =
      API.mode === "live"
        ? worst === "green"
          ? t("strip.ok")
          : t(worst === "red" ? "strip.red" : "strip.amber", {
              zone: hot ? hot.name : "",
            })
        : t("strip.offline");
    $("#stripText").textContent = text;
    $("#stripRight").textContent = new Date().toLocaleTimeString(
      LOCALES[window.I18N.lang] || "en-IN",
      { hour: "2-digit", minute: "2-digit" },
    );
  }

  function renderHome() {
    const profile = state.profile;
    $("#greeting").textContent = t("greeting", {
      name:
        profile && profile.name
          ? t("greeting.name", { name: profile.name })
          : "",
    });
    $("#today").textContent = new Date().toLocaleDateString(
      LOCALES[window.I18N.lang] || "en-IN",
      { weekday: "long", day: "numeric", month: "long" },
    );
    $("#dayBadge").innerHTML =
      t("day.badge") +
      "<br>" +
      new Date().toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
      });

    $("#tileGrid").innerHTML = TILES.map(
      (tile, index) => `
      <button class="tile ${tile.tone || ""}" data-tile="${index}">
        <span class="tile-ico"><svg class="ico"><use href="#${tile.icon}"/></svg></span>
        <span class="tile-label">${esc(t(tile.label))}</span>
      </button>`,
    ).join("");
    $("#tileGrid")
      .querySelectorAll("[data-tile]")
      .forEach((btn) => {
        btn.addEventListener("click", () =>
          TILES[Number(btn.dataset.tile)].action(),
        );
      });

    let reportsLink = document.getElementById("reportsLink");
    if (!reportsLink) {
      reportsLink = document.createElement("button");
      reportsLink.id = "reportsLink";
      reportsLink.className = "btn btn-primary";
      reportsLink.style.margin = "0 0 14px";
      reportsLink.addEventListener("click", () => navigateReports());
      $("#tileGrid").insertAdjacentElement("afterend", reportsLink);
    }
    reportsLink.textContent = reportT("viewAll");
    const critical = state.data.alerts.filter((a) => a.kind === "critical");
    $("#pinnedAlerts").innerHTML = critical
      .map((alert) => {
        const title =
          alert.title_i18n[window.I18N.lang] ||
          alert.title_i18n.hi ||
          alert.title_i18n.en;
        const body =
          alert.body_i18n[window.I18N.lang] ||
          alert.body_i18n.hi ||
          alert.body_i18n.en;
        return `<div class="alert-card critical" style="margin-bottom:12px">
        <div class="alert-head"><span class="alert-kind">${esc(t("alerts.critical"))}</span>
        <span class="alert-time">${esc(timeAgo(alert.created_at))}</span></div>
        <div class="alert-title">${esc(title)}</div>
        <div class="alert-body">${esc(body)}</div>
        <div class="alert-foot"><button class="btn btn-ghost" data-read="${esc(alert.id)}">${esc(t("alerts.read"))}</button></div>
      </div>`;
      })
      .join("");
    $("#pinnedAlerts")
      .querySelectorAll("[data-read]")
      .forEach((btn) => {
        btn.addEventListener("click", () => {
          state.readAlerts.add(btn.dataset.read);
          localStorage.setItem(
            "kumbh.read",
            JSON.stringify([...state.readAlerts]),
          );
          renderAlerts();
          toast(t("alerts.read"));
        });
      });

    const info = state.data.alerts.filter((a) => a.kind !== "critical");
    if (info.length) {
      const first = info[0];
      $("#ticker").hidden = false;
      $("#tickerText").textContent =
        (first.title_i18n[window.I18N.lang] || first.title_i18n.hi) +
        " — " +
        (first.body_i18n[window.I18N.lang] || first.body_i18n.hi);
    } else {
      $("#ticker").hidden = true;
    }

    const snan = state.data.snan.slice(0, 4);
    $("#snanList").innerHTML = snan.length
      ? snan
          .map(
            (slot) => `
      <div class="row">
        <span class="row-ico"><svg class="ico"><use href="#i-clock"/></svg></span>
        <div class="row-body">
          <div class="row-title">${esc(slot.ghat_name)}</div>
          <div class="row-sub">${esc(shortTime(slot.start_time))} – ${esc(shortTime(slot.end_time))}${slot.is_shahi ? " · " + esc(t("snan.shahi")) : ""}</div>
        </div>
        ${slot.is_shahi ? `<span class="row-right"><span class="level amber"><span class="dot"></span>${esc(t("snan.shahi"))}</span></span>` : ""}
      </div>`,
          )
          .join("")
      : `<div class="row"><div class="row-body"><div class="row-sub">${esc(t("alerts.empty"))}</div></div></div>`;

    const ghats = state.data.zones.filter((z) => z.is_ghat).slice(0, 5);
    $("#crowdList").innerHTML = ghats.length
      ? ghats
          .map(
            (zone) => `
      <div class="row">
        <span class="row-ico"><svg class="ico"><use href="#i-crowd"/></svg></span>
        <div class="row-body">
          <div class="row-title">${esc(zone.name)}</div>
          <div class="row-sub">${Math.round((zone.occupancy_ratio || 0) * 100)}% ${esc(t("crowd." + zone.level))}${zone.one_way_flow ? " · " + (zone.one_way_flow === "inward" ? "→" : "←") : ""}</div>
          <div class="crowd-progress" role="img" aria-label="${Math.round((zone.occupancy_ratio || 0) * 100)}%" style="--crowd-fill:${Math.max(0, Math.min(100, Math.round((zone.occupancy_ratio || 0) * 100)))}%"><span></span></div>
        </div>
        <span class="level ${esc(zone.level)}"><span class="dot"></span>${esc(t("crowd." + zone.level))}</span>
      </div>`,
          )
          .join("")
      : `<div class="row"><div class="row-body"><div class="row-sub">${esc(t("alerts.empty"))}</div></div></div>`;

    const weather = state.data.weather;
    $("#weatherCard").innerHTML = weather
      ? `
      <svg class="ico"><use href="#i-sun"/></svg>
      <div>
        <div class="weather-main">${Math.round(weather.temperature_c)}°C · ${esc(weather.condition)}</div>
        <div class="weather-sub">${esc(t("weather.river"))}: ${weather.river_level_m != null ? weather.river_level_m + " m" : "—"} · ${esc(t("weather." + (weather.river_level_warning || "normal")))}</div>
      </div>
      <span class="row-right">${esc(t("weather.title"))}</span>`
      : "";

    renderStatus();
  }

  function renderAlerts() {
    const list = state.data.alerts;
    $("#alertList").innerHTML = list.length
      ? list
          .map((alert) => {
            const title =
              alert.title_i18n[window.I18N.lang] ||
              alert.title_i18n.hi ||
              alert.title_i18n.en;
            const body =
              alert.body_i18n[window.I18N.lang] ||
              alert.body_i18n.hi ||
              alert.body_i18n.en;
            const critical = alert.kind === "critical";
            const read = state.readAlerts.has(alert.id);
            return `<article class="alert-card ${critical ? "critical" : ""}">
        <div class="alert-head">
          <span class="alert-kind">${esc(t(critical ? "alerts.critical" : "alerts.info"))}</span>
          <span class="alert-time">${esc(timeAgo(alert.created_at))}</span>
        </div>
        <div class="alert-title">${esc(title)}</div>
        <div class="alert-body">${esc(body)}</div>
        ${
          critical
            ? `<div class="alert-foot">
          <button class="btn btn-ghost" data-read="${esc(alert.id)}" ${read ? "disabled" : ""}>${esc(read ? t("alerts.read") + " ✓" : t("alerts.read"))}</button>
          ${read ? "" : `<span class="row-sub" style="align-self:center">${esc(t("alerts.pinned"))}</span>`}
        </div>`
            : ""
        }
      </article>`;
          })
          .join("")
      : `<p class="hint">${esc(t("alerts.empty"))}</p>`;

    $("#alertList")
      .querySelectorAll("[data-read]")
      .forEach((btn) => {
        btn.addEventListener("click", () => {
          state.readAlerts.add(btn.dataset.read);
          localStorage.setItem(
            "kumbh.read",
            JSON.stringify([...state.readAlerts]),
          );
          renderAlerts();
          renderHome();
        });
      });
  }

  function renderMap() {
    const chips = ["all", "toilet", "water", "medical", "police", "food"];
    $("#mapChips").innerHTML = chips
      .map(
        (chip) => `
      <button class="chip ${state.category === chip ? "is-active" : ""}" data-chip="${chip}">${esc(t("map.chip." + chip))}</button>`,
      )
      .join("");
    $("#mapChips")
      .querySelectorAll("[data-chip]")
      .forEach((btn) => {
        btn.addEventListener("click", () => setCategory(btn.dataset.chip));
      });

    $("#nearbyList").innerHTML = state.nearby.length
      ? state.nearby
          .map((item) => {
            const facility = item.facility;
            const distance =
              item.distance_m >= 1000
                ? t("unit.km", { km: (item.distance_m / 1000).toFixed(1) })
                : t("unit.m", { m: Math.round(item.distance_m) });
            return `<div class="row">
        <span class="row-ico"><svg class="ico"><use href="#${FACILITY_ICON[facility.category] || "i-pin"}"/></svg></span>
        <div class="row-body">
          <div class="row-title">${esc(facility.name)}</div>
          <div class="row-sub">${esc(distance)} · ${esc(t("unit.min", { n: item.walk_minutes }))}</div>
        </div>
        <span class="level ${facility.status === "open" ? "green" : facility.status === "full" ? "red" : "amber"}">
          <span class="dot"></span>${esc(facility.status)}
        </span>
      </div>`;
          })
          .join("")
      : `<div class="row"><div class="row-body"><div class="row-sub">${esc(t("map.empty"))}</div></div></div>`;
  }

  function navigateTransport() {
    const hash = "#/transport";
    if (location.hash !== hash)
      history.pushState({}, "", location.pathname + location.search + hash);
    renderTransport();
  }

  async function renderTransport() {
    switchScreen("transport");
    document.body.classList.add("transport-mode");
    const page = document.getElementById("transportPage");
    page.innerHTML = `<div class="transport-header"><h1>${esc(t("transport.title"))}</h1><button type="button" class="btn btn-ghost" id="transportBack">${esc(t("transport.back"))}</button></div><div id="transportContent" aria-live="polite"><p class="transport-state loading-state">${esc(t("transport.loading"))}</p></div>`;
    document
      .getElementById("transportBack")
      .addEventListener("click", () => switchScreen("home"));
    if (API.mode !== "live") {
      document.getElementById("transportContent").innerHTML =
        `<p class="transport-state error">${esc(t("transport.error"))}</p>`;
      return;
    }
    try {
      const layers = [
        { key: "bus_stands", title: "transport.bus" },
        { key: "parking", title: "transport.parking" },
        { key: "railway", title: "transport.railway" },
      ];
      const rows = await Promise.all(
        layers.map((layer) => API.transportFacilities(layer.key)),
      );
      const content = document.getElementById("transportContent");
      if (!content) return;
      content.innerHTML = `<div class="transport-grid">${layers
        .map((layer, index) => {
          const items = rows[index];
          const sectionIcon = layer.key === "bus_stands" ? "i-bus" : layer.key === "railway" ? "i-route" : "i-pin";
          return `<section class="transport-section"><h2><svg class="ico section-icon" aria-hidden="true"><use href="#${sectionIcon}"/></svg>${esc(t(layer.title))}</h2>${
            items.length
              ? items
                  .map((item) => {
                    const statusKey = [
                      "open",
                      "closed",
                      "full",
                      "crowded",
                    ].includes(item.status)
                      ? item.status
                      : "unknown";
                    const statusLabel =
                      statusKey === "unknown"
                        ? item.status
                        : t("transport.status." + statusKey);
                    const details = [];
                    if (item.zone_code)
                      details.push(
                        t("transport.zone", { zone: item.zone_code }),
                      );
                    if (item.capacity != null && item.occupied != null) {
                      details.push(
                        t("transport.capacity", {
                          available: Math.max(0, item.capacity - item.occupied),
                          capacity: item.capacity,
                        }),
                      );
                    }
                    if (item.opening_hours) details.push(item.opening_hours);
                    return `<article class="transport-item"><div class="transport-item-head"><h3>${esc(item.name)}</h3><span class="transport-status status-${esc(statusKey)}">${esc(statusLabel)}</span></div><p>${esc(details.join(" · ") || "—")}</p></article>`;
                  })
                  .join("")
              : `<p class="transport-empty">${esc(t("transport.empty"))}</p>`
          }</section>`;
        })
        .join(
          "",
        )}</div><aside class="transport-info"><strong>${esc(t("transport.info"))}</strong> <a href="tel:112">112</a></aside>`;
    } catch (_) {
      const content = document.getElementById("transportContent");
      if (content)
        content.innerHTML = `<p class="transport-state error">${esc(t("transport.error"))}</p>`;
    }
  }

  function navigateStay() {
    const hash = "#/stay";
    if (location.hash !== hash)
      history.pushState({}, "", location.pathname + location.search + hash);
    renderStay();
  }

  async function renderStay() {
    switchScreen("stay");
    document.body.classList.add("stay-mode");
    const page = document.getElementById("stayPage");
    page.innerHTML = `<div class="stay-header"><h1>${esc(t("stay.title"))}</h1><button type="button" class="btn btn-ghost" id="stayBack">${esc(t("stay.back"))}</button></div><div id="stayContent" aria-live="polite"><p class="stay-state loading-state">${esc(t("stay.loading"))}</p></div>`;
    document
      .getElementById("stayBack")
      .addEventListener("click", () => switchScreen("home"));
    if (API.mode !== "live") {
      document.getElementById("stayContent").innerHTML =
        `<p class="stay-state error">${esc(t("stay.error"))}</p>`;
      return;
    }
    try {
      const [accommodation, helpDesks] = await Promise.all([
        API.stayFacilities("accommodation"),
        API.stayFacilities("info_centres"),
      ]);
      const content = document.getElementById("stayContent");
      if (!content) return;
      const sections = [
        {
          title: "stay.camps", icon: "i-stay",
          items: accommodation.filter((item) => item.category === "camp"),
        },
        {
          title: "stay.dharamshalas", icon: "i-stay",
          items: accommodation.filter(
            (item) => item.category === "accommodation",
          ),
        },
        {
          title: "stay.hotels", icon: "i-stay",
          items: accommodation.filter(
            (item) => !["camp", "accommodation"].includes(item.category),
          ),
        },
        { title: "stay.helpDesks", icon: "i-helpline", items: helpDesks },
      ];
      const renderItem = (item) => {
        const statusKey = ["open", "closed", "full", "crowded"].includes(
          item.status,
        )
          ? item.status
          : "unknown";
        const details = [];
        if (item.zone_code)
          details.push(t("stay.zone", { zone: item.zone_code }));
        if (item.capacity != null && item.occupied != null) {
          details.push(
            t("stay.capacity", {
              available: Math.max(0, item.capacity - item.occupied),
              capacity: item.capacity,
            }),
          );
        }
        if (item.opening_hours) details.push(item.opening_hours);
        return `<article class="stay-item"><div class="stay-item-head"><h3>${esc(item.name)}</h3><span class="stay-status status-${esc(statusKey)}">${esc(t("stay.status." + statusKey))}</span></div><p>${esc(details.join(" · ") || "—")}</p></article>`;
      };
      content.innerHTML = `<div class="stay-grid">${sections.map((section) => `<section class="stay-section"><h2><svg class="ico section-icon" aria-hidden="true"><use href="#${section.icon}"/></svg>${esc(t(section.title))}</h2>${section.items.length ? section.items.map(renderItem).join("") : `<p class="stay-empty">${esc(t("stay.empty"))}</p>`}</section>`).join("")}</div><aside class="stay-info"><strong>${esc(t("stay.info"))}</strong> <a href="tel:112">112</a></aside>`;
    } catch (_) {
      const content = document.getElementById("stayContent");
      if (content)
        content.innerHTML = `<p class="stay-state error">${esc(t("stay.error"))}</p>`;
    }
  }

  function renderId() {
    const profile = state.profile;
    if (!profile) {
      $("#idBody").innerHTML = `
        <div class="card" style="padding:20px;text-align:center">
          <p style="margin:0 0 14px;color:#5b6480">${esc(t("id.not.registered"))}</p>
          <button class="btn btn-primary btn-block" id="idRegister">${esc(t("id.register"))}</button>
        </div>`;
      $("#idRegister").addEventListener("click", () => openRegister());
      return;
    }

    const card = state.idCard;
    const qr =
      card && card.qr_payload
        ? card.qr_payload
        : profile.ref || "KUMBH:VID:" + (profile.ref || "—");
    $("#idBody").innerHTML = `
      <div class="id-card">
        <div class="id-top">
          <div class="id-org">${esc(t("id.org"))}</div>
          <div class="id-name">${esc(profile.name)}</div>
          <div class="id-meta">${esc([profile.age ? String(profile.age) : null, profile.homeState].filter(Boolean).join(" · "))}</div>
        </div>
        <div class="id-body">
          <div class="qr-box">
            <div>
              <svg class="ico" style="width:30px;height:30px"><use href="#i-qr"/></svg>
              <div style="margin-top:6px;word-break:break-all;font-size:.6rem">${esc(qr)}</div>
            </div>
          </div>
          <div class="id-facts">
            <div>${esc(t("id.fact.language"))}: <b>${esc(window.I18N.labels[window.I18N.lang])}</b></div>
            <div>${esc(t("id.fact.emergency"))}: <b>${esc((profile.emergency && profile.emergency[0]) || "—")}</b></div>
            <div>${esc(t("id.ref"))}: <b>${esc((profile.ref || "").slice(0, 10))}</b></div>
          </div>
        </div>
        <div class="id-foot">
          <div class="id-warn">${esc(card ? t("id.warn") : t("id.qr.pending"))}</div>
        </div>
      </div>`;
  }

  function renderHelp() {
    $("#helpList").innerHTML = HELP_ROWS.map(
      (row, index) => `
      <div class="row ${row.href ? "" : "as-button"}" ${row.href ? "" : `data-help="${index}" role="button" tabindex="0"`}>
        <span class="row-ico"><svg class="ico"><use href="#${row.icon}"/></svg></span>
        <div class="row-body"><div class="row-title">${esc(t(row.label))}</div></div>
        ${row.right ? `<span class="row-right">${esc(row.right)}</span>` : `<svg class="ico row-chev" style="width:18px;height:18px"><use href="#i-chev"/></svg>`}
      </div>`,
    ).join("");

    $("#helpList")
      .querySelectorAll("[data-help]")
      .forEach((node) => {
        const row = HELP_ROWS[Number(node.dataset.help)];
        node.addEventListener("click", () => row.action && row.action());
      });
  }

  const LOST_TEXT = {
    en: {
      title: "Lost Person Reporting",
      danger: "If the person is in immediate danger, use SOS.",
      subtitle: "Share accurate details so nearby teams can begin searching.",
      trackLink: "Track Case Status",
      missing: "Missing person details",
      fullName: "Full name",
      age: "Age",
      gender: "Gender",
      choose: "Choose",
      male: "Male",
      female: "Female",
      other: "Other",
      photo: "Photo (optional, recommended)",
      photoHelp: "JPG or PNG · up to 5 MB",
      description: "Physical description",
      height: "Height",
      clothes: "Clothes",
      marks: "Identification marks",
      languages: "Languages spoken (optional)",
      medical: "Medical condition / special needs (optional)",
      lastSeen: "Last seen details",
      location: "Last seen location / ghat",
      notes: "Additional notes (optional)",
      count: "{n}/500",
      date: "Last seen date and time",
      reporter: "Reporter details",
      reporterName: "Reporter name",
      phone: "Mobile number",
      relation: "Relation with missing person",
      alternate: "Alternate contact number (optional)",
      currentLocation: "Current location / camp (optional)",
      submit: "Submit report",
      reset: "Reset / Cancel",
      trackTitle: "Track a case",
      caseId: "Case ID",
      track: "Check status",
      backReport: "Report a missing person",
      sent: "This case has been sent to the nearest Lost & Found centre and the control room.",
      caseStatus: "Status",
      reported: "Reported",
      details: "Report details",
      reportAnother: "Report another person",
      nearest:
        "Nearest Lost & Found centre and control room have been notified.",
      removePhoto: "Remove photo",
      photoTooLarge: "Photo must be 5 MB or smaller.",
      photoType: "Choose a JPG or PNG image.",
      required: "This field is required.",
      ageError: "Enter an age from 0 to 120.",
      phoneError: "Enter a valid 10-digit Indian mobile number.",
      future: "Date and time cannot be in the future.",
      submitError: "The report could not be submitted. Please try again.",
      trackError: "No case was found for that Case ID and mobile number.",
      nameMissing: "Missing person",
      reporterMobile: "Reporter mobile",
      saved: "DEMO MODE: This report is saved only in this browser.",
      demoSent:
        "Demo mode: no Lost & Found centre or control room was notified.",
      discardConfirm: "Discard the information entered in this report?",
      relationFamily: "Family member",
      relationFriend: "Friend",
      relationGuardian: "Guardian",
      photoUploaded: "Attached",
      underSearch: "Under Search",
      found: "Found",
      reunited: "Reunited",
    },
    hi: {
      title: "लापता व्यक्ति की रिपोर्ट",
      danger: "यदि व्यक्ति तत्काल खतरे में है, तो SOS का उपयोग करें।",
      subtitle: "खोज में मदद के लिए सही जानकारी दें।",
      trackLink: "केस की स्थिति देखें",
      missing: "लापता व्यक्ति का विवरण",
      fullName: "पूरा नाम",
      age: "आयु",
      gender: "लिंग",
      choose: "चुनें",
      male: "पुरुष",
      female: "महिला",
      other: "अन्य",
      photo: "फोटो (वैकल्पिक, अनुशंसित)",
      photoHelp: "JPG या PNG · अधिकतम 5 MB",
      description: "शारीरिक विवरण",
      height: "कद",
      clothes: "कपड़े",
      marks: "पहचान के निशान",
      languages: "बोली जाने वाली भाषाएँ (वैकल्पिक)",
      medical: "चिकित्सा स्थिति / विशेष आवश्यकता (वैकल्पिक)",
      lastSeen: "आखिरी बार देखे जाने का विवरण",
      location: "आखिरी बार देखा गया स्थान / घाट",
      notes: "अतिरिक्त जानकारी (वैकल्पिक)",
      count: "{n}/500",
      date: "आखिरी बार देखे जाने की तारीख और समय",
      reporter: "रिपोर्ट करने वाले का विवरण",
      reporterName: "रिपोर्टर का नाम",
      phone: "मोबाइल नंबर",
      relation: "लापता व्यक्ति से संबंध",
      alternate: "वैकल्पिक संपर्क नंबर (वैकल्पिक)",
      currentLocation: "वर्तमान स्थान / शिविर (वैकल्पिक)",
      submit: "रिपोर्ट भेजें",
      reset: "रीसेट / रद्द करें",
      trackTitle: "केस की स्थिति देखें",
      caseId: "केस आईडी",
      track: "स्थिति देखें",
      backReport: "लापता व्यक्ति की रिपोर्ट करें",
      sent: "यह केस निकटतम खोया-पाया केंद्र और नियंत्रण कक्ष को भेज दिया गया है।",
      caseStatus: "स्थिति",
      reported: "रिपोर्ट किया गया",
      details: "रिपोर्ट का विवरण",
      reportAnother: "दूसरे व्यक्ति की रिपोर्ट करें",
      nearest: "निकटतम खोया-पाया केंद्र और नियंत्रण कक्ष को सूचना दे दी गई है।",
      removePhoto: "फोटो हटाएँ",
      photoTooLarge: "फोटो 5 MB या उससे छोटी होनी चाहिए।",
      photoType: "JPG या PNG फोटो चुनें।",
      required: "यह जानकारी आवश्यक है।",
      ageError: "0 से 120 के बीच आयु लिखें।",
      phoneError: "10 अंकों का सही भारतीय मोबाइल नंबर लिखें।",
      future: "तारीख और समय भविष्य का नहीं हो सकता।",
      submitError: "रिपोर्ट भेजी नहीं जा सकी। कृपया फिर से प्रयास करें।",
      trackError: "इस केस आईडी और मोबाइल नंबर से कोई केस नहीं मिला।",
      nameMissing: "लापता व्यक्ति",
      reporterMobile: "रिपोर्टर का मोबाइल",
      saved: "डेमो मोड: यह रिपोर्ट केवल इस ब्राउज़र में सहेजी गई है।",
      demoSent:
        "डेमो मोड: खोया-पाया केंद्र या नियंत्रण कक्ष को सूचना नहीं भेजी गई।",
      discardConfirm: "क्या इस रिपोर्ट में भरी जानकारी हटाकर रद्द करें?",
      relationFamily: "परिवार का सदस्य",
      relationFriend: "मित्र",
      relationGuardian: "अभिभावक",
      photoUploaded: "संलग्न",
      underSearch: "खोज जारी",
      found: "मिल गया",
      reunited: "मिलन हुआ",
    },
    bn: {
      title: "নিখোঁজ ব্যক্তির রিপোর্ট",
      danger: "ব্যক্তি তাৎক্ষণিক বিপদে থাকলে SOS ব্যবহার করুন।",
      subtitle: "অনুসন্ধানে সাহায্যের জন্য সঠিক তথ্য দিন।",
      trackLink: "কেসের অবস্থা দেখুন",
      missing: "নিখোঁজ ব্যক্তির বিবরণ",
      fullName: "পুরো নাম",
      age: "বয়স",
      gender: "লিঙ্গ",
      choose: "বেছে নিন",
      male: "পুরুষ",
      female: "মহিলা",
      other: "অন্যান্য",
      photo: "ছবি (ঐচ্ছিক, প্রস্তাবিত)",
      photoHelp: "JPG বা PNG · সর্বোচ্চ 5 MB",
      description: "শারীরিক বিবরণ",
      height: "উচ্চতা",
      clothes: "পোশাক",
      marks: "চেনার চিহ্ন",
      languages: "কথ্য ভাষা (ঐচ্ছিক)",
      medical: "চিকিৎসার অবস্থা / বিশেষ প্রয়োজন (ঐচ্ছিক)",
      lastSeen: "শেষ দেখা যাওয়ার বিবরণ",
      location: "শেষ দেখা স্থান / ঘাট",
      notes: "অতিরিক্ত তথ্য (ঐচ্ছিক)",
      count: "{n}/500",
      date: "শেষ দেখা তারিখ ও সময়",
      reporter: "রিপোর্টকারীর বিবরণ",
      reporterName: "রিপোর্টকারীর নাম",
      phone: "মোবাইল নম্বর",
      relation: "নিখোঁজ ব্যক্তির সঙ্গে সম্পর্ক",
      alternate: "বিকল্প যোগাযোগ নম্বর (ঐচ্ছিক)",
      currentLocation: "বর্তমান অবস্থান / শিবির (ঐচ্ছিক)",
      submit: "রিপোর্ট জমা দিন",
      reset: "রিসেট / বাতিল",
      trackTitle: "কেসের অবস্থা দেখুন",
      caseId: "কেস আইডি",
      track: "অবস্থা দেখুন",
      backReport: "নিখোঁজ ব্যক্তির রিপোর্ট করুন",
      sent: "কেসটি নিকটতম হারানো-পাওয়া কেন্দ্র এবং নিয়ন্ত্রণ কক্ষে পাঠানো হয়েছে।",
      caseStatus: "অবস্থা",
      reported: "রিপোর্ট করা হয়েছে",
      details: "রিপোর্টের বিবরণ",
      reportAnother: "অন্য ব্যক্তির রিপোর্ট করুন",
      nearest:
        "নিকটতম হারানো-পাওয়া কেন্দ্র এবং নিয়ন্ত্রণ কক্ষকে জানানো হয়েছে।",
      removePhoto: "ছবি সরান",
      photoTooLarge: "ছবির আকার 5 MB বা কম হতে হবে।",
      photoType: "JPG বা PNG ছবি বেছে নিন।",
      required: "এই তথ্যটি আবশ্যক।",
      ageError: "0 থেকে 120-এর মধ্যে বয়স দিন।",
      phoneError: "10 সংখ্যার বৈধ ভারতীয় মোবাইল নম্বর দিন।",
      future: "তারিখ ও সময় ভবিষ্যতের হতে পারে না।",
      submitError: "রিপোর্ট জমা দেওয়া যায়নি। আবার চেষ্টা করুন।",
      trackError: "এই কেস আইডি ও মোবাইল নম্বরে কোনো কেস পাওয়া যায়নি।",
      nameMissing: "নিখোঁজ ব্যক্তি",
      reporterMobile: "রিপোর্টকারীর মোবাইল",
      saved: "ডেমো মোড: রিপোর্টটি শুধু এই ব্রাউজারে সংরক্ষিত।",
      demoSent:
        "ডেমো মোড: হারানো-পাওয়া কেন্দ্র বা নিয়ন্ত্রণ কক্ষে জানানো হয়নি।",
      discardConfirm: "এই রিপোর্টে দেওয়া তথ্য মুছে বাতিল করবেন?",
      relationFamily: "পরিবারের সদস্য",
      relationFriend: "বন্ধু",
      relationGuardian: "অভিভাবক",
      photoUploaded: "সংযুক্ত",
      underSearch: "অনুসন্ধান চলছে",
      found: "পাওয়া গেছে",
      reunited: "পুনর্মিলিত",
    },
  };

  const lpT = (key, vars) => {
    let value =
      (LOST_TEXT[window.I18N.lang] || LOST_TEXT.en)[key] ||
      LOST_TEXT.en[key] ||
      key;
    if (vars)
      Object.keys(vars).forEach((name) => {
        value = value.replace("{" + name + "}", vars[name]);
      });
    return value;
  };

  function openLostReport() {
    navigateLost("report");
  }

  function navigateLost(route, replace) {
    const hash = "#/lost/" + route;
    if (location.hash !== hash)
      history[replace ? "replaceState" : "pushState"](
        {},
        "",
        location.pathname + location.search + hash,
      );
    renderLostRoute(route);
  }

  function renderLostRoute(route) {
    state.lostRoute = route;
    switchScreen("lost");
    document.body.classList.add("lost-mode");
    if (route === "confirmation") {
      state.lostCase =
        state.lostCase ||
        JSON.parse(sessionStorage.getItem("kumbh.lastLostCase") || "null");
      if (state.lostCase) renderLostConfirmation();
      else navigateLost("report", true);
    } else if (route === "track") renderLostTrack();
    else renderLostForm();
  }

  function lostField(id, label, type, options) {
    const opts = options || {};
    const required = opts.required ? 'required aria-required="true"' : "";
    const control =
      type === "textarea"
        ? `<textarea id="${id}" name="${id}" ${required} ${opts.max ? `maxlength="${opts.max}"` : ""} ${opts.rows ? `rows="${opts.rows}"` : ""}></textarea>`
        : type === "select"
          ? `<select id="${id}" name="${id}" ${required}>${opts.choices || ""}</select>`
          : `<input id="${id}" name="${id}" type="${type}" ${required} ${opts.attrs || ""}/>`;
    return `<div class="lp-field"><label for="${id}">${esc(label)}${opts.required ? ' <span aria-hidden="true">*</span>' : ""}</label>${control}<small class="lp-error" id="${id}Error" aria-live="polite"></small></div>`;
  }

  function renderLostForm() {
    state.lostPhoto = null;
    const gender = `<option value="">${esc(lpT("choose"))}</option><option value="male">${esc(lpT("male"))}</option><option value="female">${esc(lpT("female"))}</option><option value="other">${esc(lpT("other"))}</option>`;
    $("#lostPage").innerHTML = `
      <button type="button" class="btn btn-primary btn-xl reports-entry" data-open-reports>${esc(reportT("viewAll"))}</button>
      <div class="lp-header"><h1>${esc(lpT("title"))}</h1><p>${esc(lpT("subtitle"))}</p></div>
      <div class="lp-danger" role="note"><svg class="ico"><use href="#i-sos"/></svg><strong>${esc(lpT("danger"))}</strong></div>
      <button type="button" class="lp-link" id="lostOpenTrack">${esc(lpT("trackLink"))} →</button>
      <form id="lostForm" novalidate>
        <fieldset class="lp-section"><legend>${esc(lpT("missing"))}</legend>
          ${lostField("lpName", lpT("fullName"), "text", { required: true, attrs: 'maxlength="120" autocomplete="name"' })}
          ${lostField("lpAge", lpT("age"), "number", { required: true, attrs: 'min="0" max="120" inputmode="numeric"' })}
          ${lostField("lpGender", lpT("gender"), "select", { required: true, choices: gender })}
          <div class="lp-field"><label for="lpPhoto">${esc(lpT("photo"))}</label><input id="lpPhoto" type="file" accept="image/jpeg,image/png,.jpg,.jpeg,.png"/><small class="lp-hint">${esc(lpT("photoHelp"))}</small><div id="lpPhotoPreview"></div><small class="lp-error" id="lpPhotoError" aria-live="polite"></small></div>
          <div class="lp-field"><label>${esc(lpT("description"))} <span aria-hidden="true">*</span></label><div class="lp-grid2">${lostField("lpHeight", lpT("height"), "text", { required: true, attrs: 'maxlength="80"' })}${lostField("lpClothes", lpT("clothes"), "text", { required: true, attrs: 'maxlength="200"' })}${lostField("lpMarks", lpT("marks"), "text", { required: true, attrs: 'maxlength="200"' })}</div></div>
          ${lostField("lpLanguages", lpT("languages"), "text", { attrs: 'maxlength="240"' })}
          ${lostField("lpMedical", lpT("medical"), "textarea", { max: 500, rows: 2 })}
        </fieldset>
        <fieldset class="lp-section"><legend>${esc(lpT("lastSeen"))}</legend>
          <div class="lp-field"><label for="lpPlace">${esc(lpT("location"))} <span aria-hidden="true">*</span></label><input id="lpPlace" name="lpPlace" list="lpLocations" required maxlength="160" autocomplete="off"/><datalist id="lpLocations">${state.lostLocations.map((f) => `<option value="${esc(f.name)}"></option>`).join("")}</datalist><small class="lp-error" id="lpPlaceError" aria-live="polite"></small></div>
          ${lostField("lpSeenAt", lpT("date"), "datetime-local", { required: true })}
          ${lostField("lpNotes", lpT("notes"), "textarea", { max: 500, rows: 3 })}<div class="lp-count" id="lpNotesCount">${lpT("count", { n: 0 })}</div>
        </fieldset>
        <fieldset class="lp-section"><legend>${esc(lpT("reporter"))}</legend>
          ${lostField("lpReporter", lpT("reporterName"), "text", { required: true, attrs: 'maxlength="120" autocomplete="name"' })}
          ${lostField("lpPhone", lpT("phone"), "tel", { required: true, attrs: 'inputmode="numeric" maxlength="10" autocomplete="tel-national"' })}
          ${lostField("lpRelation", lpT("relation"), "select", { required: true, choices: `<option value="">${esc(lpT("choose"))}</option>${[lpT("relationFamily"), lpT("relationFriend"), lpT("relationGuardian"), lpT("other")].map((v) => `<option>${esc(v)}</option>`).join("")}` })}
          ${lostField("lpAlternate", lpT("alternate"), "tel", { attrs: 'inputmode="numeric" maxlength="10" autocomplete="tel-national"' })}
          ${lostField("lpCurrentLocation", lpT("currentLocation"), "text", { attrs: 'maxlength="160"' })}
        </fieldset>
        <div class="lp-actions"><button type="submit" class="btn btn-primary btn-xl" id="lostSubmit">${esc(lpT("submit"))}</button><button type="button" class="btn btn-ghost btn-xl" id="lostReset">${esc(lpT("reset"))}</button></div>
        <div id="lostFormMessage" class="lp-form-message" role="status"></div>
      </form>`;

    const form = $("#lostForm");
    $("[data-open-reports]").addEventListener("click", navigateReports);
    form.addEventListener("submit", submitLostReport);
    $("#lostOpenTrack").addEventListener("click", () => navigateLost("track"));
    $("#lostReset").addEventListener("click", cancelLostForm);
    $("#lpNotes").addEventListener("input", (event) => {
      $("#lpNotesCount").textContent = lpT("count", {
        n: event.target.value.length,
      });
    });
    $("#lpPhoto").addEventListener("change", onLostPhotoSelected);
    const now = new Date();
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    $("#lpSeenAt").max = localNow;
    $("#lostForm").addEventListener("input", clearLostFieldError);
    $("#lostForm").addEventListener("change", clearLostFieldError);
    API.lostLocations()
      .then((rows) => {
        state.lostLocations = rows;
        const list = document.getElementById("lpLocations");
        if (list && state.lostRoute === "report")
          list.innerHTML = rows
            .map((f) => `<option value="${esc(f.name)}"></option>`)
            .join("");
      })
      .catch(() => {});
  }

  function clearLostFieldError(event) {
    if (!event.target.id) return;
    const error = document.getElementById(event.target.id + "Error");
    if (error) error.textContent = "";
  }

  function onLostPhotoSelected(event) {
    const file = event.target.files && event.target.files[0];
    const error = $("#lpPhotoError");
    error.textContent = "";
    if (!file) return;
    if (!/^image\/(jpeg|png)$/.test(file.type)) {
      error.textContent = lpT("photoType");
      event.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      error.textContent = lpT("photoTooLarge");
      event.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      state.lostPhoto = reader.result;
      $("#lpPhotoPreview").innerHTML =
        `<div class="lp-photo"><img src="${state.lostPhoto}" alt="${esc(lpT("photo"))}"/><button type="button" class="btn btn-ghost" id="lpPhotoRemove">${esc(lpT("removePhoto"))}</button></div>`;
      $("#lpPhotoRemove").addEventListener("click", () => {
        state.lostPhoto = null;
        $("#lpPhoto").value = "";
        $("#lpPhotoPreview").innerHTML = "";
      });
    };
    reader.readAsDataURL(file);
  }

  function validateLostForm() {
    const value = (id) => $("#" + id).value.trim();
    let valid = true;
    const error = (id, message) => {
      $("#" + id + "Error").textContent = message;
      valid = false;
    };
    [
      "lpName",
      "lpAge",
      "lpGender",
      "lpHeight",
      "lpClothes",
      "lpMarks",
      "lpPlace",
      "lpSeenAt",
      "lpReporter",
      "lpPhone",
      "lpRelation",
    ].forEach((id) => {
      if (!value(id)) error(id, lpT("required"));
    });
    if (
      value("lpAge") &&
      (!/^\d+$/.test(value("lpAge")) || Number(value("lpAge")) > 120)
    )
      error("lpAge", lpT("ageError"));
    const indianPhone = /^[6-9]\d{9}$/;
    if (value("lpPhone") && !indianPhone.test(value("lpPhone")))
      error("lpPhone", lpT("phoneError"));
    if (value("lpAlternate") && !indianPhone.test(value("lpAlternate")))
      error("lpAlternate", lpT("phoneError"));
    if (value("lpSeenAt") && new Date(value("lpSeenAt")).getTime() > Date.now())
      error("lpSeenAt", lpT("future"));
    if (value("lpNotes").length > 500) error("lpNotes", lpT("required"));
    const photo = $("#lpPhoto").files[0];
    if (
      photo &&
      (photo.size > 5 * 1024 * 1024 || !/^image\/(jpeg|png)$/.test(photo.type))
    )
      error(
        "lpPhoto",
        photo.size > 5 * 1024 * 1024 ? lpT("photoTooLarge") : lpT("photoType"),
      );
    return valid;
  }

  async function submitLostReport(event) {
    event.preventDefault();
    if (state.lostSubmitting || !validateLostForm()) return;
    const val = (id) => $("#" + id).value.trim();
    const selectedPlace = state.lostLocations.find(
      (facility) => facility.name === val("lpPlace"),
    );
    const payload = {
      subject_name: val("lpName"),
      subject_age: Number(val("lpAge")),
      subject_gender: val("lpGender"),
      description: [
        `Height: ${val("lpHeight")}; Clothes: ${val("lpClothes")}; Identification marks: ${val("lpMarks")}`,
        val("lpNotes") ? `Additional notes: ${val("lpNotes")}` : "",
      ]
        .filter(Boolean)
        .join("; "),
      photo_ref: state.lostPhoto,
      last_seen_place: val("lpPlace"),
      last_seen_at: new Date(val("lpSeenAt")).toISOString(),
      last_seen_lat: selectedPlace ? selectedPlace.lat : null,
      last_seen_lon: selectedPlace ? selectedPlace.lon : null,
      languages_spoken: val("lpLanguages") || null,
      medical_needs: val("lpMedical") || null,
      reporter_name: val("lpReporter"),
      reporter_phone: val("lpPhone"),
      reporter_relation: val("lpRelation"),
      alternate_phone: val("lpAlternate") || null,
      reporter_location: val("lpCurrentLocation") || null,
      is_child: Number(val("lpAge")) < 18,
    };
    state.lostSubmitting = true;
    const button = $("#lostSubmit");
    button.disabled = true;
    button.textContent = lpT("submit") + "…";
    $("#lostFormMessage").textContent = "";
    try {
      const result = await API.createLostPerson(payload);
      const caseStatuses = {
        open: lpT("reported"),
        sighting: lpT("underSearch"),
        matched: lpT("found"),
        reunited: lpT("reunited"),
      };
      const confirmationPayload = Object.assign({}, payload, {
        photo_ref: null,
      });
      state.lostCase = {
        case_no: result.case_no,
        status: caseStatuses[result.status] || result.status || lpT("reported"),
        payload: confirmationPayload,
        photoAttached: Boolean(payload.photo_ref),
        demo: API.mode !== "live",
      };
      sessionStorage.setItem(
        "kumbh.lastLostCase",
        JSON.stringify(state.lostCase),
      );
      navigateLost("confirmation", true);
    } catch (err) {
      $("#lostFormMessage").textContent = lpT("submitError");
    } finally {
      state.lostSubmitting = false;
      if (document.getElementById("lostSubmit")) {
        button.disabled = false;
        button.textContent = lpT("submit");
      }
    }
  }

  function cancelLostForm() {
    const entered =
      [...$("#lostForm").elements].some(
        (field) => field.type !== "file" && field.value,
      ) || state.lostPhoto;
    if (entered && !window.confirm(lpT("discardConfirm"))) return;
    state.lostPhoto = null;
    switchScreen("home");
  }

  function renderLostConfirmation() {
    const item = state.lostCase;
    const p = item.payload;
    const details = [
      [lpT("nameMissing"), p.subject_name],
      [lpT("age"), p.subject_age],
      [lpT("gender"), lpT(p.subject_gender)],
      [lpT("location"), p.last_seen_place],
      [lpT("date"), new Date(p.last_seen_at).toLocaleString()],
      [lpT("photo"), item.photoAttached ? lpT("photoUploaded") : "—"],
      [lpT("description"), p.description],
      [lpT("languages"), p.languages_spoken || "—"],
      [lpT("medical"), p.medical_needs || "—"],
      [
        lpT("notes"),
        p.description.includes("Additional notes:")
          ? p.description
              .split("Additional notes:")
              .slice(1)
              .join("Additional notes:")
              .trim()
          : "—",
      ],
      [lpT("reporterName"), p.reporter_name],
      [lpT("reporterMobile"), p.reporter_phone],
      [lpT("relation"), p.reporter_relation],
      [lpT("alternate"), p.alternate_phone || "—"],
      [lpT("currentLocation"), p.reporter_location || "—"],
      [lpT("caseStatus"), item.status],
    ];
    $("#lostPage").innerHTML =
      `<div class="lp-header"><h1>${esc(lpT("title"))}</h1></div><article class="lp-confirm card"><div class="lp-success">✓</div><h2>${esc(lpT("reported"))}</h2><p>${esc(item.demo ? lpT("demoSent") : lpT("sent"))}</p><div class="lp-case-id"><span>${esc(lpT("caseId"))}</span><strong>${esc(item.case_no)}</strong></div><p class="lp-demo-note" ${item.demo ? "" : "hidden"}>${esc(lpT("saved"))}</p><h3>${esc(lpT("details"))}</h3><dl>${details.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl><div class="lp-actions"><button class="btn btn-primary btn-xl" id="lostTrackFromConfirm">${esc(lpT("trackLink"))}</button><button type="button" class="btn btn-ghost btn-xl" data-open-reports>${esc(reportT("viewAll"))}</button><button class="btn btn-ghost btn-xl" id="lostAnother">${esc(lpT("reportAnother"))}</button><button class="btn btn-plain btn-xl" id="lostHome">${esc(t("nav.home"))}</button></div></article>`;
    $("#lostTrackFromConfirm").addEventListener("click", () =>
      navigateLost("track"),
    );
    $("[data-open-reports]").addEventListener("click", navigateReports);
    $("#lostAnother").addEventListener("click", () => navigateLost("report"));
    $("#lostHome").addEventListener("click", () => switchScreen("home"));
  }

  function renderLostTrack() {
    $("#lostPage").innerHTML =
      `<div class="lp-header"><h1>${esc(lpT("trackTitle"))}</h1></div><button type="button" class="btn btn-primary btn-xl reports-entry" data-open-reports>${esc(reportT("viewAll"))}</button><div class="lp-danger" role="note"><svg class="ico"><use href="#i-sos"/></svg><strong>${esc(lpT("danger"))}</strong></div><button type="button" class="lp-link" id="lostBackReport">← ${esc(lpT("backReport"))}</button><form id="lostTrackForm" class="lp-section" novalidate>${lostField("lpTrackId", lpT("caseId"), "text", { required: true, attrs: 'maxlength="24" autocapitalize="characters"' })}${lostField("lpTrackPhone", lpT("phone"), "tel", { required: true, attrs: 'inputmode="numeric" maxlength="10" autocomplete="tel-national"' })}<button class="btn btn-primary btn-xl" id="lostTrackSubmit">${esc(lpT("track"))}</button><div id="lostTrackMessage" class="lp-form-message" role="status"></div><div id="lostTrackResult"></div></form>`;
    $("[data-open-reports]").addEventListener("click", navigateReports);
    $("#lostBackReport").addEventListener("click", () =>
      navigateLost("report"),
    );
    $("#lostTrackForm").addEventListener("submit", submitLostTrack);
  }

  async function submitLostTrack(event) {
    event.preventDefault();
    const caseNo = $("#lpTrackId").value.trim().toUpperCase();
    const phone = $("#lpTrackPhone").value.trim();
    $("#lpTrackIdError").textContent = caseNo ? "" : lpT("required");
    $("#lpTrackPhoneError").textContent = /^[6-9]\d{9}$/.test(phone)
      ? ""
      : lpT("phoneError");
    if (!caseNo || !/^[6-9]\d{9}$/.test(phone)) return;
    const button = $("#lostTrackSubmit");
    button.disabled = true;
    $("#lostTrackMessage").textContent = "";
    try {
      const item = await API.trackLostPerson(caseNo, phone);
      const translatedStatus =
        {
          Reported: lpT("reported"),
          "Under Search": lpT("underSearch"),
          Found: lpT("found"),
          Reunited: lpT("reunited"),
        }[item.status] || item.status;
      $("#lostTrackResult").innerHTML =
        `<article class="lp-track-result"><h2>${esc(item.case_no)}</h2><dl><div><dt>${esc(lpT("nameMissing"))}</dt><dd>${esc(item.subject_name)}</dd></div><div><dt>${esc(lpT("caseStatus"))}</dt><dd><strong>${esc(translatedStatus)}</strong></dd></div><div><dt>${esc(lpT("location"))}</dt><dd>${esc(item.last_seen_place || "—")}</dd></div></dl></article>`;
    } catch (err) {
      $("#lostTrackMessage").textContent = lpT("trackError");
    } finally {
      button.disabled = false;
    }
  }

  /* --------------------------------------------------------------- actions */
  function switchScreen(name) {
    state.screen = name;
    if (name !== "lost") document.body.classList.remove("lost-mode");
    if (name !== "transport") document.body.classList.remove("transport-mode");
    if (name !== "stay") document.body.classList.remove("stay-mode");
    if (
      name !== "lost" &&
      name !== "reports" &&
      location.hash.startsWith("#/lost/")
    ) {
      history.replaceState({}, "", location.pathname + location.search);
    }
    if (name !== "transport" && location.hash === "#/transport") {
      history.replaceState({}, "", location.pathname + location.search);
    }
    if (name !== "stay" && location.hash === "#/stay") {
      history.replaceState({}, "", location.pathname + location.search);
    }
    document.querySelectorAll(".screen").forEach((section) => {
      section.classList.toggle("is-active", section.id === "screen-" + name);
    });
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.screen === name);
    });
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function handleLostHash() {
    if (location.hash === "#/stay") {
      renderStay();
      return;
    }
    if (location.hash === "#/transport") {
      renderTransport();
      return;
    }
    if (location.hash === "#/lost/reports") {
      renderReports();
      return;
    }
    const match = location.hash.match(/^#\/lost\/(report|confirmation|track)$/);
    if (match) renderLostRoute(match[1]);
    else if (
      state.screen === "lost" ||
      state.screen === "transport" ||
      state.screen === "stay"
    )
      switchScreen("home");
  }

  const REPORT_TEXT = {
    en: {
      title: "Lost Person Reports",
      viewAll: "View All Missing Persons Reports",
      login: "Staff sign in",
      code: "Employee code",
      phone: "Registered phone",
      totp: "Authenticator code (if enabled)",
      signIn: "Sign in",
      loginError: "Staff sign-in failed. Check your details and try again.",
      unavailable:
        "Reports require a live backend. Please try again when the service is available.",
      denied: "This account cannot view lost person reports.",
      search: "Search by name or Case ID",
      status: "Status",
      all: "All statuses",
      from: "From",
      to: "To",
      apply: "Search",
      loading: "Loading reports…",
      error: "Could not load reports. Please try again.",
      empty: "No reports found",
      case: "Case ID",
      name: "Name",
      age: "Age",
      gender: "Gender",
      place: "Last seen location",
      seen: "Last seen date/time",
      reporter: "Reporter name",
      mobile: "Reporter mobile",
      reported: "Reported on",
      details: "Report details",
      photo: "Photo",
      save: "Save status",
      saved: "Status updated successfully.",
      saveError: "Could not update status. Please try again.",
      previous: "Previous",
      next: "Next",
      of: "of",
      relation: "Reporter relationship",
      alternate: "Alternate phone",
      reporterLocation: "Reporter location",
      description: "Description",
      languages: "Languages spoken",
      medical: "Medical needs",
      coordinates: "Last seen coordinates",
      statusBy: "Last changed by",
      statusAt: "Last changed at",
      reportedStatus: "Reported",
      underSearch: "Under Search",
      found: "Found",
      reunited: "Reunited",
      logout: "Sign out",
    },
    hi: {
      title: "लापता व्यक्ति की रिपोर्ट",
      viewAll: "सभी लापता व्यक्तियों की रिपोर्ट देखें",
      login: "कर्मचारी लॉगिन",
      code: "कर्मचारी कोड",
      phone: "पंजीकृत फ़ोन",
      totp: "Authenticator कोड (यदि चालू हो)",
      signIn: "लॉगिन",
      loginError: "लॉगिन विफल। विवरण जाँचकर फिर प्रयास करें।",
      unavailable:
        "रिपोर्ट देखने के लिए लाइव सर्वर आवश्यक है। सेवा उपलब्ध होने पर फिर प्रयास करें।",
      denied: "इस खाते को रिपोर्ट देखने की अनुमति नहीं है।",
      search: "नाम या केस आईडी से खोजें",
      status: "स्थिति",
      all: "सभी स्थितियाँ",
      from: "से तारीख",
      to: "तक तारीख",
      apply: "खोजें",
      loading: "रिपोर्ट लोड हो रही हैं…",
      error: "रिपोर्ट लोड नहीं हुईं। फिर प्रयास करें।",
      empty: "कोई रिपोर्ट नहीं मिली",
      case: "केस आईडी",
      name: "नाम",
      age: "उम्र",
      gender: "लिंग",
      place: "आखिरी बार देखे जाने का स्थान",
      seen: "आखिरी बार देखे जाने की तारीख/समय",
      reporter: "रिपोर्टर का नाम",
      mobile: "रिपोर्टर मोबाइल",
      reported: "रिपोर्ट की तारीख",
      details: "रिपोर्ट विवरण",
      photo: "फ़ोटो",
      save: "स्थिति सहेजें",
      saved: "स्थिति अपडेट हो गई।",
      saveError: "स्थिति अपडेट नहीं हुई। फिर प्रयास करें।",
      previous: "पिछला",
      next: "अगला",
      of: "में से",
      relation: "रिपोर्टर से संबंध",
      alternate: "वैकल्पिक फ़ोन",
      reporterLocation: "रिपोर्टर का स्थान",
      description: "विवरण",
      languages: "बोली जाने वाली भाषाएँ",
      medical: "चिकित्सीय ज़रूरतें",
      coordinates: "आखिरी स्थान के निर्देशांक",
      statusBy: "अंतिम बदलावकर्ता",
      statusAt: "अंतिम बदलाव का समय",
      reportedStatus: "रिपोर्ट किया गया",
      underSearch: "खोज जारी",
      found: "मिल गया",
      reunited: "मिलन हुआ",
      logout: "लॉगआउट",
    },
    bn: {
      title: "নিখোঁজ ব্যক্তির রিপোর্ট",
      viewAll: "সব নিখোঁজ ব্যক্তির রিপোর্ট দেখুন",
      login: "কর্মী লগইন",
      code: "কর্মী কোড",
      phone: "নিবন্ধিত ফোন",
      totp: "Authenticator কোড (চালু থাকলে)",
      signIn: "লগইন",
      loginError: "লগইন ব্যর্থ। তথ্য যাচাই করে আবার চেষ্টা করুন।",
      unavailable:
        "রিপোর্ট দেখতে লাইভ সার্ভার দরকার। পরিষেবা চালু হলে আবার চেষ্টা করুন।",
      denied: "এই অ্যাকাউন্টের রিপোর্ট দেখার অনুমতি নেই।",
      search: "নাম বা কেস আইডি দিয়ে খুঁজুন",
      status: "অবস্থা",
      all: "সব অবস্থা",
      from: "শুরুর তারিখ",
      to: "শেষ তারিখ",
      apply: "খুঁজুন",
      loading: "রিপোর্ট লোড হচ্ছে…",
      error: "রিপোর্ট লোড করা যায়নি। আবার চেষ্টা করুন।",
      empty: "কোনো রিপোর্ট পাওয়া যায়নি",
      case: "কেস আইডি",
      name: "নাম",
      age: "বয়স",
      gender: "লিঙ্গ",
      place: "শেষ দেখা স্থান",
      seen: "শেষ দেখা তারিখ/সময়",
      reporter: "রিপোর্টারের নাম",
      mobile: "রিপোর্টারের মোবাইল",
      reported: "রিপোর্টের তারিখ",
      details: "রিপোর্টের বিবরণ",
      photo: "ছবি",
      save: "অবস্থা সংরক্ষণ",
      saved: "অবস্থা আপডেট হয়েছে।",
      saveError: "অবস্থা আপডেট করা যায়নি। আবার চেষ্টা করুন।",
      previous: "আগের",
      next: "পরের",
      of: "এর",
      relation: "রিপোর্টারের সম্পর্ক",
      alternate: "বিকল্প ফোন",
      reporterLocation: "রিপোর্টারের অবস্থান",
      description: "বিবরণ",
      languages: "কথিত ভাষা",
      medical: "চিকিৎসার প্রয়োজন",
      coordinates: "শেষ দেখা স্থানাঙ্ক",
      statusBy: "শেষ পরিবর্তনকারী",
      statusAt: "শেষ পরিবর্তনের সময়",
      reportedStatus: "রিপোর্ট করা হয়েছে",
      underSearch: "খোঁজ চলছে",
      found: "পাওয়া গেছে",
      reunited: "পুনর্মিলিত",
      logout: "লগআউট",
    },
  };
  const reportT = (key) =>
    (REPORT_TEXT[window.I18N.lang] || REPORT_TEXT.en)[key] ||
    REPORT_TEXT.en[key] ||
    key;
  let reportPage = 1,
    reportTotal = 0,
    reportSelected = null,
    reportFilters = {};

  function navigateReports() {
    const hash = "#/lost/reports";
    if (location.hash !== hash)
      history.pushState({}, "", location.pathname + location.search + hash);
    renderReports();
  }

  function reportStatus(value) {
    return (
      {
        open: reportT("reportedStatus"),
        sighting: reportT("underSearch"),
        matched: reportT("found"),
        reunited: reportT("reunited"),
        closed: reportT("reunited"),
      }[value] || value
    );
  }
  function renderReports() {
    switchScreen("reports");
    const page = document.getElementById("reportsPage");
    if (API.mode !== "live") {
      page.innerHTML = `<h1>${esc(reportT("title"))}</h1><p class="report-message error">${esc(reportT("unavailable"))}</p>`;
      return;
    }
    page.innerHTML = `<div class="reports-head"><h1>${esc(reportT("title"))}</h1></div><form id="reportFilters" class="report-filters"><input name="search" placeholder="${esc(reportT("search"))}" value="${esc(reportFilters.search || "")}"/><select name="status" aria-label="${esc(reportT("status"))}"><option value="">${esc(reportT("all"))}</option>${[
      ["Reported", "reportedStatus"],
      ["Under Search", "underSearch"],
      ["Found", "found"],
      ["Reunited", "reunited"],
    ]
      .map(
        ([value, key]) =>
          `<option value="${value}" ${reportFilters.status === value ? "selected" : ""}>${esc(reportT(key))}</option>`,
      )
      .join(
        "",
      )}</select><button class="btn btn-primary">${esc(reportT("apply"))}</button></form><div id="reportsContent" aria-live="polite"></div>`;
    document
      .getElementById("reportFilters")
      .addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        reportFilters = Object.fromEntries(data.entries());
        reportPage = 1;
        loadReports();
      });
    if (reportSelected) loadReportDetail(reportSelected);
    else loadReports();
  }

  async function loadReports() {
    const content = document.getElementById("reportsContent");
    if (!content) return;
    content.innerHTML = `<p class="report-message loading-state">${esc(reportT("loading"))}</p>`;
    const params = Object.assign({}, reportFilters, {
      page: reportPage,
      page_size: 20,
    });
    Object.keys(params).forEach((key) => {
      if (!params[key]) delete params[key];
    });
    try {
      const result = await API.lostReports(params);
      reportTotal = result.total;
      if (!result.items.length) {
        content.innerHTML = `<p class="report-empty">${esc(reportT("empty"))}</p>`;
        return;
      }
      const cols = [
        reportT("case"),
        reportT("name"),
        reportT("age"),
        reportT("gender"),
        reportT("place"),
        reportT("seen"),
        reportT("status"),
        reportT("reported"),
      ];
      content.innerHTML = `<div class="report-table-wrap"><table class="report-table"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${result.items.map((r) => `<tr tabindex="0" data-case="${esc(r.id)}"><td data-label="${esc(cols[0])}">${esc(r.case_no)}</td><td data-label="${esc(cols[1])}">${esc(r.subject_name)}</td><td data-label="${esc(cols[2])}">${esc(r.subject_age == null ? "—" : r.subject_age)}</td><td data-label="${esc(cols[3])}">${esc(r.subject_gender || "—")}</td><td data-label="${esc(cols[4])}">${esc(r.last_seen_place || "—")}</td><td data-label="${esc(cols[5])}">${esc(formatReportDate(r.last_seen_at))}</td><td data-label="${esc(cols[6])}"><span class="status-badge status-${esc(r.status)}">${esc(reportStatus(r.status))}</span></td><td data-label="${esc(cols[7])}">${esc(formatReportDate(r.created_at))}</td></tr>`).join("")}</tbody></table></div><div class="report-pagination"><button class="btn btn-ghost" id="reportPrev" ${reportPage <= 1 ? "disabled" : ""}>${esc(reportT("previous"))}</button><span>${reportPage} ${esc(reportT("of"))} ${Math.max(1, Math.ceil(reportTotal / 20))}</span><button class="btn btn-ghost" id="reportNext" ${reportPage * 20 >= reportTotal ? "disabled" : ""}>${esc(reportT("next"))}</button></div>`;
      content.querySelectorAll("[data-case]").forEach((row) => {
        const open = () => {
          reportSelected = row.dataset.case;
          loadReportDetail(reportSelected);
        };
        row.addEventListener("click", open);
        row.addEventListener("keydown", (e) => {
          if (e.key === "Enter") open();
        });
      });
      document.getElementById("reportPrev").addEventListener("click", () => {
        reportPage--;
        loadReports();
      });
      document.getElementById("reportNext").addEventListener("click", () => {
        reportPage++;
        loadReports();
      });
    } catch (_) {
      content.innerHTML = `<p class="report-message error">${esc(reportT("error"))}</p>`;
    }
  }

  function formatReportDate(value) {
    return value
      ? new Date(value).toLocaleString(LOCALES[window.I18N.lang] || "en-IN")
      : "—";
  }
  async function loadReportDetail(id) {
    const content = document.getElementById("reportsContent");
    if (!content) return;
    content.innerHTML = `<p class="report-message loading-state">${esc(reportT("loading"))}</p>`;
    try {
      const r = await API.lostReport(id);
      const noted = (r.description || "").match(/Additional notes:\s*(.*)$/i);
      const notes = [
        noted && noted[1],
        ...(r.sightings || []).map((item) => item.note),
      ]
        .filter(Boolean)
        .join("\n");
      const fields = [
        ["case", r.case_no],
        ["name", r.subject_name],
        ["age", r.subject_age],
        ["gender", r.subject_gender],
        ["description", r.description],
        ["place", r.last_seen_place],
        ["seen", formatReportDate(r.last_seen_at)],
        [
          "coordinates",
          r.last_seen_lat == null
            ? null
            : `${r.last_seen_lat}, ${r.last_seen_lon}`,
        ],
        ["languages", r.languages_spoken],
        ["medical", r.medical_needs],
        ["notes", notes || "—"],
      ];
      content.innerHTML = `<button class="lp-link" id="reportBack">← ${esc(reportT("title"))}</button><article class="lp-section report-detail"><h2>${esc(r.case_no)} · ${esc(r.subject_name)}</h2><span class="status-badge status-${esc(r.status)}">${esc(reportStatus(r.status))}</span><dl>${fields.map(([key, value]) => `<div><dt>${esc(key === "notes" ? lpT("notes") : reportT(key))}</dt><dd>${esc(value == null || value === "" ? "—" : value)}</dd></div>`).join("")}</dl>${r.photo_ref ? `<h3>${esc(reportT("photo"))}</h3><img class="report-photo" src="${esc(r.photo_ref)}" alt="${esc(reportT("photo"))}"/>` : ""}</article>`;
      document.getElementById("reportBack").addEventListener("click", () => {
        reportSelected = null;
        loadReports();
      });
    } catch (_) {
      content.innerHTML = `<p class="report-message error">${esc(reportT("error"))}</p><button class="btn btn-ghost" id="reportBack">${esc(reportT("previous"))}</button>`;
      document.getElementById("reportBack").addEventListener("click", () => {
        reportSelected = null;
        loadReports();
      });
    }
  }

  function setCategory(category) {
    state.category = category;
    API.nearby(category).then((rows) => {
      state.nearby = rows;
      renderMap();
    });
  }

  function scrollTo(id) {
    const node = document.getElementById(id);
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function stub(labelKey, endpoint) {
    toast(t(labelKey) + " · " + endpoint);
  }

  let toastTimer = null;
  function toast(message) {
    const node = $("#toast");
    node.textContent = message;
    node.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("is-on"), 3200);
  }

  function timeAgo(iso) {
    const minutes = Math.max(
      0,
      Math.round((Date.now() - new Date(iso).getTime()) / 60000),
    );
    if (minutes < 1) return "now";
    if (minutes < 60) return minutes + "m";
    return Math.round(minutes / 60) + "h";
  }

  function shortTime(value) {
    if (!value) return "—";
    return String(value).slice(0, 5);
  }

  function toggleLargeText() {
    document.documentElement.classList.toggle("large-text");
    const on = document.documentElement.classList.contains("large-text");
    localStorage.setItem("kumbh.largeText", on ? "1" : "0");
    toast(t("help.text") + (on ? " ✓" : " ✕"));
  }

  /* ------------------------------------------------------------------ SOS */
  function openSos() {
    $("#sosBackdrop").hidden = false;
    $("#sosSheet").hidden = false;
    $("#sosCategories").innerHTML = SOS_CATEGORIES.map(
      (cat) => `
      <button class="sos-cat ${state.sosCategory === cat.key ? "is-active" : ""}" data-cat="${cat.key}">
        <svg class="ico"><use href="#${cat.icon}"/></svg>${esc(t("sos.cat." + cat.key))}
      </button>`,
    ).join("");
    $("#sosCategories")
      .querySelectorAll("[data-cat]")
      .forEach((btn) => {
        btn.addEventListener("click", () => {
          state.sosCategory = btn.dataset.cat;
          $("#sosCategories")
            .querySelectorAll("[data-cat]")
            .forEach((b) => {
              b.classList.toggle(
                "is-active",
                b.dataset.cat === state.sosCategory,
              );
            });
        });
      });
  }

  function closeSos() {
    $("#sosBackdrop").hidden = true;
    $("#sosSheet").hidden = true;
  }

  async function sendSos() {
    const silent = $("#sosSilent").checked;
    closeSos();
    await API.locate();
    try {
      const result = await API.raiseSos(state.sosCategory, silent);
      const reference = result.reference || "SOS";
      toast(t("sos.sent", { ref: reference }));
      if (API.mode !== "live") toast(t("sos.fallback"));
    } catch (err) {
      toast(t("sos.fallback"));
    }
  }

  /* ------------------------------------------------------------- language */
  function openLang() {
    $("#langBackdrop").hidden = false;
    $("#langSheet").hidden = false;
    $("#langGrid").innerHTML = window.I18N.languages
      .map(
        (code) => `
      <button class="lang-opt ${window.I18N.lang === code ? "is-active" : ""}" data-lang="${code}">
        ${esc(window.I18N.labels[code])}
      </button>`,
      )
      .join("");
    $("#langGrid")
      .querySelectorAll("[data-lang]")
      .forEach((btn) => {
        btn.addEventListener("click", () => setLanguage(btn.dataset.lang));
      });
  }

  function closeLang() {
    $("#langBackdrop").hidden = true;
    $("#langSheet").hidden = true;
  }

  function setLanguage(code) {
    window.I18N.lang = code;
    localStorage.setItem("kumbh.lang", code);
    closeLang();
    renderAll();
    API.home().then((data) => {
      state.data = data;
      renderHome();
      renderAlerts();
    });
    if (state.screen === "lost") {
      if (state.lostRoute === "report") {
        const values = {};
        const form = document.getElementById("lostForm");
        if (form)
          [...form.elements].forEach((field) => {
            if (field.id && field.type !== "file")
              values[field.id] = field.value;
          });
        const photo = state.lostPhoto;
        renderLostForm();
        Object.keys(values).forEach((id) => {
          const field = document.getElementById(id);
          if (field) field.value = values[id];
        });
        if (document.getElementById("lpNotesCount"))
          $("#lpNotesCount").textContent = lpT("count", {
            n: values.lpNotes ? values.lpNotes.length : 0,
          });
        if (photo) {
          state.lostPhoto = photo;
          $("#lpPhotoPreview").innerHTML =
            `<div class="lp-photo"><img src="${photo}" alt="${esc(lpT("photo"))}"/><button type="button" class="btn btn-ghost" id="lpPhotoRemove">${esc(lpT("removePhoto"))}</button></div>`;
          $("#lpPhotoRemove").addEventListener("click", () => {
            state.lostPhoto = null;
            $("#lpPhoto").value = "";
            $("#lpPhotoPreview").innerHTML = "";
          });
        }
      } else renderLostRoute(state.lostRoute);
    } else if (state.screen === "reports") renderReports();
    else if (state.screen === "transport") renderTransport();
    else if (state.screen === "stay") renderStay();
  }

  /* ---------------------------------------------------------- registration */
  function openRegister() {
    if (document.getElementById("regSheet")) return;
    const backdrop = document.createElement("div");
    backdrop.className = "sheet-backdrop";
    backdrop.id = "regBackdrop";
    const sheet = document.createElement("div");
    sheet.className = "sheet";
    sheet.id = "regSheet";
    sheet.innerHTML = `
      <div class="sheet-grip"></div>
      <h2>${esc(t("tile.register"))}</h2>
      <p class="sheet-sub">${esc(t("id.org"))}</p>
      <div id="regBody"></div>
      <button class="btn btn-plain btn-block" id="regClose">${esc(t("sos.cancel"))}</button>`;
    document.body.appendChild(backdrop);
    document.body.appendChild(sheet);
    backdrop.addEventListener("click", closeRegister);
    $("#regClose").addEventListener("click", closeRegister);
    regStepPhone();
  }

  function closeRegister() {
    const backdrop = document.getElementById("regBackdrop");
    const sheet = document.getElementById("regSheet");
    if (backdrop) backdrop.remove();
    if (sheet) sheet.remove();
  }

  function regStepPhone() {
    $("#regBody").innerHTML = `
      <label class="row-sub" for="regPhone">Mobile number</label>
      <input id="regPhone" inputmode="numeric" autocomplete="tel" placeholder="98765 43210"
        style="width:100%;padding:16px;font-size:1.1rem;border:1px solid #e3e0d8;border-radius:14px;margin:8px 0 12px;font-family:inherit" />
      <button class="btn btn-primary btn-block" id="regSend">${esc(t("id.sendOtp"))}</button>`;
    $("#regSend").addEventListener("click", async () => {
      const phone = ($("#regPhone").value || "").replace(/\D/g, "");
      if (phone.length < 10) {
        toast("10-digit mobile number");
        return;
      }
      if (API.mode === "live") {
        try {
          const res = await API.requestOtp(phone);
          regStepOtp(phone, res.request_id, res.dev_otp);
        } catch (err) {
          toast("OTP failed: " + err.message);
        }
      } else {
        regStepOtp(phone, "demo", "000000");
      }
    });
  }

  function regStepOtp(phone, requestId, devOtp) {
    $("#regBody").innerHTML = `
      <label class="row-sub" for="regOtp">OTP</label>
      <input id="regOtp" inputmode="numeric" value="${esc(devOtp || "")}"
        style="width:100%;padding:16px;font-size:1.3rem;letter-spacing:.4em;text-align:center;border:1px solid #e3e0d8;border-radius:14px;margin:8px 0 12px;font-family:inherit" />
      <button class="btn btn-primary btn-block" id="regVerify">${esc(t("id.register"))}</button>`;
    $("#regVerify").addEventListener("click", async () => {
      const otp = ($("#regOtp").value || "").trim();
      if (API.mode === "live") {
        try {
          await API.verifyOtp(requestId, phone, otp);
        } catch (err) {
          toast("OTP: " + err.message);
          return;
        }
      }
      regStepProfile(phone);
    });
  }

  function regStepProfile(phone) {
    $("#regBody").innerHTML = `
      <input id="regName" placeholder="${esc(t("id.nameField"))}"
        style="width:100%;padding:14px;border:1px solid #e3e0d8;border-radius:14px;margin-bottom:10px;font-family:inherit;font-size:1rem" />
      <input id="regAge" inputmode="numeric" placeholder="${esc(t("id.ageField"))}"
        style="width:100%;padding:14px;border:1px solid #e3e0d8;border-radius:14px;margin-bottom:10px;font-family:inherit;font-size:1rem" />
      <input id="regEmergency" inputmode="tel" placeholder="${esc(t("id.fact.emergency"))}"
        style="width:100%;padding:14px;border:1px solid #e3e0d8;border-radius:14px;margin-bottom:12px;font-family:inherit;font-size:1rem" />
      <button class="btn btn-primary btn-block" id="regDone">${esc(t("id.register"))}</button>`;
    $("#regDone").addEventListener("click", async () => {
      const name = ($("#regName").value || "").trim() || "Guest";
      const age = Number(($("#regAge").value || "").replace(/\D/g, "")) || null;
      const emergency = [
        ($("#regEmergency").value || "").replace(/\D/g, ""),
      ].filter(Boolean);

      if (API.mode === "live" && API.token) {
        try {
          await fetch("/v1/visitors", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: "Bearer " + API.token,
            },
            body: JSON.stringify({
              name: name,
              age: age,
              language: window.I18N.lang,
              emergency_contacts: emergency.map((number) => ({
                phone: number,
                name: "Emergency",
                relation: "family",
              })),
            }),
          });
          state.idCard = await API.idCard();
        } catch (err) {
          /* offline: keep the local card, sync on next launch */
        }
      }

      state.profile = {
        name: name,
        age: age,
        emergency: emergency,
        homeState: "",
        ref:
          state.idCard && state.idCard.qr_payload
            ? state.idCard.qr_payload.replace("KUMBH:VID:", "")
            : Math.random().toString(36).slice(2, 14),
      };
      localStorage.setItem("kumbh.profile", JSON.stringify(state.profile));
      closeRegister();
      renderId();
      switchScreen("id");
      toast(t("toast.live"));
    });
  }

  /* ------------------------------------------------------------------ voice */
  function speakScreen() {
    if (!("speechSynthesis" in window)) {
      toast(t("help.voice") + " —");
      return;
    }
    const active = document.querySelector(".screen.is-active");
    const text = (active ? active.innerText : "")
      .replace(/\s+/g, " ")
      .slice(0, 500);
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = LOCALES[window.I18N.lang] || "hi-IN";
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  }

  /* ------------------------------------------------------------------- boot */
  function renderAll() {
    renderChrome();
    renderHome();
    renderAlerts();
    renderMap();
    renderId();
    renderHelp();
  }

  async function boot() {
    window.I18N.lang = localStorage.getItem("kumbh.lang") || "hi";
    if (localStorage.getItem("kumbh.largeText") === "1")
      document.documentElement.classList.add("large-text");

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchScreen(tab.dataset.screen));
    });
    window.addEventListener("hashchange", handleLostHash);
    $("#sosFab").addEventListener("click", openSos);
    $("#sosCancel").addEventListener("click", closeSos);
    $("#sosBackdrop").addEventListener("click", closeSos);
    $("#sosConfirm").addEventListener("click", sendSos);
    $("#langBtn").addEventListener("click", openLang);
    $("#langBackdrop").addEventListener("click", closeLang);
    $("#voiceBtn").addEventListener("click", speakScreen);
    $("#offlineBtn").addEventListener("click", () => {
      state.offlineTiles = true;
      localStorage.setItem("kumbh.offlineTiles", "1");
      $("#offlineBtn").textContent = t("map.offline.done");
      toast(t("map.offline.done"));
    });

    // Long-press the SOS button for the silent path.
    let pressTimer = null;
    const fab = $("#sosFab");
    fab.addEventListener("pointerdown", () => {
      pressTimer = setTimeout(() => {
        $("#sosSilent").checked = true;
        openSos();
        toast(t("sos.silent"));
      }, 900);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach((event) => {
      fab.addEventListener(event, () => clearTimeout(pressTimer));
    });

    renderAll();
    const lostRoute = location.hash.match(
      /^#\/lost\/(report|confirmation|track)$/,
    );
    if (location.hash === "#/stay") renderStay();
    else if (location.hash === "#/transport") renderTransport();
    else if (location.hash === "#/lost/reports") renderReports();
    else if (lostRoute) renderLostRoute(lostRoute[1]);
    else switchScreen("home");

    await API.init();
    renderChrome();
    if (location.hash === "#/stay") renderStay();
    else if (location.hash === "#/transport") renderTransport();
    if (location.hash === "#/lost/reports") renderReports();
    if (state.screen === "lost" && state.lostRoute === "report") {
      state.lostLocations = await API.lostLocations();
      const list = document.getElementById("lpLocations");
      if (list)
        list.innerHTML = state.lostLocations
          .map((f) => `<option value="${esc(f.name)}"></option>`)
          .join("");
    }
    state.data = await API.home();
    state.nearby = await API.nearby("all");
    state.idCard = await API.idCard();
    renderHome();
    renderAlerts();
    renderMap();
    renderId();
    toast(API.mode === "live" ? t("toast.live") : t("toast.demo"));
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
