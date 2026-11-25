// Das Brett »Geografie«: ein Raum (Tract, Polizeibezirk, Stadtteil, Sechseck) und eine
// Kennzahl (Rate, geglaettet, Veraenderung, Deliktprofil, Nacht, Festnahmen).
import {
  FARBE, achsenzahl, el, hochrechnung, komma, leer, runde, starteBrett, zahl, zeitraumtext,
} from "./gemeinsam.js";
import { kartenflaeche, schraffur } from "./karte.js";

// Je Kennzahl eine Farbreihe; Veraenderung und Profil laufen um einen
// neutralen Wert und sind deshalb zweiseitig (blau weniger, rot mehr).
const REIHE = {
  rate: ["#dcebfa", "#a9cdf2", "#6aa6e4", "#2f7de1", "#0b3f8a"],
  festnahme: ["#e3f4e8", "#b4e0c1", "#75c48f", "#2f9e5c", "#0f5e33"],
  nacht: ["#ece9f7", "#c9c1ea", "#9d8fd6", "#6c58bd", "#3b2a8a"],
  zweiseitig: ["#2f7de1", "#a9cdf2", "#e6e3dc", "#f4a99b", "#d6452f"],
};
const reihe = (d) => ({ rate: REIHE.rate, geglaettet: REIHE.rate, festnahme: REIHE.festnahme,
  nacht: REIHE.nacht }[d.kennzahl] || REIHE.zweiseitig);

const RAUM = {
  tract: { flaeche: "Census Tract", mehrzahl: "Tracts" },
  bezirk: { flaeche: "Polizeibezirk", mehrzahl: "Polizeibezirke" },
  stadtteil: { flaeche: "Stadtteil", mehrzahl: "Stadtteile" },
  sechseck: { flaeche: "Sechseck (500 m Kante)", mehrzahl: "Sechsecke" },
};

function einheit(d) {
  if (d.kennzahl === "rate" && d.raum === "sechseck") return "Fälle je km² und Jahr";
  return {
    rate: "Fälle je 1'000 Einwohner und Jahr",
    geglaettet: "Fälle je 1'000 Einwohner und Jahr, geglättet",
    veraenderung: "Veränderung der Fälle zum Vorjahr, in %",
    profil: "Anteil der gewählten Kategorien, relativ zur Stadt (1 = wie die Stadt)",
    nacht: "Anteil der Fälle bei Dunkelheit, in %",
    festnahme: "Anteil der Fälle mit Festnahme, in %",
  }[d.kennzahl];
}

function format(d, v) {
  if (v === null || v === undefined) return "–";
  if (d.kennzahl === "profil") return komma.format(v);
  if (d.kennzahl === "veraenderung") return `${v > 0 ? "+" : ""}${komma.format(v)} %`;
  if (["nacht", "festnahme"].includes(d.kennzahl)) return `${komma.format(v)} %`;
  return komma.format(v);
}

let karten = null;
let kartenBezirke = null;
let kartenStadtteile = null;

function stufe(v, grenzen, farben) {
  const i = grenzen.findIndex((g) => v <= g);
  return farben[i === -1 ? grenzen.length : i];
}

function klassentext(grenzen, i) {
  if (i === 0) return `bis ${achsenzahl(grenzen[0])}`;
  if (i === grenzen.length) return `> ${achsenzahl(grenzen[i - 1])}`;
  return `${achsenzahl(grenzen[i - 1])} – ${achsenzahl(grenzen[i])}`;
}

function kurzname(d, name) {
  return d.raum === "tract" ? name.replace("Census Tract", "Tract") : name;
}

function tooltip(d, name, geoid, t) {
  const zeilen = [d.raum === "tract" ? `${name} (${geoid})` : name];
  if (!t) return zeilen;
  const k = d.kennzahl;
  if (k === "festnahme") {
    zeilen.push(`${zahl.format(t.faelle)} Fälle, davon ${zahl.format(t.festnahmen)} mit Festnahme`);
    if (t.anteil !== null) zeilen.push(`${komma.format(t.anteil)} % der ${zahl.format(t.bekannt)} Fälle mit bekanntem Stand`);
  } else if (k === "nacht") {
    zeilen.push(`${zahl.format(t.dunkel)} von ${zahl.format(t.licht_bekannt)} Fällen bei Dunkelheit`);
  } else if (k === "veraenderung") {
    zeilen.push(`${zahl.format(t.faelle)} Fälle, ein Jahr zuvor ${zahl.format(t.faelle_vorjahr)}`);
  } else if (k === "profil") {
    zeilen.push(`${zahl.format(t.faelle)} von ${zahl.format(t.faelle_alle)} Fällen in den gewählten Kategorien`);
  } else if (d.raum === "sechseck") {
    zeilen.push(`${zahl.format(t.faelle)} Fälle`);
  } else {
    zeilen.push(t.einwohner ? `${zahl.format(t.einwohner)} Einwohner` : "keine Einwohner");
    zeilen.push(`${zahl.format(t.faelle)} Fälle` + (t.rate === null ? "" : ` · ${komma.format(t.rate)} je 1'000`));
  }
  if (t.wert !== null && k !== "rate") zeilen.push(`${einheit(d)}: ${format(d, t.wert)}`);
  if (k === "geglaettet" && t.gewicht !== undefined) {
    zeilen.push(`eigene Rate mit Gewicht ${komma.format(t.gewicht)}, Rest Mittel der Stadt`);
  }
  if (t.geringe_basis) {
    zeilen.push(["rate", "geglaettet"].includes(k)
      ? `geringe Basis (unter ${zahl.format(d.geringe_basis)} Einwohnern)`
      : `geringe Basis (unter ${zahl.format(d.mindestfaelle)} Fällen im Nenner)`);
  }
  return zeilen;
}

function rahmen(d, stadt) {
  if (d.raum === "bezirk") return kartenBezirke[stadt.stadt];
  if (d.raum === "stadtteil") return kartenStadtteile[stadt.stadt];
  const k = karten[stadt.stadt];
  if (d.raum === "tract") return k;
  // Sechsecke kommen mit der Antwort, im Rahmen der Tract-Karte.
  return { ...k, tracts: stadt.tracts.filter((t) => t.d).map((t) => ({ geoid: t.geoid, name: t.name, d: t.d })) };
}

function karte(stadt, d) {
  const k = rahmen(d, stadt);
  const r = RAUM[d.raum];
  const tafel = document.createElement("article");
  tafel.className = `tafel karte ${stadt.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = stadt.name;
  const inhalt = el("g");
  const nach = Object.fromEntries(stadt.tracts.map((t) => [t.geoid, t]));
  for (const f of k.tracts) {
    const t = nach[f.geoid];
    const fuellung = !t || t.geringe_basis || t.wert === null
      ? `url(#schraffur-${stadt.stadt})` : stufe(t.wert, d.klassen, reihe(d));
    const pfad = el("path", { d: f.d, fill: fuellung, class: d.raum === "tract" ? "tract" : `tract ${d.raum}` });
    pfad.append(el("title", {}, tooltip(d, f.name, f.geoid, t).join("\n")));
    inhalt.append(pfad);
  }
  const ziel = kartenflaeche(k, { titel: `${stadt.name}: ${einheit(d)} je ${r.flaeche}`,
    inhalt, defs: schraffur(`schraffur-${stadt.stadt}`) });
  const fuss = document.createElement("p");
  fuss.className = "unterzeile";
  fuss.textContent = `${stadt.tracts.length} ${r.mehrzahl} · ${stadt.geringe} mit geringer Basis schraffiert`
    + (d.kennzahl === "festnahme" && stadt.anteil !== null ? ` · Stadt: ${komma.format(stadt.anteil)} %` : "");
  tafel.append(h2, ziel, fuss);
  return tafel;
}

function rangliste(ziel, stadt, d) {
  const h2 = document.createElement("h2");
  h2.textContent = `Höchste Werte – ${stadt.name}`;
  const box = document.createElement("div");
  box.className = "diagramm";
  ziel.replaceChildren(h2, box);
  const reihen = stadt.hoechste.filter((t) => t.wert > 0);
  if (!reihen.length) return leer(box, `Keine ${RAUM[d.raum].mehrzahl} mit tragfähiger Basis`);
  const b = Math.max(box.clientWidth, 300), l = 130, r = 64, zeile = 24, u = 34;
  const h = reihen.length * zeile + u;
  const max = runde(Math.max(...reihen.map((t) => t.wert)));
  const x = (v) => l + ((b - l - r) * v) / max;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 4; k++) {
    const v = (max * k) / 4;
    svg.append(el("line", { x1: x(v), x2: x(v), y1: 0, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - u + 14, "text-anchor": "middle" }, achsenzahl(v)));
  }
  svg.append(el("text", { x: (l + b - r) / 2, y: h - 4, "text-anchor": "middle", class: "achsentitel" },
    einheit(d)));
  reihen.forEach((t, i) => {
    const y = i * zeile + 4;
    svg.append(el("text", { x: l - 8, y: y + 12, "text-anchor": "end" }, kurzname(d, t.name)));
    const rect = el("rect", { x: l, y, width: x(t.wert) - l, height: 16, rx: 2, fill: FARBE[stadt.stadt] });
    rect.append(el("title", {}, tooltip(d, t.name, t.geoid, t).join("\n")));
    svg.append(rect);
    svg.append(el("text", { x: x(t.wert) + 6, y: y + 12, class: "wert" }, format(d, t.wert)));
  });
  box.replaceChildren(svg);
}

function hinweise(d) {
  const p = [];
  const k = d.kennzahl;
  if (k === "festnahme") {
    p.push("Festnahme heisst: Chicago meldet eine Festnahme zum Fall (arrest); Detroit führt den Fall als "
        + "»Cleared by Arrest«. Detroits »Exceptionally Cleared« zählt nicht mit – Chicago kennt es nicht.",
      "Junge Fälle sind oft noch nicht geklärt. Der Stand wird nachgetragen, in Detroit stark: "
        + "2025 und 2026 liegt die Quote dort bei 5 bis 6 %, nach 9 bis 12 % in den Jahren davor.",
      ...d.staedte.filter((s) => s.jung).map((s) =>
        `${s.name}: Der Zeitraum endet weniger als ein Jahr vor dem letzten Tag mit Daten – `
        + "die Quote wird noch steigen und ist mit älteren Jahren nicht vergleichbar."));
  }
  if (k === "geglaettet") {
    p.push("Geglättet nach Empirical Bayes (Marshall 1991): Je weniger Einwohner, desto stärker rückt "
      + "die Rate zum Mittel der Stadt. Kleine Flächen färben so nicht wegen eines einzelnen Falls dunkel.");
  }
  if (k === "veraenderung" && d.vergleich) {
    p.push(`Verglichen werden die Tage ${d.vergleich[0]} bis ${d.vergleich[1]} mit denselben Tagen ein `
      + "Jahr zuvor, über die Tage mit Daten in beiden Jahren. Blau weniger, rot mehr Fälle.");
  }
  if (k === "profil") {
    p.push("Deliktprofil: Anteil der gewählten Kategorien an allen Fällen der Fläche, geteilt durch "
      + "denselben Anteil in der Stadt. Über 1 heisst häufiger als im Mittel der Stadt – ohne Einwohner "
      + "gerechnet, also ohne »Tatort ist nicht Wohnort«.");
  }
  if (k === "nacht") {
    p.push("Dunkelheit heisst: nach Sonnenuntergang und vor Sonnenaufgang am Ort der Stadt, wie in "
      + "»Tag und Nacht«. Fälle mit Platzhalterzeit (00:00, 12:00) zählen nicht.");
  }
  if (["rate", "geglaettet"].includes(k) && d.raum !== "sechseck") {
    p.push("Tatort ist nicht Wohnort: Innenstadt und Verkehrsknoten haben viele Taten und wenige Bewohner.");
  }
  if (!["rate", "geglaettet"].includes(k)) {
    p.push(`Flächen mit weniger als ${zahl.format(d.mindestfaelle)} Fällen im Nenner sind schraffiert.`);
  } else if (k === "rate" && d.raum !== "sechseck") {
    p.push(`Flächen unter ${zahl.format(d.geringe_basis)} Einwohnern sind schraffiert und nicht in der Rangliste.`);
  }
  if (d.raum === "bezirk") {
    p.push("Einwohner je Polizeibezirk: die Tracts nach ihrem Flächenanteil verteilt. Chicagos District 31 "
      + "fehlt – er umfasst die Gemeinden Norridge und Harwood Heights, die nicht zu Chicago gehören.");
  }
  if (d.raum === "stadtteil") {
    p.push("Stadtteile: Chicagos 77 Community Areas und Detroits 54 Master Plan Neighborhoods. "
      + "Einwohner nach Flächenanteil der Tracts verteilt. Belle Isle liegt in keinem Detroiter "
      + "Stadtteil – dort wohnt niemand.");
  }
  if (d.raum === "sechseck") {
    p.push("Sechsecke mit 500 m Kante (rund 0,65 km²), unabhängig von Verwaltungsgrenzen. Ohne Einwohner: "
      + "Die Rate ist hier eine Dichte, und es erscheinen nur Zellen mit Fällen. Gleich grosse Zellen "
      + "zeigen, ob eine Häufung auch ohne den Zuschnitt der Tracts und Bezirke besteht. Eine dunkle "
      + "Zelle heisst viele Fälle, nicht hohes Risiko: Wo sich viele Menschen aufhalten, etwa in der "
      + "Innenstadt, ist die Dichte hoch.");
  }
  p.push(...d.staedte.map((s) => {
    const v = s.verortung;
    const ohne = v.outside_city + v.no_tract + v.missing_coordinate;
    const alle = ohne + v.inside_city;
    return `${s.name}: ${zahl.format(ohne)} Fälle ohne Ort in der Stadt`
      + (alle ? ` (${komma.format((ohne * 100) / alle)} %)` : "")
      + ` – ${zahl.format(v.missing_coordinate)} ohne Koordinate, `
      + `${zahl.format(v.outside_city + v.no_tract)} ausserhalb. Sie fehlen auf der Karte.`;
  }), "Keine Aussage über individuelles Risiko.");
  return p;
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  const r = RAUM[d.raum];
  // Geglaettet gibt es fuer Sechsecke nicht - ohne Einwohner kein Nenner.
  const knopf = document.querySelector('.umschalter[data-param="kennzahl"] [data-wert="geglaettet"]');
  if (knopf) knopf.hidden = d.raum === "sechseck";
  const mitNenner = ["rate", "geglaettet"].includes(d.kennzahl) && d.raum !== "sechseck";
  document.getElementById("u-geografie").textContent = `${einheit(d)} je ${r.flaeche} · ${zr}`
    + (mitNenner && hochrechnung({ z: d.auswahl.tage }) ? ` · ${hochrechnung({ z: d.auswahl.tage })}` : "")
    + (mitNenner && d.vintage ? ` · Einwohner ACS ${d.vintages.length > 1 ? d.vintages.join("/") : d.vintage}` : "");
  document.getElementById("karten").replaceChildren(...d.staedte.map((s) => karte(s, d)));
  document.getElementById("karten").classList.toggle("einzeln", d.staedte.length === 1);

  document.getElementById("t-legende").textContent = `${einheit(d)} · ${zr}`;
  const farben = reihe(d);
  const klassen = [...d.klassen.map((_, i) => i), d.klassen.length];
  document.getElementById("d-legende").replaceChildren(...klassen.map((i) => {
    const k = document.createElement("span");
    const farbe = document.createElement("i");
    farbe.style.background = farben[i];
    k.append(farbe, klassentext(d.klassen, i));
    return k;
  }));
  document.getElementById("t-geringe").textContent = ["rate", "geglaettet"].includes(d.kennzahl)
    ? `Geringe Basis (unter ${zahl.format(d.geringe_basis)} Einwohner)`
    : `Geringe Basis (unter ${zahl.format(d.mindestfaelle)} Fällen im Nenner)`;

  // Zwei Staedte (FR-43): fest, wie die Behaelter rang-chicago und
  // rang-detroit in geografie.html. Fuer eine dritte Stadt erschiene keine
  // Rangliste.
  for (const s of ["chicago", "detroit"]) {
    const ziel = document.getElementById(`rang-${s}`);
    const stadt = d.staedte.find((x) => x.stadt === s);
    ziel.hidden = !stadt;
    if (stadt) rangliste(ziel, stadt, d);
  }

  document.getElementById("d-hinweise").replaceChildren(...hinweise(d).map((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
}

// Ein Link von vor dem 25.11.2026 traegt ``ansicht``; er gilt weiter.
function alteAnsicht() {
  const url = new URLSearchParams(location.search);
  const alt = { tract: ["tract", "rate"], bezirk: ["bezirk", "rate"], festnahme: ["bezirk", "festnahme"] };
  const paar = alt[url.get("ansicht")];
  if (!paar || url.has("raum")) return;
  url.delete("ansicht");
  url.set("raum", paar[0]);
  url.set("kennzahl", paar[1]);
  history.replaceState(null, "", "?" + url);
}

async function start() {
  alteAnsicht();
  const [tracts, bezirke, teile] = await Promise.all([fetch("/api/karten"),
    fetch("/api/karten?raum=bezirk"), fetch("/api/karten?raum=stadtteil")]);
  if (tracts.ok) karten = await tracts.json();
  if (bezirke.ok) kartenBezirke = await bezirke.json();
  if (teile.ok) kartenStadtteile = await teile.json();
  starteBrett({ api: "/api/geografie", zeichne });
}

start();
