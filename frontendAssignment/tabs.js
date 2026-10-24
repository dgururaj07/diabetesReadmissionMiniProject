// Shows one tab panel at a time. The URL hash (#add / #search / #care) keeps the tab after a reload.
const TAB_NAMES = ["add", "search", "care"];
const TABS = Object.fromEntries(TAB_NAMES.map((name) => [name, {
  tab: document.getElementById(`tab-${name}`),
  panel: document.getElementById(`panel-${name}`),
}]));

function selectTab(name, moveFocus) {
  for (const [key, { tab, panel }] of Object.entries(TABS)) {
    const active = key === name;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;  // only the active tab is in the Tab key order
    panel.hidden = !active;
  }
  if (moveFocus) {
    TABS[name].tab.focus();
  }
  history.replaceState(null, "", `#${name}`);
  if (name === "search") {
    ensureSearchLoaded();
  }
}

TAB_NAMES.forEach(function (name, index) {
  const { tab } = TABS[name];
  tab.addEventListener("click", () => selectTab(name, false));
  // Left / right arrows move between tabs (wrapping around), as screen reader users expect
  tab.addEventListener("keydown", function (event) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0) {
      selectTab(TAB_NAMES[(index + step + TAB_NAMES.length) % TAB_NAMES.length], true);
    }
  });
});

const startTab = location.hash.slice(1);
selectTab(TAB_NAMES.includes(startTab) ? startTab : "add", false);
