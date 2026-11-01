// Das Brett »Datenqualität«.
import { MONATE, el, komma, legende, starteBrett, zahl } from "./gemeinsam.js";

const ZUORDNUNG = {
  exact: { name: "Exakt (eindeutige Zuordnung)", farbe: "#17a38b" },
  fallback_90Z: { name: "Auffang 90Z (Übrige Straftaten)", farbe: "#8ec5f0" },
  ambiguous: { name: "Mehrdeutig", farbe: "#f2a33a" },
  unmapped: { name: "Ohne Zuordnung", farbe: "#9aa3ae" },
};
const STATUS = { ok: ["Bestanden", "ok"], warnung: ["Unter der Schwelle", "teil"],
  keine_daten: ["Keine Daten", "teil"] };

const prozent = (v) => (v === null ? "–" : `${komma.format(v)} %`);

function monatsraster(ziel, d) {
  const t = document.createElement("table");
  t.className = "raster-tabelle";
  const kopf = t.createTHead().insertRow();
  kopf.append(Object.assign(document.createElement("th"), { textContent: "Stadt" }));
  for (const m of d.monate) {
    const [j, mm] = m.split("-");
    kopf.append(Object.assign(document.createElement("th"), {
      textContent: d.monate.length > 9 ? MONATE[Number(mm) - 1] : `${MONATE[Number(mm) - 1]} ${j}` }));
  }
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
      punkt.title = `${s.name}, ${d.monate[i].slice(0, 7)}: `
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
        fill: info.farbe });
      rect.append(el("title", {}, `${s.name}, ${info.name}: ${prozent(s.zuordnung[z])}`));
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
  document.getElementById("k-monate").textContent = `${k.vollstaendige_monate} / ${k.monate}`;
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
  pruefungen(document.getElementById("d-pruefungen"), d);
  const konsole = document.getElementById("konsole");
  konsole.hidden = !d.konsole;
  if (d.konsole) konsole.href = d.konsole;
}

starteBrett({ api: "/api/datenqualitaet", zeichne });
