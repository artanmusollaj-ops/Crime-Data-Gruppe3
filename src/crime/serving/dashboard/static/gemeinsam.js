// Was alle Bretter teilen: Zahlformat, Leiste, Linien und Balken.
// Die Diagramme sind eigenes SVG statt einer Bibliothek - kein CDN, und die
// Content-Security-Policy bleibt bei 'self'. Einzige Ausnahme: Bilder von
// OpenStreetMap, die Hintergrundkacheln der Karten (karte.js).

const SVGNS = "http://www.w3.org/2000/svg";
// Zwei Staedte (FR-43): Eine dritte Stadt ohne Eintrag bekaeme keine Farbe,
// und SVG fuellt sie dann schwarz.
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

// Ein Datum wie in der Schweiz: 4.7.2024.
export function datum(iso) {
  const [j, m, t] = iso.split("-").map(Number);
  return `${t}.${m}.${j}`;
}

const WOCHENTAG = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
// »Do 4.7.2024«: Ein einzelner Tag nennt seinen Wochentag - im Vergleich mit
// dem Vorjahr faellt derselbe Tag auf einen anderen (Entscheid vom 23.11.2026).
export function tagtext(iso) {
  const [j, m, t] = iso.split("-").map(Number);
  return `${WOCHENTAG[new Date(Date.UTC(j, m - 1, t)).getUTCDay()]} ${datum(iso)}`;
}

// Ganze Monate eines Jahres heissen wie bisher »Mär–Mai 2024«; ein freier
// Zeitraum nennt seine Tage, ein einzelner Tag nur sich selbst.
export function zeitraumtext(a, jahr = a.jahr) {
  if (a.ganze_monate === false) {
    return a.tag_von === a.tag_bis ? tagtext(a.tag_von) : `${datum(a.tag_von)}–${datum(a.tag_bis)}`;
  }
  const von = MONATE[a.von - 1], bis = MONATE[a.bis - 1];
  return a.von === a.bis ? `${von} ${jahr}` : `${von}–${bis} ${jahr}`;
}

// Der Zeitraum ein Jahr frueher, fuer die Legende eines Vorjahresvergleichs:
// bei ganzen Monaten »Mär–Mai 2023«, sonst die Tage aus der Antwort.
export function vorjahrestext(a, vergleich) {
  if (a.ganze_monate !== false) return zeitraumtext(a, vergleich.vorjahr);
  return zeitraumtext({ ganze_monate: false, tag_von: vergleich.von, tag_bis: vergleich.bis });
}

// Eine Periode der Achse: ein Tag, eine Woche ab Montag oder ein Monat
// (serving.dashboard.zeitraum). ``kurz`` fuer die Achse, sonst fuer Tooltips.
export function periodentext(iso, koernung = "monat", kurz = false, mitJahr = true) {
  const [j, m, t] = iso.split("-").map(Number);
  if (koernung === "tag") return kurz ? `${t}.${m}.` : datum(iso);
  if (koernung === "woche") return kurz ? `${t}.${m}.` : `Woche ab ${datum(iso)}`;
  if (!kurz) return monatsname(iso);
  return mitJahr ? `${MONATE[m - 1]} ${String(j).slice(2)}` : MONATE[m - 1];
}

// »Monatliche Fallzahlen«, »Wöchentliche …«, »Tägliche …«.
export const JE_PERIODE = { tag: "Tägliche", woche: "Wöchentliche", monat: "Monatliche" };
export const PERIODEN = { tag: "Tage", woche: "Wochen", monat: "Monate" };

// Eine Rate je Jahr aus weniger als einem Jahr ist hochgerechnet - bei einem
// Tag 365-fach. Die Seite sagt es dann dazu (Entscheid vom 23.11.2026).
export function hochrechnung(tage) {
  const wenigste = Math.min(...Object.values(tage || {}).filter((t) => t > 0));
  if (!Number.isFinite(wenigste) || wenigste >= 365) return "";
  return wenigste === 1 ? "über 1 Tag hochgerechnet" : `über ${zahl.format(wenigste)} Tage hochgerechnet`;
}

const ISO_TAG = /^\d{4}-\d{2}-\d{2}$/;
const zwei = (n) => String(n).padStart(2, "0");
const monatsende = (j, m) => `${j}-${zwei(m)}-${zwei(new Date(Date.UTC(j, m, 0)).getUTCDate())}`;

// Welche Vorgabe den Zeitraum von-bis genau trifft, als Index - sonst "".
// Treffen zwei denselben Zeitraum, bleibt die gewaehlte stehen. Seit dem
// 27.11.2026 zeigt die Liste so die aktive Vorgabe, auch nach dem Neuladen,
// statt nach jeder Wahl auf »Vorgabe …« zurueckzuspringen.
export function passendeVorgabe(vorgaben, von, bis, gewaehlt = "") {
  const trifft = (i) => vorgaben[i] && vorgaben[i].von === von && vorgaben[i].bis === bis;
  if (gewaehlt !== "" && trifft(Number(gewaehlt))) return String(gewaehlt);
  const i = vorgaben.findIndex((v, j) => trifft(j));
  return i < 0 ? "" : String(i);
}

// Die erweiterte Zeitwahl: zwei Tage statt Monaten eines Jahres, dazu
// Vorgaben vom letzten Tag mit Daten aus (»Letzte 30 Tage«, »Sommer 2025«).
// Beide Wahlen schicken ``von`` und ``bis``: als Monate mit ``jahr`` oder als
// Daten ohne. Die jeweils andere ist gesperrt, und ein gesperrtes Feld
// schickt ein Formular nicht mit. So bleiben alte Links gueltig.
// Angeboten wird sie auf den Brettern, die Tage rechnen (``optionen.frei``),
// und auf jedem Brett, dessen Adresse schon Tage traegt - dort meldet der
// Server, was das Brett noch nicht kann, und »Monate« fuehrt zurueck.
function zeitwahl(o, brett, url) {
  const von = document.getElementById("von"), bis = document.getElementById("bis");
  const jahr = document.getElementById("jahr");
  if (!von || !bis || !jahr || !o.tage) return null;
  const tagModus = ISO_TAG.test(url.get("von") || "");
  if (!tagModus && !(o.frei || []).includes(brett)) return null;
  const monatsfeld = von.closest("label");
  const feld = (name, id, label) => {
    const f = Object.assign(document.createElement("input"),
      { type: "date", name, id, min: o.tage.erster, max: o.tage.letzter });
    f.setAttribute("aria-label", label);
    return f;
  };
  const tagVon = feld("von", "tag-von", "von Tag"), tagBis = feld("bis", "tag-bis", "bis Tag");
  const vorgabe = Object.assign(document.createElement("select"), { id: "vorgabe" });
  vorgabe.setAttribute("aria-label", "Schnellauswahl");
  vorgabe.append(new Option("Schnellauswahl …", ""), ...o.vorgaben.map((v, i) => new Option(v.name, i)));
  const tagfeld = document.createElement("label");
  tagfeld.className = "tagwahl";
  tagfeld.append("Zeitraum", tagVon, Object.assign(document.createElement("span"),
    { className: "bis", textContent: "–" }), tagBis, vorgabe);
  const knopf = Object.assign(document.createElement("button"),
    { type: "button", className: "zeitmodus" });
  monatsfeld.after(tagfeld, knopf);

  const setze = (tage) => {
    monatsfeld.hidden = tage;
    tagfeld.hidden = !tage;
    [von, bis, jahr].forEach((f) => { f.disabled = tage; });
    [tagVon, tagBis].forEach((f) => { f.disabled = !tage; });
    knopf.textContent = tage ? "Monate" : "Tage";
    knopf.title = tage ? "Zurück zu Monaten eines Jahres" : "Einen freien Zeitraum auf den Tag genau wählen";
  };
  if (tagModus) {
    tagVon.value = url.get("von");
    tagBis.value = url.get("bis") || url.get("von");
  }
  // Die Liste zeigt die Vorgabe, die den Zeitraum trifft; aendert jemand
  // ein Datum von Hand, steht sie wieder auf »Schnellauswahl …« (bis zum
  // 27.11.2026 hiess die Liste »Vorgabe …«).
  const zeigeVorgabe = () => {
    vorgabe.value = passendeVorgabe(o.vorgaben, tagVon.value, tagBis.value, vorgabe.value);
  };
  setze(tagModus);
  zeigeVorgabe();
  vorgabe.addEventListener("change", () => {
    const v = o.vorgaben[Number(vorgabe.value)];
    if (v) { tagVon.value = v.von; tagBis.value = v.bis; }
    zeigeVorgabe();
  });
  [tagVon, tagBis].forEach((f) => f.addEventListener("change", zeigeVorgabe));
  knopf.addEventListener("click", () => {
    if (tagfeld.hidden) {
      // Von den Monaten zu den Tagen: derselbe Zeitraum, jetzt als Daten.
      const j = Number(jahr.value);
      tagVon.value = `${j}-${zwei(von.value)}-01`;
      tagBis.value = monatsende(j, Number(bis.value));
      setze(true);
      zeigeVorgabe();
    } else {
      // Zurueck: die Monate des ersten Tages, bis Jahresende, wenn der
      // Zeitraum darueber hinausgeht.
      const [j1, m1] = tagVon.value.split("-").map(Number);
      const [j2, m2] = tagBis.value.split("-").map(Number);
      jahr.value = String(j1);
      von.value = String(m1);
      bis.value = String(j2 === j1 ? m2 : 12);
      setze(false);
    }
    document.getElementById("leiste").dispatchEvent(new Event("change"));
  });
  return { tagVon, tagBis };
}

// Eine lange Tabelle in einem Fenster ``.tabellenfenster``: Es zeigt
// SICHTBARE_ZEILEN Zeilen, der Rest scrollt darin, der Kopf haftet (CSS).
// Seit dem 28.11.2026, zuerst fuer die Zuordnungstabelle auf
// »Datenqualität«, dann fuer »Entfernte Einträge« auf »Quellbewegung«.
// Gemessen und nicht fest, weil eine lange Bezeichnung ihre Zeile umbricht;
// bei weniger Zeilen kein Fenster. Nach jedem Zeichnen aufrufen.
export const SICHTBARE_ZEILEN = 20;
const beobachtet = new WeakSet();

export function scrollfenster(tabelle) {
  const fenster = tabelle.closest(".tabellenfenster");
  if (!fenster) return;
  const messe = () => {
    const zeilen = tabelle.tBodies[0] ? tabelle.tBodies[0].rows : [];
    if (zeilen.length <= SICHTBARE_ZEILEN) { fenster.style.maxHeight = ""; return; }
    const unten = zeilen[SICHTBARE_ZEILEN - 1].getBoundingClientRect().bottom;
    fenster.style.maxHeight = `${Math.ceil(unten - tabelle.getBoundingClientRect().top)}px`;
  };
  fenster.scrollTop = 0;  // ein neuer Filter beginnt wieder oben
  messe();
  if (!beobachtet.has(fenster)) {
    // Eine andere Breite bricht andere Zeilen um.
    beobachtet.add(fenster);
    let warte;
    window.addEventListener("resize", () => { clearTimeout(warte); warte = setTimeout(messe, 150); });
  }
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
export function linie(ziel, monate, reihen, { basis = null, format = zahl.format, koernung = "monat" } = {}) {
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
  // Hoechstens zwoelf Beschriftungen; bei 92 Tagen jede achte. Ueber mehrere
  // Jahre traegt ein Monat sein Jahr, innerhalb eines Jahres ab sieben
  // Monaten nicht - dort steht es in der Leiste.
  const schritt = Math.ceil(n / 12);
  const jahre = new Set(monate.map((m) => m.slice(0, 4))).size;
  monate.forEach((m, i) => {
    if (i % schritt) return;
    svg.append(el("line", { x1: x(i), x2: x(i), y1: o, y2: h - u, class: "achse" }));
    const text = koernung !== "monat" || jahre > 1 ? periodentext(m, koernung, true, jahre > 1)
      : n > 6 ? MONATE[Number(m.split("-")[1]) - 1] : monatsname(m);
    svg.append(el("text", { x: x(i), y: h - 10, "text-anchor": "middle" }, text));
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
      // Viele Punkte werden klein, sonst verdecken sie die Linie.
      const r = n > 40 ? 2.5 : s.gestrichelt ? 3 : 4.5;
      const c = el("circle", { cx: x(i), cy: y(v), r,
        fill: teil ? "#fff" : s.farbe, stroke: s.farbe, "stroke-width": n > 40 ? 1.5 : 2 });
      const name = koernung === "monat" && jahre === 1 ? MONATE[Number(monate[i].split("-")[1]) - 1]
        : periodentext(monate[i], koernung);
      c.append(el("title", {}, `${s.name}, ${name}: ${format(v)}`
        + (teil ? (koernung === "monat" ? " (Teilmonat)" : " (nur zum Teil mit Daten)") : "")));
      svg.append(c);
    });
  }
  ziel.replaceChildren(svg);
}

// ``balkenhoehe`` und ``abstand`` (zwischen den Gruppen) nur, wo wenige Zeilen
// eine Tafel fuellen sollen, die so hoch ist wie ihre Nachbarin.
export function balken(ziel, zeilen, staedte, format, achse = format,
  { balkenhoehe = 14, abstand = 14 } = {}) {
  const werte = zeilen.flatMap((z) => staedte.map((s) => z.werte[s.stadt] ?? 0));
  if (!zeilen.length) return leer(ziel, "Keine Delikte in dieser Auswahl");
  const b = Math.max(ziel.clientWidth, 320), l = 170, r = 64, o = 6, u = 26;
  const luecke = 3, gruppe = staedte.length * (balkenhoehe + luecke) + abstand;
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
      // ``blass``: eine Zeile, die daneben steht und nicht vorn - etwa die Tatebene.
      const rect = el("rect", { x: l, y, width: Math.max(0, x(v ?? 0) - l), height: balkenhoehe,
        rx: 2, fill: FARBE[s.stadt], "fill-opacity": z.blass ? 0.4 : 1 });
      rect.append(el("title", {}, `${s.name}, ${z.name}: ${v === null ? "keine Rate" : format(v)}`));
      svg.append(rect);
      svg.append(el("text", { x: x(v ?? 0) + 6, y: y + balkenhoehe / 2 + 4, class: "wert" },
        v === null ? "–" : format(v)));
    });
  });
  ziel.replaceChildren(svg);
}

function optionen(select, eintraege, wert) {
  // Ein Brett ohne diese Wahl (»Quellbewegung« kennt weder Jahr noch Kategorie).
  if (!select) return;
  select.replaceChildren(...eintraege.map(([w, name]) => new Option(name, w, false, String(w) === String(wert))));
}

// Eine Mehrfachwahl in einer Aufklappliste: oben »Alle«, darunter je Eintrag
// ein Häkchen. Zu sehen ist die Zusammenfassung (»Alle«, »Chicago« oder
// »Raub, Diebstahl +2«); der volle Text steht im Tooltip. Ist nicht »Alle«
// gewaehlt, ist das Feld als aktiver Filter markiert. Die Wahl landet im
// versteckten Feld: »alle« oder die Liste mit dem Trenner, etwa
// »chicago,detroit« oder »Robbery|Arson«. Damit bleiben Formular, Adresse und
// Reiter wie bei einer einzelnen Wahl. Die Eintraege kommen aus
// /api/optionen. Ein Klick auf »Alle« setzt alle Häkchen oder nimmt alle weg -
// sonst muesste man fuer eine von vierzig Kategorien 39 einzeln entfernen.
// Leer ist aber keine Auswahl: Solange nichts gewaehlt ist, steht »Bitte
// waehlen« im Feld, und das Brett laedt nicht neu.
// Gebaut mit <details>, damit Tastatur und Vorleser es kennen.
function mehrfachwahl(gruppe, feld, eintraege, wert, trenner) {
  if (!gruppe || !feld) return;
  const roh = String(wert || "alle");
  const alleGewaehlt = ["alle", "beide"].includes(roh.toLowerCase());
  const gewaehlt = new Set(alleGewaehlt ? eintraege.map((e) => e.wert)
    : roh.split(trenner).map((w) => (trenner === "," ? w.toLowerCase() : w)));
  const box = (wertname, name, an) => {
    const l = document.createElement("label");
    l.className = "mehrfach-wahl";
    const c = Object.assign(document.createElement("input"), { type: "checkbox", checked: an });
    c.dataset.wert = wertname;
    l.append(c, name);
    return [l, c];
  };
  const [alleLabel, alle] = box("alle", "Alle", false);
  const einzeln = eintraege.map((e) => box(e.wert, e.name, gewaehlt.has(e.wert)));
  const klappe = document.createElement("details");
  klappe.className = "mehrfach-klappe";
  const kopf = document.createElement("summary");
  const liste = document.createElement("div");
  liste.className = "mehrfach-liste";
  liste.append(alleLabel, ...einzeln.map(([l]) => l));
  klappe.append(kopf, liste);
  gruppe.replaceChildren(gruppe.firstElementChild, klappe);
  // Ein Klick daneben schliesst die Liste, wie bei einem Auswahlfeld.
  document.addEventListener("click", (ev) => {
    if (klappe.open && !klappe.contains(ev.target)) klappe.open = false;
  });
  klappe.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { klappe.open = false; kopf.focus(); }
  });
  const boxen = einzeln.map(([, c]) => c);
  const namen = Object.fromEntries(eintraege.map((e) => [e.wert, e.name]));
  const setze = () => {
    const an = boxen.filter((c) => c.checked).map((c) => c.dataset.wert);
    alle.checked = an.length === boxen.length;
    feld.value = alle.checked ? "alle" : an.join(trenner);
    const liste = an.map((w) => namen[w]);
    kopf.textContent = alle.checked ? "Alle"
      : liste.length <= 2 ? liste.join(", ") : `${liste.slice(0, 2).join(", ")} +${liste.length - 2}`;
    kopf.title = alle.checked ? "Kein Filter" : liste.join("\n");
    klappe.classList.toggle("aktiv", !alle.checked);
  };
  // Zugeklappt ohne Häkchen: zurueck zur letzten gueltigen Wahl im Feld.
  klappe.addEventListener("toggle", () => {
    if (klappe.open || boxen.some((b) => b.checked)) return;
    const zuletzt = feld.value === "alle" ? null : new Set(feld.value.split(trenner));
    boxen.forEach((b) => { b.checked = !zuletzt || zuletzt.has(b.dataset.wert); });
    setze();
  });
  // Vor dem change der Leiste, die danach neu laedt: Das Ereignis steigt von
  // der Gruppe zum Formular auf, also ist das Feld dann schon gesetzt.
  gruppe.addEventListener("change", (ev) => {
    if (ev.target === alle) boxen.forEach((b) => { b.checked = alle.checked; });
    if (!boxen.some((b) => b.checked)) {
      // Noch nichts gewaehlt: Das Feld behaelt die letzte gueltige Wahl, und
      // die Leiste erfaehrt nichts davon - kein Neuladen mit leerer Auswahl.
      ev.stopPropagation();
      alle.checked = false;
      kopf.textContent = "Bitte wählen";
      kopf.title = "Mindestens ein Häkchen setzen";
      klappe.classList.add("aktiv");
      return;
    }
    setze();
  });
  setze();
}

function fehler(text) {
  const f = document.getElementById("fehler");
  f.textContent = text;
  f.hidden = !text;
}

// Startet ein Brett: fuellt Leiste, Kopf und Fuss, laedt bei jeder Aenderung
// von api neu und ruft zeichne(daten). Jeder .umschalter setzt seinen Parameter.
// Die Hoehe des oben haftenden Blocks (Kopf, Reiter, Filterleiste) als
// --fixiert-hoehe, damit ein Sprungziel nicht hinter ihm verschwindet. Die
// Leiste bricht je nach Breite um, deshalb gemessen und nicht fest.
function halteKopfHoehe() {
  const block = document.getElementById("fixiert");
  if (!block) return;
  const setze = () => document.documentElement.style.setProperty(
    "--fixiert-hoehe", `${block.getBoundingClientRect().height}px`);
  setze();
  if (typeof ResizeObserver === "function") new ResizeObserver(setze).observe(block);
}

export async function starteBrett({ api, zeichne }) {
  halteKopfHoehe();
  // Jeder Umschalter setzt den Parameter aus data-param (Vorgabe: mass). Seit
  // dem 25.11.2026 duerfen es mehrere sein (»Geografie«: Raum und Kennzahl).
  const schalter = [...document.querySelectorAll(".umschalter")];
  const param = (s) => s.dataset.param || "mass";
  const zustand = { werte: {}, daten: null };
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
  // Ohne Vorgabe gilt der erste Knopf des Schalters.
  for (const s of schalter) {
    zustand.werte[param(s)] = wahl(param(s)) ?? s.querySelector("button")?.dataset.wert;
  }
  mehrfachwahl(document.getElementById("staedte"), document.getElementById("stadt"), o.staedte, wahl("stadt"), ",");
  optionen(document.getElementById("jahr"), o.jahre.map((j) => [j, String(j)]), wahl("jahr"));
  const monate = MONATE.map((m, i) => [i + 1, m]);
  optionen(document.getElementById("von"), monate, wahl("von"));
  optionen(document.getElementById("bis"), monate, wahl("bis"));
  mehrfachwahl(document.getElementById("kategorien"), document.getElementById("kategorie"), o.kategorien, wahl("kategorie"), "|");
  const tage = zeitwahl(o, api.split("/").pop(), url);
  const markiere = () => schalter.forEach((s) => s.querySelectorAll("button").forEach((b) =>
    b.classList.toggle("an", b.dataset.wert === zustand.werte[param(s)])));
  markiere();

  const st = o.stand;
  const gebaut = st.gebaut ? new Date(st.gebaut).toLocaleString("de-CH") : "unbekannt";
  document.getElementById("stand").replaceChildren(
    "Datenstand ", Object.assign(document.createElement("b"), { textContent: gebaut }));
  document.getElementById("fuss-stand").textContent =
    `Release: ${st.release || "keines"} · Datenstand ${gebaut}`;

  async function lade() {
    const form = new FormData(document.getElementById("leiste"));
    for (const [k, v] of Object.entries(zustand.werte)) if (v !== undefined) form.set(k, v);
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
    if (von && bis && Number(von.value) > Number(bis.value)) {
      if (ev.target === von) bis.value = von.value; else von.value = bis.value;
    }
    // Daten in ISO-Form vergleichen sich als Text richtig.
    if (tage && tage.tagVon.value && tage.tagBis.value && tage.tagVon.value > tage.tagBis.value) {
      if (ev.target === tage.tagVon) tage.tagBis.value = tage.tagVon.value;
      else tage.tagVon.value = tage.tagBis.value;
    }
    // Ein Datumsfeld mitten in der Eingabe ist leer; dann noch nicht laden.
    if (tage && !tage.tagVon.disabled && !(tage.tagVon.value && tage.tagBis.value)) return;
    lade();
  });
  schalter.forEach((s) => s.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    zustand.werte[param(s)] = b.dataset.wert;
    markiere();
    lade();
  })));
  let warte;
  window.addEventListener("resize", () => {
    clearTimeout(warte);
    warte = setTimeout(() => zustand.daten && zeichne(zustand.daten), 150);
  });
  lade();
}
