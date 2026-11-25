// Das Brett »Geografie«: Rate je Tract, Rate je Polizeibezirk, Festnahmen je Bezirk.
import {
  FARBE, achsenzahl, el, hochrechnung, komma, leer, runde, starteBrett, zahl, zeitraumtext,
} from "./gemeinsam.js";
import { kartenflaeche, schraffur } from "./karte.js";

// Eine Farbreihe fuer beide Staedte: Dieselbe Farbe ist derselbe Wert. Die
// Festnahmequote bekommt eine eigene, damit sie nicht wie eine Rate aussieht.
const STUFEN = ["#dcebfa", "#a9cdf2", "#6aa6e4", "#2f7de1", "#0b3f8a"];
const STUFEN_FEST = ["#e3f4e8", "#b4e0c1", "#75c48f", "#2f9e5c", "#0f5e33"];
let karten = null;
let kartenBezirke = null;

// Was je Ansicht anders heisst.
const ANSICHT = {
  tract: {
    einheit: "Fälle je 1'000 Einwohner und Jahr",
    flaeche: "Census Tract", mehrzahl: "Tracts",
  },
  bezirk: {
    einheit: "Fälle je 1'000 Einwohner und Jahr",
    flaeche: "Polizeibezirk", mehrzahl: "Polizeibezirke",
  },
  festnahme: {
    einheit: "Anteil der Fälle mit Festnahme, in %",
    flaeche: "Polizeibezirk", mehrzahl: "Polizeibezirke",
  },
};

const stufen = (d) => (d.ansicht === "festnahme" ? STUFEN_FEST : STUFEN);
const wert = (d, v) => (d.ansicht === "festnahme" ? `${komma.format(v)} %` : komma.format(v));

function stufe(v, grenzen, reihe) {
  const i = grenzen.findIndex((g) => v <= g);
  return reihe[i === -1 ? grenzen.length : i];
}

function klassentext(grenzen, i) {
  if (i === 0) return `bis ${achsenzahl(grenzen[0])}`;
  if (i === grenzen.length) return `> ${achsenzahl(grenzen[i - 1])}`;
  return `${achsenzahl(grenzen[i - 1])} – ${achsenzahl(grenzen[i])}`;
}

function kurzname(d, name) {
  return d.ansicht === "tract" ? name.replace("Census Tract", "Tract") : name;
}

function tooltip(d, f, t) {
  const zeilen = [d.ansicht === "tract" ? `${f.name} (${f.geoid})` : f.name];
  if (!t) return zeilen;
  if (d.ansicht === "festnahme") {
    zeilen.push(`${zahl.format(t.faelle)} Fälle, davon ${zahl.format(t.festnahmen)} mit Festnahme`);
    if (t.anteil !== null) zeilen.push(`${komma.format(t.anteil)} % der ${zahl.format(t.bekannt)} Fälle mit bekanntem Stand`);
    if (t.geringe_basis) zeilen.push(`geringe Basis (unter ${zahl.format(d.mindestfaelle)} Fällen)`);
    return zeilen;
  }
  zeilen.push(t.einwohner ? `${zahl.format(t.einwohner)} Einwohner` : "keine Einwohner");
  zeilen.push(`${zahl.format(t.faelle)} Fälle` + (t.rate === null ? "" : ` · ${komma.format(t.rate)} je 1'000`));
  if (t.geringe_basis && t.einwohner) zeilen.push(`geringe Basis (unter ${zahl.format(d.geringe_basis)})`);
  return zeilen;
}

function karte(stadt, d) {
  const k = (d.ansicht === "tract" ? karten : kartenBezirke)[stadt.stadt];
  const a = ANSICHT[d.ansicht];
  const tafel = document.createElement("article");
  tafel.className = `tafel karte ${stadt.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = stadt.name;
  const inhalt = el("g");
  const nach = Object.fromEntries(stadt.tracts.map((t) => [t.geoid, t]));
  for (const f of k.tracts) {
    const t = nach[f.geoid];
    const fuellung = !t || t.geringe_basis || t.wert === null
      ? `url(#schraffur-${stadt.stadt})` : stufe(t.wert, d.klassen, stufen(d));
    const pfad = el("path", { d: f.d, fill: fuellung, class: d.ansicht === "tract" ? "tract" : "tract bezirk" });
    pfad.append(el("title", {}, tooltip(d, f, t).join("\n")));
    inhalt.append(pfad);
  }
  const ziel = kartenflaeche(k, { titel: `${stadt.name}: ${a.einheit} je ${a.flaeche}`,
    inhalt, defs: schraffur(`schraffur-${stadt.stadt}`) });
  const fuss = document.createElement("p");
  fuss.className = "unterzeile";
  fuss.textContent = `${stadt.tracts.length} ${a.mehrzahl} · ${stadt.geringe} mit geringer Basis schraffiert`
    + (d.ansicht === "festnahme" && stadt.anteil !== null
      ? ` · Stadt: ${komma.format(stadt.anteil)} %` : "");
  tafel.append(h2, ziel, fuss);
  return tafel;
}

function rangliste(ziel, stadt, d) {
  const h2 = document.createElement("h2");
  h2.textContent = `${d.ansicht === "festnahme" ? "Höchste Festnahmequoten" : "Höchste Raten"} – ${stadt.name}`;
  const box = document.createElement("div");
  box.className = "diagramm";
  ziel.replaceChildren(h2, box);
  if (!stadt.hoechste.length) return leer(box, `Keine ${ANSICHT[d.ansicht].mehrzahl} mit tragfähiger Basis`);
  const b = Math.max(box.clientWidth, 300), l = 130, r = 56, zeile = 24, u = 34;
  const h = stadt.hoechste.length * zeile + u;
  const max = runde(Math.max(...stadt.hoechste.map((t) => t.wert)));
  const x = (v) => l + ((b - l - r) * v) / max;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 4; k++) {
    const v = (max * k) / 4;
    svg.append(el("line", { x1: x(v), x2: x(v), y1: 0, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - u + 14, "text-anchor": "middle" }, achsenzahl(v)));
  }
  svg.append(el("text", { x: (l + b - r) / 2, y: h - 4, "text-anchor": "middle", class: "achsentitel" },
    ANSICHT[d.ansicht].einheit));
  stadt.hoechste.forEach((t, i) => {
    const y = i * zeile + 4;
    svg.append(el("text", { x: l - 8, y: y + 12, "text-anchor": "end" }, kurzname(d, t.name)));
    const rect = el("rect", { x: l, y, width: x(t.wert) - l, height: 16, rx: 2, fill: FARBE[stadt.stadt] });
    rect.append(el("title", {}, tooltip(d, { name: t.name, geoid: t.geoid }, t).join("\n")));
    svg.append(rect);
    svg.append(el("text", { x: x(t.wert) + 6, y: y + 12, class: "wert" }, wert(d, t.wert)));
  });
  box.replaceChildren(svg);
}

function hinweise(d) {
  const punkte = [];
  if (d.ansicht === "festnahme") {
    punkte.push(
      "Festnahme heisst: Chicago meldet eine Festnahme zum Fall (arrest); Detroit führt den Fall als "
        + "»Cleared by Arrest«. Detroits »Exceptionally Cleared« zählt nicht mit – Chicago kennt es nicht.",
      `Junge Fälle sind oft noch nicht geklärt. Der Stand wird nachgetragen, in Detroit stark: `
        + "2025 und 2026 liegt die Quote dort bei 5 bis 6 %, nach 9 bis 12 % in den Jahren davor.",
      ...d.staedte.filter((s) => s.jung).map((s) =>
        `${s.name}: Der Zeitraum endet weniger als ein Jahr vor dem letzten Tag mit Daten – `
        + "die Quote wird noch steigen und ist mit älteren Jahren nicht vergleichbar."),
      `Bezirke mit weniger als ${zahl.format(d.mindestfaelle)} Fällen mit bekanntem Stand sind schraffiert.`,
    );
  } else {
    punkte.push(d.ansicht === "tract"
      ? "Kleine Einwohnerzahlen lassen Raten stark schwanken; Tracts unter "
        + `${zahl.format(d.geringe_basis)} Einwohnern sind schraffiert und nicht in der Rangliste.`
      : "Einwohner je Polizeibezirk: die Tracts nach ihrem Flächenanteil am Bezirk verteilt. "
        + "Zusammen ergeben alle Bezirke die Einwohner der Stadt.",
    "Tatort ist nicht Wohnort: Innenstadt und Verkehrsknoten haben viele Taten und wenige Bewohner.");
  }
  if (d.ansicht !== "tract") {
    punkte.push("Chicagos District 31 fehlt: Er umfasst die Gemeinden Norridge und Harwood Heights, "
      + "die nicht zu Chicago gehören.");
  }
  punkte.push(...d.staedte.map((s) => {
    const v = s.verortung;
    const ohne = v.outside_city + v.no_tract + v.missing_coordinate;
    const alle = ohne + v.inside_city;
    return `${s.name}: ${zahl.format(ohne)} Fälle ohne Ort in der Stadt`
      + (alle ? ` (${komma.format((ohne * 100) / alle)} %)` : "")
      + ` – ${zahl.format(v.missing_coordinate)} ohne Koordinate, `
      + `${zahl.format(v.outside_city + v.no_tract)} ausserhalb. Sie fehlen auf der Karte.`;
  }), "Keine Aussage über individuelles Risiko.");
  return punkte;
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  const a = ANSICHT[d.ansicht];
  const kopf = d.ansicht === "festnahme"
    ? `${a.einheit} je ${a.flaeche} · ${zr}`
    : `${a.einheit} je ${a.flaeche} · ${zr}`
      + (hochrechnung({ z: d.auswahl.tage }) ? ` · ${hochrechnung({ z: d.auswahl.tage })}` : "")
      + (d.vintage ? ` · Einwohner ACS ${d.vintages.length > 1 ? d.vintages.join("/") : d.vintage}` : "");
  document.getElementById("u-geografie").textContent = kopf;
  document.getElementById("karten").replaceChildren(...d.staedte.map((s) => karte(s, d)));
  document.getElementById("karten").classList.toggle("einzeln", d.staedte.length === 1);

  document.getElementById("t-legende").textContent = `${a.einheit} · ${zr}`;
  const klassen = [...d.klassen.map((_, i) => i), d.klassen.length];
  document.getElementById("d-legende").replaceChildren(...klassen.map((i) => {
    const k = document.createElement("span");
    const farbe = document.createElement("i");
    farbe.style.background = stufen(d)[i];
    k.append(farbe, klassentext(d.klassen, i));
    return k;
  }));
  document.getElementById("t-geringe").textContent = d.ansicht === "festnahme"
    ? `Geringe Basis (unter ${zahl.format(d.mindestfaelle)} Fällen mit bekanntem Stand)`
    : `Geringe Basis (unter ${zahl.format(d.geringe_basis)} Einwohner)`;

  // Zwei Staedte (FR-43): fest, wie die Behaelter rang-chicago und
  // rang-detroit in geografie.html. Fuer eine dritte Stadt erschiene keine
  // Rangliste.
  for (const s of ["chicago", "detroit"]) {
    const ziel = document.getElementById(`rang-${s}`);
    const stadt = d.staedte.find((x) => x.stadt === s);
    ziel.hidden = !stadt;
    if (stadt) rangliste(ziel, stadt, d);
  }

  document.getElementById("d-hinweise").replaceChildren(...hinweise(d).map((p) => {
    const li = document.createElement("li");
    li.textContent = p;
    return li;
  }));
}

async function start() {
  const [tracts, bezirke] = await Promise.all([fetch("/api/karten"), fetch("/api/karten?raum=bezirk")]);
  if (tracts.ok) karten = await tracts.json();
  if (bezirke.ok) kartenBezirke = await bezirke.json();
  starteBrett({ api: "/api/geografie", zeichne });
}

start();
