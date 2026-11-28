// Das Brett »Datenqualität«.
import { MONATE, PERIODEN, el, komma, legende, periodentext, scrollfenster, starteBrett, zahl }
  from "./gemeinsam.js";

const ZUORDNUNG = {
  exact: { name: "Exakt (eindeutige Zuordnung)", kurz: "Exakt", farbe: "#17a38b" },
  fallback_90Z: { name: "Auffang 90Z (Übrige Straftaten)", kurz: "Auffang 90Z", farbe: "#8ec5f0" },
  ambiguous: { name: "Mehrdeutig", kurz: "Mehrdeutig", farbe: "#f2a33a" },
  unmapped: { name: "Ohne Zuordnung", kurz: "Ohne Zuordnung", farbe: "#9aa3ae" },
};
const STATUS = { ok: ["Bestanden", "ok"], warnung: ["Unter der Schwelle", "teil"],
  keine_daten: ["Keine Daten", "teil"] };

const prozent = (v) => (v === null ? "–" : `${komma.format(v)} %`);

// Je Stadt und Periode ein Feld. Ueber viele Perioden - 92 Tage, 104 Wochen,
// sechs Jahre in Monaten - werden die Felder schmal, und nur jede n-te
// Spalte traegt eine Beschriftung.
function monatsraster(ziel, d) {
  const k = d.achse.koernung, n = d.monate.length, schritt = Math.ceil(n / 12);
  const jahre = new Set(d.monate.map((m) => m.slice(0, 4))).size;
  const t = document.createElement("table");
  t.className = n > 24 ? "raster-tabelle dicht" : "raster-tabelle";
  const kopf = t.createTHead().insertRow();
  kopf.append(Object.assign(document.createElement("th"), { textContent: "Stadt" }));
  d.monate.forEach((m, i) => {
    const [j, mm] = m.split("-");
    const text = i % schritt ? ""
      : k !== "monat" || jahre > 1 ? periodentext(m, k, true, jahre > 1)
      : n > 9 ? MONATE[Number(mm) - 1] : `${MONATE[Number(mm) - 1]} ${j}`;
    kopf.append(Object.assign(document.createElement("th"), { textContent: text }));
  });
  const rumpf = t.createTBody();
  for (const s of d.staedte) {
    const tr = rumpf.insertRow();
    const name = tr.insertCell();
    name.textContent = s.name;
    name.className = `stadtname ${s.stadt}`;
    s.monate.forEach((z, i) => {
      const td = tr.insertCell();
      const punkt = document.createElement("i");
      punkt.className = `s-${z}`;
      punkt.title = `${s.name}, ${k === "monat" ? d.monate[i].slice(0, 7) : periodentext(d.monate[i], k)}: `
        + { voll: "vollständig", teil: "teilweise vorhanden", fehlt: "fehlt",
          spaeter: "noch nicht erschienen" }[z];
      td.append(punkt);
    });
  }
  ziel.replaceChildren(t);
}

function zuordnung(ziel, staedte) {
  const b = Math.max(ziel.clientWidth, 320), l = 80, r = 24, hoehe = 40, luecke = 22, u = 26;
  const h = staedte.length * (hoehe + luecke) + u;
  const x = (v) => l + ((b - l - r) * v) / 100;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 5; k++) {
    svg.append(el("line", { x1: x(k * 20), x2: x(k * 20), y1: 0, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(k * 20), y: h - 8, "text-anchor": "middle" }, `${k * 20} %`));
  }
  staedte.forEach((s, i) => {
    const y = i * (hoehe + luecke) + luecke / 2;
    svg.append(el("text", { x: l - 10, y: y + hoehe / 2 + 5, "text-anchor": "end", class: "stark" }, s.name));
    let links = 0;
    for (const [z, info] of Object.entries(ZUORDNUNG)) {
      const v = s.zuordnung[z] ?? 0;
      const rect = el("rect", { x: x(links), y, width: Math.max(0, x(links + v) - x(links)), height: hoehe,
        fill: info.farbe, class: "klickbar" });
      rect.append(el("title", {}, `${s.name}, ${info.name}: ${prozent(s.zuordnung[z])} · Klick zeigt die Quellcodes`));
      // Der Klick setzt Stadt und Status der Detailtafel und springt dorthin.
      rect.addEventListener("click", () => {
        Object.assign(detailwahl, { status: z, stadt: s.stadt, stadtname: s.name });
        if (letzte) detail(letzte);
        document.getElementById("zuordnung-detail").scrollIntoView({ behavior: "smooth", block: "start" });
      });
      svg.append(rect);
      if (v >= 6) {
        svg.append(el("text", { x: x(links + v / 2), y: y + hoehe / 2 + 5, "text-anchor": "middle",
          class: z === "exact" ? "im-balken" : "im-balken dunkel" }, prozent(v)));
      }
      links += v;
    }
  });
  ziel.replaceChildren(svg);
}

// Die Detailtafel. Ihr Filter lebt hier und nicht in der Leiste: Er gilt nur
// fuer diese Tabelle, und ein Wechsel braucht keinen Rundweg zum Server.
const detailwahl = { status: "alle", stadt: null, stadtname: "", suche: "" };
let letzte = null;

function detail(d) {
  letzte = d;
  const zeilen = d.zuordnung_detail;
  const suche = detailwahl.suche.trim().toLowerCase();
  const passt = (z) => (!detailwahl.stadt || z.stadt === detailwahl.stadt)
    && (!suche || [z.quellcode, z.quelltext, z.nibrs_code, z.nibrs_text, z.kategorie]
      .some((t) => (t || "").toLowerCase().includes(suche)));
  const vorab = zeilen.filter(passt);
  // Die Knoepfe zaehlen Quellcodes je Status in der aktuellen Auswahl.
  const knoepfe = document.getElementById("f-status");
  const zaehler = { alle: vorab.length };
  for (const z of vorab) zaehler[z.status] = (zaehler[z.status] || 0) + 1;
  knoepfe.replaceChildren(...[["alle", "Alle"], ["exact", "Exakt"], ["fallback_90Z", "Auffang 90Z"],
    ["ambiguous", "Mehrdeutig"], ["unmapped", "Ohne Zuordnung"]].map(([w, name]) => {
    const b = Object.assign(document.createElement("button"), { type: "button" });
    b.append(name, Object.assign(document.createElement("small"), { textContent: ` ${zahl.format(zaehler[w] || 0)}` }));
    b.classList.toggle("an", detailwahl.status === w);
    b.addEventListener("click", () => { Object.assign(detailwahl, { status: w }); detail(d); });
    return b;
  }));
  const chip = document.getElementById("f-stadt");
  chip.hidden = !detailwahl.stadt;
  chip.textContent = `nur ${detailwahl.stadtname} ✕`;
  const gezeigt = vorab.filter((z) => detailwahl.status === "alle" || z.status === detailwahl.status);
  document.getElementById("f-treffer").textContent =
    `${zahl.format(gezeigt.length)} ${gezeigt.length === 1 ? "Quellcode" : "Quellcodes"}`;

  const t = document.getElementById("d-zuordnung-detail");
  t.replaceChildren();
  const kopf = t.createTHead().insertRow();
  for (const s of ["Stadt", "Quellcode", "Quellbezeichnung", "NIBRS", "NIBRS-Bezeichnung", "Kategorie",
    "Zuordnung", "Taten", "Anteil"]) {
    kopf.append(Object.assign(document.createElement("th"), { textContent: s }));
  }
  const rumpf = t.createTBody();
  for (const z of gezeigt) {
    const tr = rumpf.insertRow();
    const stadt = tr.insertCell();
    stadt.textContent = z.name;
    stadt.className = `stadtname ${z.stadt}`;
    tr.insertCell().textContent = z.quellcode ?? "–";
    tr.insertCell().textContent = z.quelltext ?? "–";
    tr.insertCell().textContent = z.nibrs_code ?? "–";
    tr.insertCell().textContent = z.nibrs_text ?? "–";
    tr.insertCell().textContent = z.kategorie;
    const marke = document.createElement("span");
    marke.className = "zuordnungsmarke";
    marke.style.setProperty("--farbe", ZUORDNUNG[z.status].farbe);
    marke.textContent = ZUORDNUNG[z.status].kurz;
    tr.insertCell().append(marke);
    Object.assign(tr.insertCell(), { textContent: zahl.format(z.delikte), className: "zahl" });
    Object.assign(tr.insertCell(), { textContent: prozent(z.anteil), className: "zahl" });
  }
  if (!gezeigt.length) {
    const td = rumpf.insertRow().insertCell();
    td.colSpan = 9;
    td.textContent = "Kein Quellcode in dieser Auswahl";
  }
  scrollfenster(t);
}

function detailsteuerung() {
  const suche = document.getElementById("f-suche");
  suche.addEventListener("input", () => { detailwahl.suche = suche.value; if (letzte) detail(letzte); });
  document.getElementById("f-stadt").addEventListener("click", () => {
    Object.assign(detailwahl, { stadt: null, stadtname: "" });
    if (letzte) detail(letzte);
  });
}

function status(zelle, schluessel) {
  const [text, klasse] = STATUS[schluessel];
  zelle.textContent = text;
  zelle.className = klasse;
}

function pruefungen(ziel, d) {
  ziel.replaceChildren();
  const kopf = ziel.createTHead().insertRow();
  for (const s of ["Aspekt", "Wert", "Schwelle", "Status", "Details"]) {
    kopf.append(Object.assign(document.createElement("th"), { textContent: s }));
  }
  const rumpf = ziel.createTBody();
  const je = (feld) => d.staedte.map((s) => `${s.name} ${prozent(s[feld[0]][feld[1]])}`).join(", ");
  const details = {
    "NIBRS-Zuordnung exakt": `${je(["zuordnung", "exact"])}. Der Rest ist Auffang 90Z oder mehrdeutig.`,
    "Ohne NIBRS-Zuordnung": `${je(["zuordnung", "unmapped"])}. Sie zählen mit, haben aber keine Kategorie.`,
    "Verortung im Stadtgebiet": `${je(["verortung", "inside_city"])}. Ausserhalb oder ohne Koordinate `
      + "fehlt auf der Karte, nicht in den Zahlen.",
    "Eindeutige Delikt-ID": "Jede offense_id kommt im gewählten Zeitraum genau einmal vor.",
  };
  for (const p of d.pruefungen) {
    const tr = rumpf.insertRow();
    tr.insertCell().textContent = p.aspekt;
    const wert = tr.insertCell();
    wert.textContent = p.aspekt === "Eindeutige Delikt-ID"
      ? `${zahl.format(p.wert)} doppelt` : prozent(p.wert);
    wert.className = "zahl";
    tr.insertCell().textContent = p.schwelle;
    status(tr.insertCell(), p.status);
    tr.insertCell().textContent = p.aspekt === "Eindeutige Delikt-ID" && p.wert
      ? `${zahl.format(p.wert)} offense_id kommen mehrfach vor.` : details[p.aspekt];
  }
  const k = d.kennzahlen, r = d.referenz;
  const zusatz = [
    ["Ortszeit eindeutig", `${zahl.format(k.ortszeit_mehrdeutig)} mehrdeutig`, "Hinweis", "ok",
      "Taten in der doppelten Stunde der Zeitumstellung im Herbst; sie zählen, ihre Stunde ist unsicher."],
    ["Referenzdaten", r.acs_vintage ? `ACS ${r.acs_vintage}` : "–", "ein ACS-Vintage je Jahr",
      r.acs_vintage ? "ok" : "warnung",
      `${r.kategorien} NIBRS-Kategorien im Bestand, Umrisse für ${zahl.format(r.tracts.chicago)} Tracts `
      + `in Chicago und ${zahl.format(r.tracts.detroit)} in Detroit`
      + (r.acs_vintage ? "." : `; Vintages im Jahr: ${r.acs_vintages.join(", ") || "keines"}.`)],
    ["Aktives Release", r.release || "keines", "AKTUELL.json", r.release ? "ok" : "warnung",
      r.release ? `Release ${r.release} ist aktiv.` : "Kein Release ist als aktuell markiert."],
  ];
  for (const [aspekt, wert, schwelle, st, text] of zusatz) {
    const tr = rumpf.insertRow();
    tr.insertCell().textContent = aspekt;
    tr.insertCell().textContent = wert;
    tr.insertCell().textContent = schwelle;
    status(tr.insertCell(), st);
    if (aspekt === "Ortszeit eindeutig") tr.cells[3].textContent = "Hinweis";
    tr.insertCell().textContent = text;
  }
}

function zeichne(d) {
  const k = d.kennzahlen;
  const kachel = document.getElementById("k-monate");
  kachel.previousElementSibling.textContent = `Vollständige ${PERIODEN[d.achse.koernung]}`;
  kachel.textContent = `${k.vollstaendige_monate} / ${k.monate}`;
  const raster = document.getElementById("d-monate").previousElementSibling;
  raster.textContent = `${{ tag: "Tages", woche: "Wochen", monat: "Monats" }[d.achse.koernung]}`
    + "abdeckung nach Stadt";
  document.getElementById("k-unmapped").textContent = prozent(k.ohne_zuordnung);
  const unmapped = d.pruefungen.find((p) => p.aspekt === "Ohne NIBRS-Zuordnung");
  document.getElementById("k-unmapped-text").textContent = `Publish-Gate: ${unmapped.schwelle}`;
  document.getElementById("k-koordinate").textContent = prozent(k.ohne_koordinate);
  const doppelt = document.getElementById("k-doppelt");
  doppelt.textContent = k.doppelte_ids ? `${zahl.format(k.doppelte_ids)} doppelt` : "Bestanden";
  doppelt.className = k.doppelte_ids ? "rauf" : "gut";
  document.getElementById("k-doppelt-text").textContent =
    `${zahl.format(k.delikte)} Taten im gewählten Zeitraum geprüft`;
  monatsraster(document.getElementById("d-monate"), d);
  zuordnung(document.getElementById("d-zuordnung"), d.staedte);
  const leg = document.getElementById("l-zuordnung");
  legende(leg, Object.values(ZUORDNUNG).map((z) => ({ name: z.name, klasse: "rang" })));
  [...leg.children].forEach((span, i) => span.style.setProperty("--farbe", Object.values(ZUORDNUNG)[i].farbe));
  detail(d);
  pruefungen(document.getElementById("d-pruefungen"), d);
  const konsole = document.getElementById("konsole");
  konsole.hidden = !d.konsole;
  if (d.konsole) konsole.href = d.konsole;
}

detailsteuerung();
starteBrett({ api: "/api/datenqualitaet", zeichne });
