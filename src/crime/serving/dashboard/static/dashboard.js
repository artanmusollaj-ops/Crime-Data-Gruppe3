// Das Brett »Überblick«. Die Diagramme sind eigenes SVG statt einer
// Bibliothek: zwei Formen (Linie, gruppierte Balken), kein CDN, und die
// Content-Security-Policy bleibt bei 'self'.
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const FARBE = { chicago: "#17a38b", detroit: "#2f7de1" };
const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
// Wie in den Dokumenten: 2'661'953 und 94,5 - Hochkomma fuer Tausender,
// Komma fuer Dezimalen. de-CH allein schreibt 94.5.
const ganz = new Intl.NumberFormat("de-CH", { maximumFractionDigits: 0 });
const zahl = { format: (v) => ganz.format(v).replace(/[’‘]/g, "'") };
const komma = { format: (v) => v.toFixed(1).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, "'") };
const zustand = { mass: "anzahl", daten: null };

const SYMBOLE = {
  dokument: "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h6 M10 16h6",
  ordner: "M3 7h6l2 2h10v10H3z M3 11h18",
  balken: "M5 20V12 M10 20V6 M15 20v-9 M20 20V9",
  kalender: "M4 6h16v14H4z M4 10h16 M8 3v5 M16 3v5 M8 14h2 M12 14h2 M16 14h0 M8 17h2",
};

function el(name, attrs = {}, text) {
  const e = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}

function monatsname(iso) {
  const [j, m] = iso.split("-");
  return MONATE[Number(m) - 1] + " " + j;
}

// Die Achse endet bei vier glatten Schritten: 4 x 5'000, nicht 4 x 4'687,5.
// Ganze Schritte ohne Dezimalen, halbe mit: 0, 0,5, 1, 1,5 statt 0, 1, 1, 2.
const achsenzahl = (v) => (Number.isInteger(v) ? zahl.format(v) : komma.format(v));

function runde(max) {
  if (max <= 0) return 4;
  const schritt = max / 4, p = Math.pow(10, Math.floor(Math.log10(schritt)));
  for (const f of [1, 2, 2.5, 5, 10]) if (f * p >= schritt) return 4 * f * p;
  return 40 * p;
}

function leer(ziel, text) {
  const svg = el("svg", { viewBox: "0 0 600 240" });
  svg.append(el("text", { x: 300, y: 120, "text-anchor": "middle", class: "leer" }, text));
  ziel.replaceChildren(svg);
}

function legende(tafel, staedte) {
  const l = tafel.querySelector(".legende");
  l.replaceChildren(...staedte.map((s) => {
    const span = document.createElement("span");
    span.className = s.stadt;
    span.textContent = s.name;
    return span;
  }));
}

function linie(ziel, verlauf) {
  const b = Math.max(ziel.clientWidth, 320), h = 260, l = 56, r = 36, o = 16, u = 32;
  const max = runde(Math.max(1, ...verlauf.reihen.flatMap((s) => s.werte.filter((v) => v !== null))));
  const n = verlauf.monate.length;
  const x = (i) => l + (n === 1 ? (b - l - r) / 2 : (i * (b - l - r)) / (n - 1));
  const y = (v) => o + (h - o - u) * (1 - v / max);
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img",
    "aria-label": "Delikte je Monat und Stadt" });
  for (let k = 0; k <= 4; k++) {
    const v = (max * k) / 4;
    svg.append(el("line", { x1: l, x2: b - r, y1: y(v), y2: y(v), class: "achse" }));
    svg.append(el("text", { x: l - 8, y: y(v) + 4, "text-anchor": "end" }, zahl.format(v)));
  }
  verlauf.monate.forEach((m, i) => {
    svg.append(el("line", { x1: x(i), x2: x(i), y1: o, y2: h - u, class: "achse" }));
    // Ab sieben Monaten nur der Monat; das Jahr steht in der Leiste.
    svg.append(el("text", { x: x(i), y: h - 10, "text-anchor": "middle" },
      n > 6 ? MONATE[Number(m.split("-")[1]) - 1] : monatsname(m)));
  });
  for (const s of verlauf.reihen) {
    // Ein Monat ohne Daten unterbricht die Linie, statt auf null zu fallen.
    let strecke = [];
    const ziehe = () => {
      if (strecke.length > 1) svg.append(el("polyline", { points: strecke.join(" "), fill: "none",
        stroke: FARBE[s.stadt], "stroke-width": 2.5 }));
      strecke = [];
    };
    s.werte.forEach((v, i) => (v === null ? ziehe() : strecke.push(`${x(i)},${y(v)}`)));
    ziehe();
    s.werte.forEach((v, i) => {
      if (v === null) return;
      // Ein Teilmonat ist hohl: Sein Wert ist kein Monatswert.
      const teil = s.status[i] === "teil";
      const c = el("circle", { cx: x(i), cy: y(v), r: 4.5, fill: teil ? "#fff" : FARBE[s.stadt],
        stroke: FARBE[s.stadt], "stroke-width": 2 });
      c.append(el("title", {}, `${s.name}, ${monatsname(verlauf.monate[i])}: ${zahl.format(v)}`
        + (teil ? " (Teilmonat)" : "")));
      svg.append(c);
    });
  }
  ziel.replaceChildren(svg);
}

function balken(ziel, zeilen, staedte, format, achse = format) {
  const werte = zeilen.flatMap((z) => staedte.map((s) => z.werte[s.stadt] ?? 0));
  if (!zeilen.length) return leer(ziel, "Keine Delikte in dieser Auswahl");
  const b = Math.max(ziel.clientWidth, 320), l = 170, r = 64, o = 6, u = 26;
  const balkenhoehe = 14, luecke = 3, gruppe = staedte.length * (balkenhoehe + luecke) + 14;
  const h = o + zeilen.length * gruppe + u;
  const max = runde(Math.max(1, ...werte));
  const x = (v) => l + ((b - l - r) * v) / max;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 4; k++) {
    const v = (max * k) / 4;
    svg.append(el("line", { x1: x(v), x2: x(v), y1: o, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - 8, "text-anchor": "middle" }, achse(v)));
  }
  zeilen.forEach((z, i) => {
    const y0 = o + i * gruppe;
    const mitte = y0 + (staedte.length * (balkenhoehe + luecke)) / 2;
    svg.append(el("text", { x: l - 10, y: mitte + 4, "text-anchor": "end" }, z.name));
    staedte.forEach((s, j) => {
      const v = z.werte[s.stadt];
      const y = y0 + j * (balkenhoehe + luecke);
      const rect = el("rect", { x: l, y, width: Math.max(0, x(v ?? 0) - l), height: balkenhoehe,
        rx: 2, fill: FARBE[s.stadt] });
      rect.append(el("title", {}, `${s.name}, ${z.name}: ${v === null ? "keine Rate" : format(v)}`));
      svg.append(rect);
      svg.append(el("text", { x: x(v ?? 0) + 6, y: y + balkenhoehe - 3, class: "wert" },
        v === null ? "–" : format(v)));
    });
  });
  ziel.replaceChildren(svg);
}

function zeitraumtext(a) {
  const von = MONATE[a.von - 1], bis = MONATE[a.bis - 1];
  return a.von === a.bis ? `${von} ${a.jahr}` : `${von}–${bis} ${a.jahr}`;
}

function abdeckung(ziel, staedte) {
  ziel.replaceChildren(...staedte.map((s) => {
    const karte = document.createElement("div");
    karte.className = `stadtkarte ${s.stadt}`;
    const h3 = document.createElement("h3");
    h3.textContent = s.name;
    const tabelle = document.createElement("table");
    const zeilen = [
      ["Zeitraum mit Daten", s.von ? `${monatsname(s.von)} – ${monatsname(s.bis)}` : "keine Daten"],
      ["Vollständige Monate", `${s.vollstaendig} / ${s.monate.length}`, s.vollstaendig === s.monate.length],
      ["Letzter Monat im Bestand", s.letzter_monat ? monatsname(s.letzter_monat) : "–"],
      ["Datenstatus", { vollstaendig: "Vollständig", unvollstaendig: "Teilweise", keine_daten: "Keine Daten" }[s.status],
        s.status === "vollstaendig"],
    ];
    for (const [etikett, wert, gut] of zeilen) {
      const tr = tabelle.insertRow();
      tr.insertCell().textContent = etikett;
      const td = tr.insertCell();
      td.textContent = wert;
      if (gut !== undefined) td.className = gut ? "ok" : "teil";
    }
    karte.append(h3, tabelle);
    return karte;
  }));
}

function zeichne() {
  const d = zustand.daten;
  if (!d) return;
  const k = d.kennzahlen;
  const staedte = d.verlauf.reihen.map((r) => ({ stadt: r.stadt, name: r.name }));
  document.getElementById("k-delikte").textContent = zahl.format(k.delikte);
  document.getElementById("k-faelle").textContent = zahl.format(k.faelle);
  const vj = document.getElementById("k-vorjahr");
  vj.className = k.vorjahr_prozent === null ? "" : k.vorjahr_prozent < 0 ? "runter" : "rauf";
  vj.textContent = k.vorjahr_prozent === null ? "nicht vergleichbar"
    : `${k.vorjahr_prozent < 0 ? "↓ −" : "↑ +"}${komma.format(Math.abs(k.vorjahr_prozent))} %`;
  vj.title = k.vorjahr_monate < k.monate
    ? `Über ${k.vorjahr_monate} von ${k.monate} Monaten, die in beiden Jahren vollständig vorliegen`
    : "Dieselben Monate im Vorjahr";
  document.getElementById("k-vorjahr-basis").textContent = k.vorjahr_monate < k.monate
    ? `über ${k.vorjahr_monate} vergleichbare Monate` : "";
  document.getElementById("k-monate").textContent = `${k.vollstaendige_monate} / ${k.monate}`;

  const zr = zeitraumtext(d.auswahl);
  linie(document.getElementById("d-verlauf"), d.verlauf);
  document.getElementById("t-raten").textContent = `Delikte je 1'000 Einwohner · ${zr}`;
  const e = d.raten.einwohner;
  document.getElementById("u-raten").textContent = "Bevölkerungsbasis: " + (Object.keys(e).length
    ? staedte.map((s) => `${s.name} ${zahl.format(e[s.stadt])}`).join(", ") + " (ACS)"
    : "keine einheitliche – Rate nicht definiert");
  balken(document.getElementById("d-raten"), d.raten.zeilen, staedte, (v) => komma.format(v),
    achsenzahl);
  const titel = { anzahl: "Registrierte Delikte", anteil: "Anteil an allen Delikten",
    rate: "Delikte je 1'000 Einwohner" }[d.kategorien.mass];
  document.getElementById("t-kategorien").textContent = `${titel} nach Kategorie · ${zr}`;
  const format = d.kategorien.mass === "anzahl" ? (v) => zahl.format(v)
    : d.kategorien.mass === "anteil" ? (v) => `${komma.format(v)} %` : (v) => komma.format(v);
  balken(document.getElementById("d-kategorien"), d.kategorien.zeilen, staedte, format,
    d.kategorien.mass === "anteil" ? (v) => `${achsenzahl(v)} %` : achsenzahl);
  abdeckung(document.getElementById("d-abdeckung"), d.abdeckung);
  document.querySelectorAll(".tafel").forEach((t) => {
    if (t.querySelector(".legende")) legende(t, staedte);
  });
}

async function lade() {
  const form = new FormData(document.getElementById("leiste"));
  form.set("mass", zustand.mass);
  const antwort = await fetch("/api/ueberblick?" + new URLSearchParams(form));
  // Ein 500 kommt als HTML; dann bleibt die Meldung allgemein, aber sichtbar.
  const daten = await antwort.json().catch(() => ({}));
  const fehler = document.getElementById("fehler");
  if (!antwort.ok) {
    fehler.textContent = daten.fehler || `Die Daten konnten nicht geladen werden (HTTP ${antwort.status}).`;
    fehler.hidden = false;
    return;
  }
  fehler.hidden = true;
  zustand.daten = daten;
  history.replaceState(null, "", "?" + new URLSearchParams(form));
  zeichne();
}

function optionen(select, eintraege, wert) {
  select.replaceChildren(...eintraege.map(([w, name]) => new Option(name, w, false, String(w) === String(wert))));
}

async function start() {
  for (const s of document.querySelectorAll("[data-symbol]")) {
    const svg = el("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
    svg.append(el("path", { d: SYMBOLE[s.dataset.symbol] }));
    s.append(svg);
  }
  const antwort = await fetch("/api/optionen");
  const o = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    const fehler = document.getElementById("fehler");
    fehler.textContent = o.fehler || `Der Datenstand ist nicht erreichbar (HTTP ${antwort.status}).`;
    fehler.hidden = false;
    return;
  }
  const url = new URLSearchParams(location.search);
  const wahl = (k) => url.get(k) ?? o.vorgabe[k];
  zustand.mass = wahl("mass");
  optionen(document.getElementById("stadt"), o.staedte.map((s) => [s.wert, s.name]), wahl("stadt"));
  optionen(document.getElementById("jahr"), o.jahre.map((j) => [j, String(j)]), wahl("jahr"));
  const monate = MONATE.map((m, i) => [i + 1, m]);
  optionen(document.getElementById("von"), monate, wahl("von"));
  optionen(document.getElementById("bis"), monate, wahl("bis"));
  optionen(document.getElementById("kategorie"), o.kategorien.map((k) => [k.wert, k.name]), wahl("kategorie"));
  document.querySelectorAll(".umschalter button").forEach((b) =>
    b.classList.toggle("an", b.dataset.mass === zustand.mass));

  const st = o.stand;
  const gebaut = st.gebaut ? new Date(st.gebaut).toLocaleString("de-CH") : "unbekannt";
  const stand = document.getElementById("stand");
  stand.replaceChildren("Datenstand ", Object.assign(document.createElement("b"), { textContent: gebaut }));
  document.getElementById("fuss-stand").textContent =
    `Release: ${st.release || "keines"} · Datenstand ${gebaut}`;

  document.getElementById("leiste").addEventListener("change", (ev) => {
    const von = document.getElementById("von"), bis = document.getElementById("bis");
    if (Number(von.value) > Number(bis.value)) {
      if (ev.target === von) bis.value = von.value; else von.value = bis.value;
    }
    lade();
  });
  document.querySelectorAll(".umschalter button").forEach((b) => b.addEventListener("click", () => {
    zustand.mass = b.dataset.mass;
    document.querySelectorAll(".umschalter button").forEach((x) => x.classList.toggle("an", x === b));
    lade();
  }));
  let warte;
  window.addEventListener("resize", () => { clearTimeout(warte); warte = setTimeout(zeichne, 150); });
  lade();
}

start();
