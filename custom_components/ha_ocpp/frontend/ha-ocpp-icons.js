const TYPE2_ICON = Object.freeze({
  path: "M6.35 3h11.3c.38 0 .75.15 1.02.42l1.25 1.25A10.25 10.25 0 0 1 22.5 11.5C22.5 17.3 17.8 22 12 22S1.5 17.3 1.5 11.5a10.25 10.25 0 0 1 2.58-6.83l1.25-1.25C5.6 3.15 5.97 3 6.35 3ZM8.7 5.2a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM15.3 5.2a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM5.7 10.4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM12 10.4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM18.3 10.4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM8.8 15.7a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8ZM15.2 15.7a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 1 0 0-3.8Z",
  viewBox: "0 0 24 24",
});

window.customIcons = window.customIcons || {};
window.customIcons["ha-ocpp"] = {
  getIcon: async (name) => (name === "type2" ? TYPE2_ICON : { path: "" }),
  getIconList: async () => [
    { name: "type2", keywords: ["charger", "ev", "ocpp", "type 2"] },
  ],
};
