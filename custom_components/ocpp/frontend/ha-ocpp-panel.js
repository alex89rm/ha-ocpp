const TEXT = {
  it: {
    overview: "Panoramica",
    wallboxes: "Wallbox",
    users: "Utenti e RFID",
    server: "Server",
    online: "Connessa",
    offline: "Non connessa",
    running: "In ascolto",
    stopped: "Arrestato",
    connections: "Connessioni",
    registeredUsers: "Utenti registrati",
    pendingCards: "Tessere da assegnare",
    noWallboxes: "Nessuna wallbox configurata",
    identity: "Identificazione",
    firmware: "Firmware",
    protocol: "Protocollo",
    profile: "Profilo wallbox",
    automatic: "Automatico",
    verified: "Verificato su hardware",
    stationLimits: "Limiti stazione",
    maxCurrent: "Corrente massima",
    maxPower: "Potenza massima",
    apply: "Applica",
    connector: "Connettore",
    transaction: "Transazione",
    energy: "Energia",
    sessionEnergy: "Energia sessione",
    power: "Potenza",
    current: "Corrente",
    voltage: "Tensione",
    start: "Avvia",
    stop: "Ferma",
    unlock: "Sblocca",
    enable: "Rendi disponibile",
    disable: "Rendi non disponibile",
    settings: "Impostazioni",
    meterInterval: "Aggiornamento in carica",
    idleInterval: "Aggiornamento a riposo",
    seconds: "secondi",
    save: "Salva",
    accessPolicy: "Politica di accesso",
    registeredOnly: "Autorizza solo tessere registrate",
    openAccess: "Accetta anche tessere sconosciute",
    addUser: "Aggiungi utente",
    readRfid: "Leggi RFID",
    chooseWallbox: "Seleziona wallbox",
    enrollmentActive: "Lettura attiva",
    noUsers: "Nessun utente registrato",
    cards: "Tessere",
    noCards: "Nessuna tessera associata",
    label: "Etichetta",
    status: "Stato",
    active: "Attiva",
    inactive: "Disattiva",
    delete: "Elimina",
    pending: "In attesa",
    assign: "Assegna",
    discard: "Scarta",
    userName: "Nome utente",
    selectUser: "Seleziona utente",
    cancel: "Annulla",
    host: "Indirizzo di ascolto",
    port: "Porta",
    tls: "TLS",
    certificate: "Certificato",
    privateKey: "Chiave privata",
    pingInterval: "Intervallo ping",
    pingTimeout: "Timeout ping",
    pingTries: "Tentativi ping",
    closeTimeout: "Timeout chiusura",
    loading: "Caricamento",
    retry: "Riprova",
    updated: "Modifica applicata",
    error: "Operazione non riuscita",
    connectedStations: "Wallbox connesse",
    activeServers: "Server attivi",
    allServers: "Tutti i server",
  },
  en: {
    overview: "Overview",
    wallboxes: "Wallboxes",
    users: "Users & RFID",
    server: "Server",
    online: "Connected",
    offline: "Disconnected",
    running: "Listening",
    stopped: "Stopped",
    connections: "Connections",
    registeredUsers: "Registered users",
    pendingCards: "Cards to assign",
    noWallboxes: "No wallboxes configured",
    identity: "Identity",
    firmware: "Firmware",
    protocol: "Protocol",
    profile: "Wallbox profile",
    automatic: "Automatic",
    verified: "Hardware verified",
    stationLimits: "Station limits",
    maxCurrent: "Maximum current",
    maxPower: "Maximum power",
    apply: "Apply",
    connector: "Connector",
    transaction: "Transaction",
    energy: "Energy",
    sessionEnergy: "Session energy",
    power: "Power",
    current: "Current",
    voltage: "Voltage",
    start: "Start",
    stop: "Stop",
    unlock: "Unlock",
    enable: "Make available",
    disable: "Make unavailable",
    settings: "Settings",
    meterInterval: "Charging update interval",
    idleInterval: "Idle update interval",
    seconds: "seconds",
    save: "Save",
    accessPolicy: "Access policy",
    registeredOnly: "Authorize registered cards only",
    openAccess: "Accept unknown cards",
    addUser: "Add user",
    readRfid: "Read RFID",
    chooseWallbox: "Select wallbox",
    enrollmentActive: "Reading active",
    noUsers: "No registered users",
    cards: "Cards",
    noCards: "No associated cards",
    label: "Label",
    status: "Status",
    active: "Active",
    inactive: "Inactive",
    delete: "Delete",
    pending: "Pending",
    assign: "Assign",
    discard: "Discard",
    userName: "User name",
    selectUser: "Select user",
    cancel: "Cancel",
    host: "Listen address",
    port: "Port",
    tls: "TLS",
    certificate: "Certificate",
    privateKey: "Private key",
    pingInterval: "Ping interval",
    pingTimeout: "Ping timeout",
    pingTries: "Ping attempts",
    closeTimeout: "Close timeout",
    loading: "Loading",
    retry: "Retry",
    updated: "Change applied",
    error: "Operation failed",
    connectedStations: "Connected wallboxes",
    activeServers: "Active servers",
    allServers: "All servers",
  },
};

class HaOcppPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "overview";
    this._snapshot = null;
    this._loading = false;
    this._busy = false;
    this._error = "";
    this._entryId = "";
    this._modal = null;
    this._unsubscribe = null;
    this._refreshTimer = null;
  }

  set hass(value) {
    const connectionChanged = this._hass?.connection !== value?.connection;
    this._hass = value;
    if (value && !this._snapshot && !this._loading) this._load();
    if (value && connectionChanged) this._subscribe();
  }

  set narrow(value) {
    this._narrow = value;
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    this._render();
    if (this._hass) {
      this._load();
      this._subscribe();
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    clearTimeout(this._refreshTimer);
  }

  get _t() {
    return TEXT[this._hass?.language?.startsWith("it") ? "it" : "en"];
  }

  async _subscribe() {
    if (!this._hass?.connection || this._unsubscribe) return;
    try {
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        () => this._scheduleRefresh(),
        { type: "ha_ocpp/subscribe" },
      );
    } catch (error) {
      this._error = error?.message || String(error);
      this._render();
    }
  }

  _scheduleRefresh() {
    clearTimeout(this._refreshTimer);
    this._refreshTimer = setTimeout(() => this._load(true), 250);
  }

  async _load(silent = false) {
    if (!this._hass || this._loading) return;
    this._loading = true;
    if (!silent) this._render();
    try {
      this._snapshot = await this._hass.callWS({ type: "ha_ocpp/dashboard" });
      const entries = this._snapshot.entries || [];
      if (!entries.some((item) => item.entry_id === this._entryId)) {
        this._entryId = entries[0]?.entry_id || "";
      }
      this._error = "";
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _command(message, successMessage = this._t.updated) {
    if (this._busy) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callWS(message);
      this._notify(successMessage);
      await this._load(true);
    } catch (error) {
      this._notify(`${this._t.error}: ${error?.message || error}`);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _notify(message) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        bubbles: true,
        composed: true,
        detail: { message },
      }),
    );
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _entry() {
    return (this._snapshot?.entries || []).find(
      (item) => item.entry_id === this._entryId,
    );
  }

  _allWallboxes() {
    return (this._snapshot?.entries || []).flatMap((entry) =>
      entry.wallboxes.map((wallbox) => ({ ...wallbox, serverName: entry.name })),
    );
  }

  _metric(metric, digits = 1) {
    if (metric?.value === null || metric?.value === undefined) return "-";
    const numeric = Number(metric.value);
    const value = Number.isFinite(numeric)
      ? numeric.toLocaleString(this._hass?.language || "it", {
          maximumFractionDigits: digits,
        })
      : this._escape(metric.value);
    return `${value}${metric.unit ? ` ${this._escape(metric.unit)}` : ""}`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const t = this._t;
    const entries = this._snapshot?.entries || [];
    const body = this._error
      ? `<div class="state-message error"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${this._escape(this._error)}</span><button class="primary" data-action="retry">${t.retry}</button></div>`
      : !this._snapshot
        ? `<div class="state-message"><span class="spinner"></span><span>${t.loading}</span></div>`
        : this._renderTab();

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <div class="app ${this._busy ? "busy" : ""}">
        <header>
          <div class="brand"><ha-icon icon="mdi:ev-station"></ha-icon><span>HA OCPP</span></div>
          ${
            entries.length > 1
              ? `<label class="server-picker"><span class="sr-only">${t.server}</span><select id="entry-select"><option value="">${t.allServers}</option>${entries.map((entry) => `<option value="${this._escape(entry.entry_id)}" ${entry.entry_id === this._entryId ? "selected" : ""}>${this._escape(entry.name)}</option>`).join("")}</select></label>`
              : ""
          }
        </header>
        <nav aria-label="HA OCPP">
          ${this._navItem("overview", "mdi:view-dashboard-outline", t.overview)}
          ${this._navItem("wallboxes", "mdi:ev-station", t.wallboxes)}
          ${this._navItem("users", "mdi:account-key-outline", t.users)}
          ${this._navItem("server", "mdi:server-network", t.server)}
        </nav>
        <main>${body}</main>
        ${this._renderModal()}
      </div>`;
    this._bindEvents();
  }

  _navItem(id, icon, label) {
    return `<button class="nav-item ${this._tab === id ? "selected" : ""}" data-tab="${id}"><ha-icon icon="${icon}"></ha-icon><span>${label}</span></button>`;
  }

  _renderTab() {
    if (this._tab === "wallboxes") return this._renderWallboxes();
    if (this._tab === "users") return this._renderUsers();
    if (this._tab === "server") return this._renderServers();
    return this._renderOverview();
  }

  _renderOverview() {
    const t = this._t;
    const entries = this._snapshot.entries || [];
    const wallboxes = this._allWallboxes();
    const users = entries.reduce(
      (total, entry) => total + entry.authorization.users.length,
      0,
    );
    const pending = entries.reduce(
      (total, entry) => total + entry.authorization.pending_credentials.length,
      0,
    );
    const connected = wallboxes.filter((item) => item.connected).length;
    return `
      <section class="page-heading"><div><h1>${t.overview}</h1><p>HA OCPP</p></div></section>
      <section class="summary-grid">
        ${this._summary("mdi:ev-station", t.connectedStations, connected, wallboxes.length)}
        ${this._summary("mdi:account-group-outline", t.registeredUsers, users)}
        ${this._summary("mdi:card-account-details-outline", t.pendingCards, pending)}
        ${this._summary("mdi:server-network", t.activeServers, entries.filter((e) => e.server.running).length)}
      </section>
      <section class="section-block">
        <div class="section-title"><h2>${t.wallboxes}</h2></div>
        <div class="wallbox-list compact-list">
          ${wallboxes.length ? wallboxes.map((wallbox) => this._wallboxOverviewRow(wallbox)).join("") : `<div class="empty">${t.noWallboxes}</div>`}
        </div>
      </section>`;
  }

  _summary(icon, label, value, total = null) {
    return `<article class="summary"><ha-icon icon="${icon}"></ha-icon><div><span>${label}</span><strong>${value}${total === null ? "" : `<small> / ${total}</small>`}</strong></div></article>`;
  }

  _wallboxOverviewRow(wallbox) {
    const t = this._t;
    const identity = wallbox.identity;
    return `<article class="overview-row">
      ${this._productVisual(wallbox)}
      <div class="overview-main"><strong>${this._escape(identity.model || wallbox.cpid)}</strong><span>${this._escape(identity.vendor || wallbox.profile.manufacturer || "OCPP")} · ${this._escape(wallbox.cpid)}</span></div>
      <span class="status ${wallbox.connected ? "online" : "offline"}"><i></i>${wallbox.connected ? t.online : t.offline}</span>
      <div class="overview-metric"><span>${t.power}</span><strong>${this._metric(wallbox.connectors[0]?.power)}</strong></div>
      <button class="icon-button" title="${t.wallboxes}" data-open-wallbox="${this._escape(wallbox.cpid)}"><ha-icon icon="mdi:chevron-right"></ha-icon></button>
    </article>`;
  }

  _productVisual(wallbox) {
    const image = wallbox.profile?.product_image;
    if (image) {
      return `<div class="product-visual"><img src="${this._escape(image)}" alt="${this._escape(wallbox.profile.name)}"></div>`;
    }
    return `<div class="product-visual fallback"><ha-icon icon="mdi:ev-station"></ha-icon></div>`;
  }

  _renderWallboxes() {
    const t = this._t;
    const wallboxes = this._entryId
      ? this._entry()?.wallboxes || []
      : this._allWallboxes();
    return `
      <section class="page-heading"><div><h1>${t.wallboxes}</h1><p>${wallboxes.length}</p></div></section>
      <section class="wallbox-grid">
        ${wallboxes.length ? wallboxes.map((item) => this._wallboxCard(item)).join("") : `<div class="empty">${t.noWallboxes}</div>`}
      </section>`;
  }

  _wallboxCard(wallbox) {
    const t = this._t;
    const identity = wallbox.identity;
    const entryId = wallbox.entry_id;
    const profileOptions = [
      { id: "auto", name: t.automatic },
      ...(this._snapshot.profiles || []),
    ];
    return `<article class="wallbox-card" data-wallbox="${this._escape(wallbox.cpid)}">
      <div class="wallbox-head">
        ${this._productVisual(wallbox)}
        <div class="wallbox-title"><h2>${this._escape(identity.model || wallbox.cpid)}</h2><p>${this._escape(identity.vendor || wallbox.profile.manufacturer || "OCPP")} · ${this._escape(wallbox.cpid)}</p></div>
        <span class="status ${wallbox.connected ? "online" : "offline"}"><i></i>${wallbox.connected ? t.online : t.offline}</span>
      </div>
      <div class="identity-grid">
        <div><span>${t.profile}</span><strong>${this._escape(wallbox.profile.name)}</strong>${wallbox.profile.hardware_verified ? `<small class="verified"><ha-icon icon="mdi:check-decagram"></ha-icon>${t.verified}</small>` : ""}</div>
        <div><span>${t.firmware}</span><strong>${this._escape(identity.firmware_version || "-")}</strong></div>
        <div><span>${t.protocol}</span><strong>${this._escape(wallbox.protocol || "-")}</strong></div>
        <div><span>${t.status}</span><strong>${this._escape(wallbox.status || "-")}</strong></div>
      </div>
      <div class="control-band">
        <div class="section-title"><h3>${t.stationLimits}</h3></div>
        <div class="limit-grid">
          ${wallbox.supported_rate_units.includes("Current") ? this._limitControl(wallbox, "Current", null) : ""}
          ${wallbox.supported_rate_units.includes("Power") ? this._limitControl(wallbox, "Power", null) : ""}
        </div>
      </div>
      <div class="connectors">
        ${wallbox.connectors.map((connector) => this._connector(wallbox, connector)).join("")}
      </div>
      <details class="settings-panel">
        <summary><ha-icon icon="mdi:tune-variant"></ha-icon>${t.settings}<ha-icon class="summary-arrow" icon="mdi:chevron-down"></ha-icon></summary>
        <div class="settings-content">
          <form class="profile-form" data-entry-id="${this._escape(entryId)}" data-cp-id="${this._escape(wallbox.cp_id)}">
            <label><span>${t.profile}</span><select name="profile_id">${profileOptions.map((profile) => `<option value="${this._escape(profile.id)}" ${profile.id === wallbox.profile_override ? "selected" : ""}>${this._escape(profile.name)}</option>`).join("")}</select></label>
            <button class="secondary" type="submit"><ha-icon icon="mdi:content-save-outline"></ha-icon>${t.save}</button>
          </form>
          <form class="wallbox-settings-form" data-entry-id="${this._escape(entryId)}" data-cp-id="${this._escape(wallbox.cp_id)}">
            <label><span>${t.meterInterval} (${t.seconds})</span><input type="number" min="1" name="meter_interval" value="${this._escape(wallbox.settings.meter_interval ?? 60)}"></label>
            <label><span>${t.idleInterval} (${t.seconds})</span><input type="number" min="1" name="idle_interval" value="${this._escape(wallbox.settings.idle_interval ?? 900)}"></label>
            <button class="secondary" type="submit"><ha-icon icon="mdi:content-save-outline"></ha-icon>${t.save}</button>
          </form>
        </div>
      </details>
    </article>`;
  }

  _limitControl(wallbox, unit, connectorId) {
    const t = this._t;
    const isPower = unit === "Power";
    const key = isPower ? "maximum_power" : "maximum_current";
    const configured = isPower
      ? wallbox.limits.configured_maximum_power
      : wallbox.limits.configured_maximum_current;
    const connector = connectorId
      ? wallbox.connectors.find((item) => item.id === connectorId)
      : null;
    const currentValue = connector
      ? connector.maximum_current
      : wallbox.limits[key];
    const max = Math.max(Number(configured) || (isPower ? 22000 : 32), 1);
    const value = Math.min(Math.max(Number(currentValue ?? max), 0), max);
    const step = isPower ? 10 : 1;
    const label = isPower ? t.maxPower : t.maxCurrent;
    const suffix = isPower ? "W" : "A";
    const controlId = `${wallbox.cpid}-${key}-${connectorId || 0}`.replaceAll(/[^a-zA-Z0-9_-]/g, "-");
    return `<form class="limit-control" data-entry-id="${this._escape(wallbox.entry_id)}" data-cpid="${this._escape(wallbox.cpid)}" data-unit="${unit}" data-connector-id="${connectorId || 0}">
      <div class="limit-label"><label for="${controlId}">${label}</label><div class="number-unit"><input class="limit-number" type="number" min="0" max="${max}" step="${step}" value="${value}"><span>${suffix}</span></div></div>
      <div class="range-row"><input id="${controlId}" class="limit-range" type="range" min="0" max="${max}" step="${step}" value="${value}"><button class="primary icon-action" type="submit" title="${t.apply}"><ha-icon icon="mdi:check"></ha-icon><span>${t.apply}</span></button></div>
    </form>`;
  }

  _connector(wallbox, connector) {
    const t = this._t;
    const charging = String(connector.status || "").toLowerCase() === "charging";
    const showConnectorLimit = wallbox.connectors.length > 1;
    return `<section class="connector-row">
      <div class="connector-header"><div><ha-icon icon="mdi:ev-plug-type2"></ha-icon><h3>${t.connector} ${connector.id}</h3></div><span class="connector-status ${charging ? "charging" : ""}">${this._escape(connector.status || "-")}</span></div>
      <div class="metrics-grid">
        ${this._metricCell("mdi:flash", t.power, connector.power)}
        ${this._metricCell("mdi:current-ac", t.current, connector.current)}
        ${this._metricCell("mdi:sine-wave", t.voltage, connector.voltage)}
        ${this._metricCell("mdi:lightning-bolt-circle", t.sessionEnergy, connector.session_energy)}
      </div>
      ${showConnectorLimit ? `<div class="connector-limit">${this._limitControl(wallbox, "Current", connector.id)}</div>` : ""}
      <div class="connector-actions">
        <button class="secondary connector-command" data-action="start" data-entry-id="${this._escape(wallbox.entry_id)}" data-cpid="${this._escape(wallbox.cpid)}" data-connector-id="${connector.id}"><ha-icon icon="mdi:play"></ha-icon>${t.start}</button>
        <button class="secondary connector-command" data-action="stop" data-entry-id="${this._escape(wallbox.entry_id)}" data-cpid="${this._escape(wallbox.cpid)}" data-connector-id="${connector.id}"><ha-icon icon="mdi:stop"></ha-icon>${t.stop}</button>
        <button class="icon-button connector-command" title="${t.unlock}" data-action="unlock" data-entry-id="${this._escape(wallbox.entry_id)}" data-cpid="${this._escape(wallbox.cpid)}" data-connector-id="${connector.id}"><ha-icon icon="mdi:lock-open-variant-outline"></ha-icon></button>
      </div>
    </section>`;
  }

  _metricCell(icon, label, metric) {
    return `<div class="metric"><ha-icon icon="${icon}"></ha-icon><span>${label}</span><strong>${this._metric(metric)}</strong></div>`;
  }

  _renderUsers() {
    const t = this._t;
    const entry = this._entry();
    if (!entry) return `<div class="empty">${t.server}</div>`;
    const auth = entry.authorization;
    const connectedWallboxes = entry.wallboxes.filter((item) => item.connected);
    return `
      <section class="page-heading actions-heading"><div><h1>${t.users}</h1><p>${auth.users.length} ${t.registeredUsers.toLowerCase()}</p></div><div class="heading-actions"><button class="secondary" data-action="open-enrollment" ${connectedWallboxes.length ? "" : "disabled"}><ha-icon icon="mdi:contactless-payment-circle-outline"></ha-icon>${t.readRfid}</button><button class="primary" data-action="open-add-user"><ha-icon icon="mdi:account-plus-outline"></ha-icon>${t.addUser}</button></div></section>
      <section class="policy-band">
        <div><ha-icon icon="mdi:shield-key-outline"></ha-icon><div><h2>${t.accessPolicy}</h2><span>${auth.registered_only ? t.registeredOnly : t.openAccess}</span></div></div>
        <label class="switch"><input id="registered-only" type="checkbox" ${auth.registered_only ? "checked" : ""}><span></span></label>
      </section>
      ${auth.enrollments.length ? `<section class="enrollment-band"><ha-icon icon="mdi:contactless-payment-circle"></ha-icon>${auth.enrollments.map((item) => `<span>${t.enrollmentActive}: ${this._escape(item.cp_id)} · ${item.seconds_remaining}s</span>`).join("")}</section>` : ""}
      ${auth.pending_credentials.length ? `<section class="section-block"><div class="section-title"><h2>${t.pendingCards}</h2><span class="count">${auth.pending_credentials.length}</span></div><div class="pending-list">${auth.pending_credentials.map((card) => this._pendingCard(entry, card)).join("")}</div></section>` : ""}
      <section class="section-block"><div class="section-title"><h2>${t.registeredUsers}</h2><span class="count">${auth.users.length}</span></div><div class="user-list">${auth.users.length ? auth.users.map((user) => this._userCard(entry, user)).join("") : `<div class="empty">${t.noUsers}</div>`}</div></section>`;
  }

  _pendingCard(entry, card) {
    const t = this._t;
    return `<article class="pending-row"><div class="pending-icon"><ha-icon icon="mdi:card-account-details-outline"></ha-icon></div><div><strong>${this._escape(card.masked_token)}</strong><span>${this._escape(card.cp_id)}</span></div><div class="row-actions"><button class="secondary assign-pending" data-entry-id="${this._escape(entry.entry_id)}" data-pending-id="${this._escape(card.id)}" ${entry.authorization.users.length ? "" : "disabled"}><ha-icon icon="mdi:account-arrow-left-outline"></ha-icon>${t.assign}</button><button class="icon-button auth-command" title="${t.discard}" data-action="discard_pending" data-entry-id="${this._escape(entry.entry_id)}" data-pending-id="${this._escape(card.id)}"><ha-icon icon="mdi:delete-outline"></ha-icon></button></div></article>`;
  }

  _userCard(entry, user) {
    const t = this._t;
    return `<article class="user-row">
      <form class="user-form" data-entry-id="${this._escape(entry.entry_id)}" data-user-id="${this._escape(user.id)}">
        <div class="user-avatar"><ha-icon icon="mdi:account-outline"></ha-icon></div>
        <label class="grow"><span class="sr-only">${t.userName}</span><input name="name" value="${this._escape(user.name)}" required></label>
        <label class="check-label"><input name="enabled" type="checkbox" ${user.enabled ? "checked" : ""}>${user.enabled ? t.active : t.inactive}</label>
        <button class="icon-button" type="submit" title="${t.save}"><ha-icon icon="mdi:content-save-outline"></ha-icon></button>
        <button class="icon-button danger auth-command" type="button" title="${t.delete}" data-action="delete_user" data-entry-id="${this._escape(entry.entry_id)}" data-user-id="${this._escape(user.id)}"><ha-icon icon="mdi:delete-outline"></ha-icon></button>
      </form>
      <div class="credentials"><div class="credentials-title"><span>${t.cards}</span><small>${user.credentials.length}</small></div>${user.credentials.length ? user.credentials.map((credential) => this._credential(entry, credential)).join("") : `<div class="no-credentials">${t.noCards}</div>`}</div>
    </article>`;
  }

  _credential(entry, credential) {
    const t = this._t;
    const statuses = entry.authorization.statuses || [];
    return `<form class="credential-row" data-entry-id="${this._escape(entry.entry_id)}" data-credential-id="${this._escape(credential.id)}">
      <code>${this._escape(credential.masked_token)}</code>
      <label><span class="sr-only">${t.label}</span><input name="label" placeholder="${t.label}" value="${this._escape(credential.label)}"></label>
      <label><span class="sr-only">${t.status}</span><select name="authorization_status">${statuses.map((status) => `<option value="${this._escape(status)}" ${status === credential.authorization_status ? "selected" : ""}>${this._escape(status)}</option>`).join("")}</select></label>
      <label class="switch small"><input name="enabled" type="checkbox" ${credential.enabled ? "checked" : ""}><span></span></label>
      <button class="icon-button" type="submit" title="${t.save}"><ha-icon icon="mdi:content-save-outline"></ha-icon></button>
      <button class="icon-button danger auth-command" type="button" title="${t.delete}" data-action="delete_credential" data-entry-id="${this._escape(entry.entry_id)}" data-credential-id="${this._escape(credential.id)}"><ha-icon icon="mdi:delete-outline"></ha-icon></button>
    </form>`;
  }

  _renderServers() {
    const t = this._t;
    const entries = this._entryId ? [this._entry()].filter(Boolean) : this._snapshot.entries;
    return `<section class="page-heading"><div><h1>${t.server}</h1><p>${entries.length}</p></div></section><section class="server-list">${entries.map((entry) => this._serverForm(entry)).join("")}</section>`;
  }

  _serverForm(entry) {
    const t = this._t;
    const server = entry.server;
    return `<article class="server-block"><div class="server-head"><div><ha-icon icon="mdi:server-network"></ha-icon><div><h2>${this._escape(entry.name)}</h2><span>${this._escape(server.id)}</span></div></div><span class="status ${server.running ? "online" : "offline"}"><i></i>${server.running ? t.running : t.stopped}</span></div>
      <form class="server-form" data-entry-id="${this._escape(entry.entry_id)}">
        <label><span>${t.host}</span><input name="host" value="${this._escape(server.host)}" required></label>
        <label><span>${t.port}</span><input name="port" type="number" min="1" max="65535" value="${server.port}" required></label>
        <label class="check-label server-check"><input name="ssl" type="checkbox" ${server.ssl ? "checked" : ""}>${t.tls}</label>
        <label><span>${t.pingInterval} (${t.seconds})</span><input name="websocket_ping_interval" type="number" min="1" value="${server.websocket_ping_interval}" required></label>
        <label><span>${t.pingTimeout} (${t.seconds})</span><input name="websocket_ping_timeout" type="number" min="1" value="${server.websocket_ping_timeout}" required></label>
        <label><span>${t.pingTries}</span><input name="websocket_ping_tries" type="number" min="0" value="${server.websocket_ping_tries}" required></label>
        <label><span>${t.closeTimeout} (${t.seconds})</span><input name="websocket_close_timeout" type="number" min="1" value="${server.websocket_close_timeout}" required></label>
        <div class="form-actions"><button class="primary" type="submit"><ha-icon icon="mdi:content-save-outline"></ha-icon>${t.save}</button></div>
      </form>
    </article>`;
  }

  _renderModal() {
    if (!this._modal) return "";
    const t = this._t;
    const entry = this._entry();
    if (this._modal.type === "add-user") {
      return `<div class="modal-backdrop" role="presentation"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><h2 id="modal-title">${t.addUser}</h2><button class="icon-button" data-action="close-modal" title="${t.cancel}"><ha-icon icon="mdi:close"></ha-icon></button></div><form id="add-user-form"><label><span>${t.userName}</span><input name="name" required autofocus></label><label class="check-label"><input name="enabled" type="checkbox" checked>${t.active}</label><div class="modal-actions"><button class="secondary" type="button" data-action="close-modal">${t.cancel}</button><button class="primary" type="submit"><ha-icon icon="mdi:account-plus-outline"></ha-icon>${t.addUser}</button></div></form></section></div>`;
    }
    if (this._modal.type === "enrollment") {
      return `<div class="modal-backdrop" role="presentation"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><h2 id="modal-title">${t.readRfid}</h2><button class="icon-button" data-action="close-modal" title="${t.cancel}"><ha-icon icon="mdi:close"></ha-icon></button></div><form id="enrollment-form"><label><span>${t.chooseWallbox}</span><select name="cpid" required>${entry.wallboxes.filter((item) => item.connected).map((item) => `<option value="${this._escape(item.cpid)}">${this._escape(item.identity.model || item.cpid)} · ${this._escape(item.cpid)}</option>`).join("")}</select></label><div class="modal-actions"><button class="secondary" type="button" data-action="close-modal">${t.cancel}</button><button class="primary" type="submit"><ha-icon icon="mdi:contactless-payment-circle-outline"></ha-icon>${t.readRfid}</button></div></form></section></div>`;
    }
    if (this._modal.type === "assign") {
      return `<div class="modal-backdrop" role="presentation"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><h2 id="modal-title">${t.assign}</h2><button class="icon-button" data-action="close-modal" title="${t.cancel}"><ha-icon icon="mdi:close"></ha-icon></button></div><form id="assign-form"><label><span>${t.selectUser}</span><select name="user_id" required>${entry.authorization.users.map((user) => `<option value="${this._escape(user.id)}">${this._escape(user.name)}</option>`).join("")}</select></label><label><span>${t.label}</span><input name="label"></label><div class="modal-actions"><button class="secondary" type="button" data-action="close-modal">${t.cancel}</button><button class="primary" type="submit"><ha-icon icon="mdi:account-arrow-left-outline"></ha-icon>${t.assign}</button></div></form></section></div>`;
    }
    return "";
  }

  _bindEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this._modal = null;
        this._render();
      });
    });
    root.querySelector("#entry-select")?.addEventListener("change", (event) => {
      this._entryId = event.target.value;
      this._render();
    });
    root.querySelector('[data-action="retry"]')?.addEventListener("click", () => this._load());
    root.querySelectorAll("[data-open-wallbox]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = "wallboxes";
        this._render();
        this.shadowRoot.querySelector(`[data-wallbox="${CSS.escape(button.dataset.openWallbox)}"]`)?.scrollIntoView({ behavior: "smooth" });
      });
    });
    root.querySelectorAll(".limit-control").forEach((form) => {
      const range = form.querySelector(".limit-range");
      const number = form.querySelector(".limit-number");
      range.addEventListener("input", () => { number.value = range.value; });
      number.addEventListener("input", () => { range.value = number.value; });
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._command({ type: "ha_ocpp/wallbox/command", entry_id: form.dataset.entryId, cpid: form.dataset.cpid, action: "set_limit", value: Number(number.value), unit: form.dataset.unit, connector_id: Number(form.dataset.connectorId) });
      });
    });
    root.querySelectorAll(".connector-command").forEach((button) => {
      button.addEventListener("click", () => this._command({ type: "ha_ocpp/wallbox/command", entry_id: button.dataset.entryId, cpid: button.dataset.cpid, action: button.dataset.action, connector_id: Number(button.dataset.connectorId) }));
    });
    root.querySelectorAll(".profile-form").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._command({ type: "ha_ocpp/wallbox/profile", entry_id: form.dataset.entryId, cp_id: form.dataset.cpId, profile_id: new FormData(form).get("profile_id") });
      });
    });
    root.querySelectorAll(".wallbox-settings-form").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(form);
        this._command({ type: "ha_ocpp/wallbox/settings", entry_id: form.dataset.entryId, cp_id: form.dataset.cpId, meter_interval: Number(data.get("meter_interval")), idle_interval: Number(data.get("idle_interval")) });
      });
    });
    root.querySelector("#registered-only")?.addEventListener("change", (event) => this._command({ type: "ha_ocpp/authorization/command", entry_id: this._entryId, action: "set_policy", registered_only: event.target.checked }));
    root.querySelector('[data-action="open-add-user"]')?.addEventListener("click", () => { this._modal = { type: "add-user" }; this._render(); });
    root.querySelector('[data-action="open-enrollment"]')?.addEventListener("click", () => { this._modal = { type: "enrollment" }; this._render(); });
    root.querySelectorAll('[data-action="close-modal"]').forEach((button) => button.addEventListener("click", () => { this._modal = null; this._render(); }));
    root.querySelector(".modal-backdrop")?.addEventListener("click", (event) => { if (event.target.classList.contains("modal-backdrop")) { this._modal = null; this._render(); } });
    root.querySelector("#add-user-form")?.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(event.target); this._modal = null; this._command({ type: "ha_ocpp/authorization/command", entry_id: this._entryId, action: "add_user", name: data.get("name"), enabled: data.get("enabled") === "on" });
    });
    root.querySelector("#enrollment-form")?.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(event.target); this._modal = null; this._command({ type: "ha_ocpp/authorization/command", entry_id: this._entryId, action: "start_enrollment", cpid: data.get("cpid") });
    });
    root.querySelectorAll(".assign-pending").forEach((button) => button.addEventListener("click", () => { this._modal = { type: "assign", entryId: button.dataset.entryId, pendingId: button.dataset.pendingId }; this._render(); }));
    root.querySelector("#assign-form")?.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(event.target); const modal = this._modal; this._modal = null; this._command({ type: "ha_ocpp/authorization/command", entry_id: modal.entryId, action: "assign_pending", pending_id: modal.pendingId, user_id: data.get("user_id"), label: data.get("label") });
    });
    root.querySelectorAll(".user-form").forEach((form) => form.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(form); this._command({ type: "ha_ocpp/authorization/command", entry_id: form.dataset.entryId, action: "update_user", user_id: form.dataset.userId, name: data.get("name"), enabled: data.get("enabled") === "on" });
    }));
    root.querySelectorAll(".credential-row").forEach((form) => form.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(form); this._command({ type: "ha_ocpp/authorization/command", entry_id: form.dataset.entryId, action: "update_credential", credential_id: form.dataset.credentialId, label: data.get("label"), enabled: data.get("enabled") === "on", authorization_status: data.get("authorization_status") });
    }));
    root.querySelectorAll(".auth-command").forEach((button) => button.addEventListener("click", () => {
      this._command({ type: "ha_ocpp/authorization/command", entry_id: button.dataset.entryId, action: button.dataset.action, ...(button.dataset.userId && { user_id: button.dataset.userId }), ...(button.dataset.credentialId && { credential_id: button.dataset.credentialId }), ...(button.dataset.pendingId && { pending_id: button.dataset.pendingId }) });
    }));
    root.querySelectorAll(".server-form").forEach((form) => form.addEventListener("submit", (event) => {
      event.preventDefault(); const data = new FormData(form); this._command({ type: "ha_ocpp/server/settings", entry_id: form.dataset.entryId, host: data.get("host"), port: Number(data.get("port")), ssl: data.get("ssl") === "on", websocket_ping_interval: Number(data.get("websocket_ping_interval")), websocket_ping_timeout: Number(data.get("websocket_ping_timeout")), websocket_ping_tries: Number(data.get("websocket_ping_tries")), websocket_close_timeout: Number(data.get("websocket_close_timeout")) });
    }));
  }

  _styles() {
    return `
      :host { display:block; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      * { box-sizing:border-box; letter-spacing:0; }
      button, input, select { font:inherit; }
      button { cursor:pointer; }
      button:disabled { cursor:not-allowed; opacity:.5; }
      .app { min-height:100vh; }
      .app.busy { cursor:progress; }
      header { height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 28px; color:#fff; background:#17242b; border-bottom:3px solid var(--primary-color, #03a9f4); }
      .brand { display:flex; align-items:center; gap:12px; font-size:20px; font-weight:700; }
      .brand ha-icon { color:#4dd0e1; }
      .server-picker select { min-width:180px; color:#fff; background:#263940; border-color:#52656c; }
      nav { position:sticky; top:0; z-index:4; height:52px; display:flex; align-items:stretch; gap:4px; padding:0 24px; background:var(--card-background-color, #fff); border-bottom:1px solid var(--divider-color, #ddd); }
      .nav-item { min-width:120px; display:flex; align-items:center; justify-content:center; gap:8px; padding:0 14px; color:var(--secondary-text-color); background:transparent; border:0; border-bottom:3px solid transparent; }
      .nav-item.selected { color:var(--primary-color, #0288d1); border-bottom-color:var(--primary-color, #0288d1); font-weight:600; }
      main { max-width:1440px; margin:0 auto; padding:24px 28px 56px; }
      h1, h2, h3, p { margin:0; }
      h1 { font-size:26px; line-height:1.25; }
      h2 { font-size:18px; line-height:1.3; }
      h3 { font-size:15px; line-height:1.3; }
      .page-heading { min-height:56px; display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:22px; }
      .page-heading p { margin-top:4px; color:var(--secondary-text-color); }
      .actions-heading { align-items:center; }
      .heading-actions, .row-actions, .connector-actions, .modal-actions, .form-actions { display:flex; align-items:center; gap:8px; }
      .summary-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }
      .summary { min-height:100px; display:flex; align-items:center; gap:16px; padding:18px; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .summary > ha-icon { width:36px; height:36px; color:var(--primary-color, #0288d1); }
      .summary div { min-width:0; display:flex; flex-direction:column; gap:6px; }
      .summary span { color:var(--secondary-text-color); font-size:13px; }
      .summary strong { font-size:25px; }
      .summary small { color:var(--secondary-text-color); font-size:14px; }
      .section-block { margin-top:28px; }
      .section-title { min-height:30px; display:flex; align-items:center; gap:8px; margin-bottom:10px; }
      .count { min-width:24px; height:24px; display:inline-flex; align-items:center; justify-content:center; color:var(--secondary-text-color); background:var(--secondary-background-color); border-radius:12px; font-size:12px; }
      .compact-list, .user-list, .pending-list, .server-list { display:flex; flex-direction:column; gap:10px; }
      .overview-row { min-height:78px; display:grid; grid-template-columns:52px minmax(180px, 1fr) auto minmax(120px, .35fr) 40px; align-items:center; gap:14px; padding:12px 14px; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .product-visual { width:52px; height:52px; display:flex; align-items:center; justify-content:center; overflow:hidden; border-radius:6px; background:var(--secondary-background-color, #f2f3f4); }
      .product-visual img { width:100%; height:100%; object-fit:contain; }
      .product-visual ha-icon { width:30px; height:30px; color:#367e89; }
      .overview-main { min-width:0; display:flex; flex-direction:column; gap:4px; }
      .overview-main strong, .overview-main span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .overview-main span, .overview-metric span { color:var(--secondary-text-color); font-size:12px; }
      .overview-metric { display:flex; flex-direction:column; gap:4px; }
      .status { display:inline-flex; align-items:center; gap:7px; min-height:28px; color:var(--secondary-text-color); font-size:12px; font-weight:600; }
      .status i { width:8px; height:8px; border-radius:50%; background:#9e9e9e; }
      .status.online { color:#217a4b; }
      .status.online i { background:#2eaf68; }
      .wallbox-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 580px), 1fr)); gap:16px; }
      .wallbox-card { overflow:hidden; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .wallbox-head { min-height:88px; display:grid; grid-template-columns:60px minmax(0, 1fr) auto; align-items:center; gap:14px; padding:16px 18px; border-bottom:1px solid var(--divider-color, #ddd); }
      .wallbox-head .product-visual { width:60px; height:60px; }
      .wallbox-title { min-width:0; }
      .wallbox-title h2, .wallbox-title p { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .wallbox-title p { margin-top:4px; color:var(--secondary-text-color); font-size:13px; }
      .identity-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; padding:14px 18px; background:var(--secondary-background-color, #f5f5f5); border-bottom:1px solid var(--divider-color, #ddd); }
      .identity-grid > div { min-width:0; display:flex; flex-direction:column; gap:4px; }
      .identity-grid span { color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; }
      .identity-grid strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; }
      .verified { display:flex; align-items:center; gap:3px; color:#217a4b; font-size:10px; }
      .verified ha-icon { width:13px; height:13px; }
      .control-band { padding:16px 18px; border-bottom:1px solid var(--divider-color, #ddd); }
      .control-band .section-title { margin-bottom:6px; }
      .limit-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:18px; }
      .limit-control { min-width:0; }
      .limit-label, .range-row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
      .limit-label label { font-size:13px; font-weight:600; }
      .number-unit { width:112px; height:36px; display:grid; grid-template-columns:1fr 28px; align-items:center; overflow:hidden; border:1px solid var(--divider-color, #aaa); border-radius:5px; }
      .number-unit input { width:100%; height:100%; padding:0 7px; text-align:right; border:0; background:transparent; color:var(--primary-text-color); }
      .number-unit span { color:var(--secondary-text-color); font-size:12px; }
      .range-row { margin-top:7px; }
      input[type="range"] { min-width:0; flex:1; accent-color:var(--primary-color, #0288d1); }
      .connectors { display:flex; flex-direction:column; }
      .connector-row { padding:16px 18px; border-bottom:1px solid var(--divider-color, #ddd); }
      .connector-row:last-child { border-bottom:0; }
      .connector-header { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }
      .connector-header > div { display:flex; align-items:center; gap:8px; }
      .connector-header ha-icon { color:#367e89; }
      .connector-status { color:var(--secondary-text-color); font-size:12px; }
      .connector-status.charging { color:#217a4b; font-weight:600; }
      .metrics-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:8px; }
      .metric { min-width:0; display:grid; grid-template-columns:22px 1fr; gap:1px 6px; align-items:center; }
      .metric ha-icon { grid-row:1 / 3; width:20px; height:20px; color:var(--secondary-text-color); }
      .metric span { color:var(--secondary-text-color); font-size:10px; }
      .metric strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; }
      .connector-limit { margin-top:16px; padding-top:14px; border-top:1px solid var(--divider-color, #ddd); }
      .connector-actions { justify-content:flex-end; margin-top:14px; }
      .settings-panel { border-top:1px solid var(--divider-color, #ddd); }
      .settings-panel summary { min-height:48px; display:flex; align-items:center; gap:8px; padding:0 18px; cursor:pointer; list-style:none; font-weight:600; font-size:13px; }
      .settings-panel summary::-webkit-details-marker { display:none; }
      .summary-arrow { margin-left:auto; transition:transform .15s ease; }
      details[open] .summary-arrow { transform:rotate(180deg); }
      .settings-content { display:flex; flex-direction:column; gap:14px; padding:0 18px 18px; }
      .profile-form, .wallbox-settings-form { display:grid; grid-template-columns:minmax(180px, 1fr) minmax(180px, 1fr) auto; align-items:end; gap:10px; }
      .profile-form label { grid-column:span 2; }
      label { min-width:0; display:flex; flex-direction:column; gap:6px; color:var(--secondary-text-color); font-size:12px; }
      input, select { min-width:0; height:40px; padding:0 10px; color:var(--primary-text-color); background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #aaa); border-radius:5px; }
      input:focus, select:focus { outline:2px solid color-mix(in srgb, var(--primary-color, #0288d1) 35%, transparent); border-color:var(--primary-color, #0288d1); }
      .primary, .secondary, .icon-button { min-height:40px; display:inline-flex; align-items:center; justify-content:center; gap:7px; border-radius:5px; }
      .primary { padding:0 14px; color:#fff; background:var(--primary-color, #0288d1); border:1px solid var(--primary-color, #0288d1); font-weight:600; }
      .secondary { padding:0 13px; color:var(--primary-text-color); background:transparent; border:1px solid var(--divider-color, #aaa); }
      .icon-button { width:40px; padding:0; color:var(--secondary-text-color); background:transparent; border:1px solid transparent; }
      .icon-button:hover { background:var(--secondary-background-color, #f5f5f5); }
      .icon-button.danger { color:#b3261e; }
      .icon-action { min-width:92px; }
      .policy-band { min-height:76px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 18px; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .policy-band > div { display:flex; align-items:center; gap:12px; }
      .policy-band > div > ha-icon { color:#367e89; }
      .policy-band h2 { font-size:15px; }
      .policy-band span { color:var(--secondary-text-color); font-size:12px; }
      .switch { display:inline-flex; align-items:center; }
      .switch input { position:absolute; opacity:0; pointer-events:none; }
      .switch > span { width:42px; height:24px; position:relative; border-radius:12px; background:#8c969b; transition:.15s ease; }
      .switch > span::after { content:""; width:18px; height:18px; position:absolute; top:3px; left:3px; border-radius:50%; background:#fff; transition:.15s ease; }
      .switch input:checked + span { background:#21885a; }
      .switch input:checked + span::after { transform:translateX(18px); }
      .switch.small > span { width:36px; height:20px; }
      .switch.small > span::after { width:14px; height:14px; }
      .switch.small input:checked + span::after { transform:translateX(16px); }
      .enrollment-band { min-height:48px; display:flex; align-items:center; gap:10px; margin-top:12px; padding:10px 14px; color:#7a4c00; background:#fff4d6; border:1px solid #e8c66b; border-radius:8px; font-size:13px; }
      .pending-row { min-height:66px; display:grid; grid-template-columns:42px minmax(120px, 1fr) auto; align-items:center; gap:12px; padding:11px 14px; background:var(--card-background-color, #fff); border:1px solid #e8c66b; border-left:4px solid #d39b17; border-radius:8px; }
      .pending-row > div:nth-child(2) { display:flex; flex-direction:column; gap:3px; }
      .pending-row span { color:var(--secondary-text-color); font-size:12px; }
      .pending-icon { width:38px; height:38px; display:flex; align-items:center; justify-content:center; color:#956900; background:#fff4d6; border-radius:6px; }
      .user-row { overflow:hidden; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .user-form { min-height:66px; display:grid; grid-template-columns:42px minmax(160px, 1fr) auto 40px 40px; align-items:center; gap:9px; padding:11px 14px; }
      .user-avatar { width:38px; height:38px; display:flex; align-items:center; justify-content:center; color:#367e89; background:var(--secondary-background-color, #f5f5f5); border-radius:50%; }
      .grow input { width:100%; }
      .check-label { flex-direction:row; align-items:center; gap:7px; color:var(--primary-text-color); }
      .check-label input { width:18px; height:18px; padding:0; accent-color:var(--primary-color, #0288d1); }
      .credentials { padding:0 14px 12px 65px; }
      .credentials-title { display:flex; align-items:center; gap:6px; margin:4px 0 8px; color:var(--secondary-text-color); font-size:12px; }
      .credentials-title small { min-width:20px; text-align:center; }
      .credential-row { min-height:52px; display:grid; grid-template-columns:110px minmax(120px, 1fr) 130px 42px 40px 40px; align-items:center; gap:8px; padding:6px 0; border-top:1px solid var(--divider-color, #ddd); }
      .credential-row code { font-size:12px; }
      .no-credentials { padding:8px 0; color:var(--secondary-text-color); font-size:12px; border-top:1px solid var(--divider-color, #ddd); }
      .server-block { overflow:hidden; background:var(--card-background-color, #fff); border:1px solid var(--divider-color, #ddd); border-radius:8px; }
      .server-head { min-height:76px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 18px; border-bottom:1px solid var(--divider-color, #ddd); }
      .server-head > div { display:flex; align-items:center; gap:12px; }
      .server-head > div > ha-icon { width:32px; height:32px; color:#367e89; }
      .server-head span { color:var(--secondary-text-color); font-size:12px; }
      .server-form { display:grid; grid-template-columns:repeat(3, minmax(160px, 1fr)); align-items:end; gap:14px; padding:18px; }
      .server-check { min-height:40px; }
      .form-actions { grid-column:1 / -1; justify-content:flex-end; }
      .empty, .state-message { min-height:160px; display:flex; align-items:center; justify-content:center; gap:12px; color:var(--secondary-text-color); }
      .state-message.error { flex-direction:column; color:#b3261e; }
      .spinner { width:28px; height:28px; border:3px solid var(--divider-color, #ddd); border-top-color:var(--primary-color, #0288d1); border-radius:50%; animation:spin .8s linear infinite; }
      .modal-backdrop { position:fixed; z-index:20; inset:0; display:flex; align-items:center; justify-content:center; padding:20px; background:rgba(0,0,0,.48); }
      .modal { width:min(460px, 100%); max-height:calc(100vh - 40px); overflow:auto; padding:18px; background:var(--card-background-color, #fff); border-radius:8px; box-shadow:0 12px 42px rgba(0,0,0,.3); }
      .modal-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:18px; }
      .modal form { display:flex; flex-direction:column; gap:14px; }
      .modal-actions { justify-content:flex-end; margin-top:8px; }
      .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
      @keyframes spin { to { transform:rotate(360deg); } }
      @media (max-width:900px) {
        .summary-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
        .identity-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
        .server-form { grid-template-columns:repeat(2, minmax(140px, 1fr)); }
        .credential-row { grid-template-columns:100px minmax(110px, 1fr) 110px 38px 36px 36px; }
      }
      @media (max-width:650px) {
        header { height:56px; padding:0 16px; }
        nav { height:60px; padding:0 4px; gap:0; }
        .nav-item { min-width:0; flex:1; flex-direction:column; gap:2px; padding:5px 2px; font-size:10px; }
        .nav-item ha-icon { width:22px; height:22px; }
        main { padding:18px 12px 40px; }
        h1 { font-size:22px; }
        .page-heading { min-height:46px; margin-bottom:14px; }
        .actions-heading { align-items:flex-start; flex-direction:column; }
        .heading-actions { width:100%; }
        .heading-actions button { flex:1; }
        .summary-grid { grid-template-columns:1fr 1fr; gap:8px; }
        .summary { min-height:84px; padding:12px; gap:10px; }
        .summary > ha-icon { width:28px; height:28px; }
        .summary strong { font-size:20px; }
        .overview-row { grid-template-columns:46px minmax(0, 1fr) 40px; gap:10px; }
        .overview-row .product-visual { width:46px; height:46px; }
        .overview-row .status, .overview-row .overview-metric { grid-column:2; }
        .overview-row .icon-button { grid-column:3; grid-row:1 / 3; }
        .wallbox-head { grid-template-columns:52px minmax(0, 1fr); padding:14px; }
        .wallbox-head .product-visual { width:52px; height:52px; }
        .wallbox-head .status { grid-column:2; }
        .identity-grid { padding:12px 14px; }
        .control-band, .connector-row { padding:14px; }
        .limit-grid { grid-template-columns:1fr; }
        .metrics-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px 8px; }
        .profile-form, .wallbox-settings-form { grid-template-columns:1fr; }
        .profile-form label { grid-column:auto; }
        .profile-form button, .wallbox-settings-form button { width:100%; }
        .pending-row { grid-template-columns:40px minmax(0, 1fr); }
        .pending-row .row-actions { grid-column:1 / -1; justify-content:flex-end; }
        .user-form { grid-template-columns:38px minmax(0, 1fr) 36px 36px; padding:10px; }
        .user-form .check-label { grid-column:2; }
        .credentials { padding:0 10px 10px; }
        .credential-row { grid-template-columns:minmax(90px, 1fr) 90px 36px 36px; gap:6px; }
        .credential-row label:first-of-type { grid-column:1 / 3; }
        .credential-row .switch { justify-content:center; }
        .server-form { grid-template-columns:1fr; padding:14px; }
        .server-picker select { min-width:130px; max-width:45vw; }
        .icon-action { min-width:42px; width:42px; padding:0; }
        .icon-action span { display:none; }
      }
    `;
  }
}

if (!customElements.get("ha-ocpp-panel")) {
  customElements.define("ha-ocpp-panel", HaOcppPanel);
}
