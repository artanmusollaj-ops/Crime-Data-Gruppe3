// Was alle Bretter teilen: Zahlformat, Leiste, Linien und Balken.
// Die Diagramme sind eigenes SVG statt einer Bibliothek - kein CDN, und die
// Content-Security-Policy bleibt bei 'self'.

const SVGNS = "http://www.w3.org/2000/svg";
export const FARBE = { chicago: "#17a38b", detroit: "#2f7de1" };
export const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
// Wie in den Dokumenten: 2'661'953 und 94,5 - Hochkomma fuer Tausender,
// Komma fuer Dezimalen. de-CH allein schreibt 94.5.
const ganz = new Intl.NumberFormat("de-CH", { maximumFractionDigits: 0 });
export const zahl = { format: (v) => ganz.format(v).replace(/[’‘]/g, "'") };
export const komma = { format: (v) => v.toFixed(1).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, "'") };
// Ganze Schritte ohne Dezimalen, halbe mit: 0, 0,5, 1, 1,5 statt 0, 1, 1, 2.
export const achsenzahl = (v) => (Number.isInteger(v) ? zahl.format(v) : komma.format(v));

const SYMBOLE = {
  dokument: "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h6 M10 16h6",
  ordner: "M3 7h6l2 2h10v10H3z M3 11h18",
  balken: "M5 20V12 M10 20V6 M15 20v-9 M20 20V9",
  kalender: "M4 6h16v14H4z M4 10h16 M8 3v5 M16 3v5 M8 14h2 M12 14h2 M16 14h0 M8 17h2",
  uhr: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 7v5l3 2",
  teilmonat: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 7v6 M12 16v1",
  datenbank: "M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3z M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6 M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3",
  ort: "M12 21s-6-5.5-6-11a6 6 0 1 1 12 0c0 5.5-6 11-6 11z M12 7.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5",
  haken: "M5 12.5l4.5 4.5L19 7.5",
};

export function el(name, attrs = {}, text) {
  const e = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}

export function monatsname(iso) {
  const [j, m] = iso.split("-");
  return MONATE[Number(m) - 1] + " " + j;
}

export function zeitraumtext(a, jahr = a.jahr) {
  const von = MONATE[a.von - 1], bis = MONATE[a.bis - 1];
  return a.von === a.bis ? `${von} ${jahr}` : `${von}–${bis} ${jahr}`;
}

// Die Achse endet bei vier glatten Schritten: 4 x 5'000, nicht 4 x 4'687,5.
// Die Stufen liegen eng genug, dass die Linie mehr als die halbe Hoehe nutzt.
export function runde(max) {
  if (max <= 0) return 4;
  const schritt = max / 4, p = Math.pow(10, Math.floor(Math.log10(schritt)));
  for (const f of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10]) if (f * p >= schritt) return 4 * f * p;
  return 40 * p;
}

export function leer(ziel, text) {
  const svg = el("svg", { viewBox: "0 0 600 240" });
  svg.append(el("text", { x: 300, y: 120, "text-anchor": "middle", class: "leer" }, text));
  ziel.replaceChildren(svg);
}

// Eintraege: {name, klasse} - die Klasse setzt Farbe und Strich im CSS.
export function legende(ziel, eintraege) {
  ziel.replaceChildren(...eintraege.map((e) => {
    const span = document.createElement("span");
    span.className = e.klasse;
    span.textContent = e.name;
    return span;
  }));
}

// Reihen: {name, farbe, werte, status?, gestrichelt?}. Ein Wert null ist eine
// Luecke, ein Status "teil" ein hohler Punkt. Mit basis wird die Achse um den
// Bereich der Werte gelegt statt bei null zu beginnen, und die Basis als
// gestrichelte Linie gezogen.
export function linie(ziel, monate, reihen, { basis = null, format = zahl.format } = {}) {
  const b = Math.max(ziel.clientWidth, 320), h = 260, l = 56, r = 36, o = 16, u = 32;
  const alle = reihen.flatMap((s) => s.werte.filter((v) => v !== null));
  if (!alle.length) return leer(ziel, "Keine Daten in dieser Auswahl");
  let unten = 0, oben = runde(Math.max(1, ...alle));
  if (basis !== null) {
    const weite = Math.max(...alle.map((v) => Math.abs(v - basis)), 1);
    const schritt = runde(weite * 2) / 4;
    unten = Math.floor((basis - weite) / schritt) * schritt;
    oben = Math.ceil((basis + weite) / schritt) * schritt;
  }
  const n = monate.length;
  const x = (i) => l + (n === 1 ? (b - l - r) / 2 : (i * (b - l - r)) / (n - 1));
  const y = (v) => o + (h - o - u) * (1 - (v - unten) / (oben - unten));
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 4; k++) {
    const v = unten + ((oben - unten) * k) / 4;
    svg.append(el("line", { x1: l, x2: b - r, y1: y(v), y2: y(v), class: "achse" }));
    svg.append(el("text", { x: l - 8, y: y(v) + 4, "text-anchor": "end" }, achsenzahl(v)));
  }
  monate.forEach((m, i) => {
    svg.append(el("line", { x1: x(i), x2: x(i), y1: o, y2: h - u, class: "achse" }));
    // Ab sieben Monaten nur der Monat; das Jahr steht in der Leiste.
    svg.append(el("text", { x: x(i), y: h - 10, "text-anchor": "middle" },
      n > 6 ? MONATE[Number(m.split("-")[1]) - 1] : monatsname(m)));
  });
  if (basis !== null) {
    svg.append(el("line", { x1: l, x2: b - r, y1: y(basis), y2: y(basis), class: "basis" }));
  }
  for (const s of reihen) {
    // Ein Monat ohne Daten unterbricht die Linie, statt auf null zu fallen.
    let strecke = [];
    const ziehe = () => {
      if (strecke.length > 1) svg.append(el("polyline", { points: strecke.join(" "), fill: "none",
        stroke: s.farbe, "stroke-width": s.gestrichelt ? 2 : 2.5,
        "stroke-dasharray": s.gestrichelt ? "2 5" : "none", "stroke-linecap": "round" }));
      strecke = [];
    };
    s.werte.forEach((v, i) => (v === null ? ziehe() : strecke.push(`${x(i)},${y(v)}`)));
    ziehe();
    s.werte.forEach((v, i) => {
      if (v === null) return;
      // Ein Teilmonat ist hohl: Sein Wert ist kein Monatswert.
      const teil = s.status && s.status[i] === "teil";
      const c = el("circle", { cx: x(i), cy: y(v), r: s.gestrichelt ? 3 : 4.5,
        fill: teil ? "#fff" : s.farbe, stroke: s.farbe, "stroke-width": 2 });
      c.append(el("title", {}, `${s.name}, ${MONATE[Number(monate[i].split("-")[1]) - 1]}: ${format(v)}`
        + (teil ? " (Teilmonat)" : "")));
      svg.append(c);
    });
  }
  ziel.replaceChildren(svg);
}

export function balken(ziel, zeilen, staedte, format, achse = format) {
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

function optionen(select, eintraege, wert) {
  select.replaceChildren(...eintraege.map(([w, name]) => new Option(name, w, false, String(w) === String(wert))));
}

function fehler(text) {
  const f = document.getElementById("fehler");
  f.textContent = text;
  f.hidden = !text;
}

// Startet ein Brett: fuellt Leiste, Kopf und Fuss, laedt bei jeder Aenderung
// von api neu und ruft zeichne(daten). Ein .umschalter setzt seinen Parameter.
export async function starteBrett({ api, zeichne }) {
  // Der Umschalter setzt den Parameter aus data-param (Vorgabe: mass).
  const schalter = document.querySelector(".umschalter");
  const param = schalter ? schalter.dataset.param || "mass" : null;
  const zustand = { wert: null, daten: null };
  for (const s of document.querySelectorAll("[data-symbol]")) {
    const svg = el("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
    svg.append(el("path", { d: SYMBOLE[s.dataset.symbol] }));
    s.append(svg);
  }
  const antwort = await fetch("/api/optionen");
  const o = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    return fehler(o.fehler || `Der Datenstand ist nicht erreichbar (HTTP ${antwort.status}).`);
  }
  const url = new URLSearchParams(location.search);
  const wahl = (k) => url.get(k) ?? o.vorgabe[k];
  if (param) zustand.wert = wahl(param);
  optionen(document.getElementById("stadt"), o.staedte.map((s) => [s.wert, s.name]), wahl("stadt"));
  optionen(document.getElementById("jahr"), o.jahre.map((j) => [j, String(j)]), wahl("jahr"));
  const monate = MONATE.map((m, i) => [i + 1, m]);
  optionen(document.getElementById("von"), monate, wahl("von"));
  optionen(document.getElementById("bis"), monate, wahl("bis"));
  optionen(document.getElementById("kategorie"), o.kategorien.map((k) => [k.wert, k.name]), wahl("kategorie"));
  const knoepfe = document.querySelectorAll(".umschalter button");
  knoepfe.forEach((b) => b.classList.toggle("an", b.dataset.wert === zustand.wert));

  const st = o.stand;
  const gebaut = st.gebaut ? new Date(st.gebaut).toLocaleString("de-CH") : "unbekannt";
  document.getElementById("stand").replaceChildren(
    "Datenstand ", Object.assign(document.createElement("b"), { textContent: gebaut }));
  document.getElementById("fuss-stand").textContent =
    `Release: ${st.release || "keines"} · Datenstand ${gebaut}`;

  async function lade() {
    const form = new FormData(document.getElementById("leiste"));
    if (param) form.set(param, zustand.wert);
    const suche = "?" + new URLSearchParams(form);
    const antwort = await fetch(api + suche);
    // Ein 500 kommt als HTML; dann bleibt die Meldung allgemein, aber sichtbar.
    const daten = await antwort.json().catch(() => ({}));
    if (!antwort.ok) {
      return fehler(daten.fehler || `Die Daten konnten nicht geladen werden (HTTP ${antwort.status}).`);
    }
    fehler("");
    zustand.daten = daten;
    history.replaceState(null, "", suche);
    // Die Reiter nehmen die Auswahl mit auf das naechste Brett.
    document.querySelectorAll(".reiter a").forEach((a) => {
      a.href = a.getAttribute("href").split("?")[0] + suche;
    });
    zeichne(daten);
  }

  document.getElementById("leiste").addEventListener("change", (ev) => {
    const von = document.getElementById("von"), bis = document.getElementById("bis");
    if (Number(von.value) > Number(bis.value)) {
      if (ev.target === von) bis.value = von.value; else von.value = bis.value;
    }
    lade();
  });
  knoepfe.forEach((b) => b.addEventListener("click", () => {
    zustand.wert = b.dataset.wert;
    knoepfe.forEach((x) => x.classList.toggle("an", x === b));
    lade();
  }));
  let warte;
  window.addEventListener("resize", () => {
    clearTimeout(warte);
    warte = setTimeout(() => zustand.daten && zeichne(zustand.daten), 150);
  });
  lade();
}
