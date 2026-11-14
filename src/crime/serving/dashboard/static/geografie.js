// Das Brett »Geografie«.
import { FARBE, achsenzahl, el, komma, leer, runde, starteBrett, zahl, zeitraumtext } from "./gemeinsam.js";
import { kartenflaeche, schraffur } from "./karte.js";

// Eine Farbreihe fuer beide Staedte: Dieselbe Farbe ist dieselbe Rate.
const STUFEN = ["#dcebfa", "#a9cdf2", "#6aa6e4", "#2f7de1", "#0b3f8a"];
let karten = null;

function stufe(rate, grenzen) {
  const i = grenzen.findIndex((g) => rate <= g);
  return STUFEN[i === -1 ? grenzen.length : i];
}

function klassentext(grenzen, i) {
  if (i === 0) return `bis ${achsenzahl(grenzen[0])}`;
  if (i === grenzen.length) return `> ${achsenzahl(grenzen[i - 1])}`;
  return `${achsenzahl(grenzen[i - 1])} – ${achsenzahl(grenzen[i])}`;
}

function karte(stadt, d) {
  const k = karten[stadt.stadt];
  const tafel = document.createElement("article");
  tafel.className = `tafel karte ${stadt.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = stadt.name;
  const inhalt = el("g");
  const nach = Object.fromEntries(stadt.tracts.map((t) => [t.geoid, t]));
  for (const f of k.tracts) {
    const t = nach[f.geoid];
    const fuellung = !t || t.geringe_basis || t.rate === null
      ? `url(#schraffur-${stadt.stadt})` : stufe(t.rate, d.klassen);
    const pfad = el("path", { d: f.d, fill: fuellung, class: "tract" });
    const zeilen = [`${f.name} (${f.geoid})`];
    if (t) {
      zeilen.push(t.einwohner ? `${zahl.format(t.einwohner)} Einwohner` : "keine Einwohner");
      zeilen.push(`${zahl.format(t.faelle)} Fälle` + (t.rate === null ? "" : ` · ${komma.format(t.rate)} je 1'000`));
      if (t.geringe_basis && t.einwohner) zeilen.push(`geringe Basis (unter ${zahl.format(d.geringe_basis)})`);
    }
    pfad.append(el("title", {}, zeilen.join("\n")));
    inhalt.append(pfad);
  }
  const ziel = kartenflaeche(k, { titel: `${stadt.name}: Fälle je 1'000 Einwohner je Tract`,
    inhalt, defs: schraffur(`schraffur-${stadt.stadt}`) });
  const fuss = document.createElement("p");
  fuss.className = "unterzeile";
  fuss.textContent = `${stadt.tracts.length} Tracts · ${stadt.geringe} mit geringer Basis schraffiert`;
  tafel.append(h2, ziel, fuss);
  return tafel;
}

function rangliste(ziel, stadt) {
  const h2 = document.createElement("h2");
  h2.textContent = `Höchste Raten – ${stadt.name}`;
  const box = document.createElement("div");
  box.className = "diagramm";
  ziel.replaceChildren(h2, box);
  if (!stadt.hoechste.length) return leer(box, "Keine Tracts mit tragfähiger Basis");
  const b = Math.max(box.clientWidth, 300), l = 130, r = 56, zeile = 24, u = 34;
  const h = stadt.hoechste.length * zeile + u;
  const max = runde(Math.max(...stadt.hoechste.map((t) => t.rate)));
  const x = (v) => l + ((b - l - r) * v) / max;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 4; k++) {
    const v = (max * k) / 4;
    svg.append(el("line", { x1: x(v), x2: x(v), y1: 0, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - u + 14, "text-anchor": "middle" }, achsenzahl(v)));
  }
  svg.append(el("text", { x: (l + b - r) / 2, y: h - 4, "text-anchor": "middle", class: "achsentitel" },
    "Fälle je 1'000 Einwohner"));
  stadt.hoechste.forEach((t, i) => {
    const y = i * zeile + 4;
    svg.append(el("text", { x: l - 8, y: y + 12, "text-anchor": "end" }, t.name.replace("Census Tract", "Tract")));
    const rect = el("rect", { x: l, y, width: x(t.rate) - l, height: 16, rx: 2, fill: FARBE[stadt.stadt] });
    rect.append(el("title", {}, `${t.name} (${t.geoid}): ${zahl.format(t.faelle)} Fälle, `
      + `${zahl.format(t.einwohner)} Einwohner`));
    svg.append(rect);
    svg.append(el("text", { x: x(t.rate) + 6, y: y + 12, class: "wert" }, komma.format(t.rate)));
  });
  box.replaceChildren(svg);
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  document.getElementById("u-geografie").textContent =
    `Fälle je 1'000 Einwohner je Census Tract · ${zr}` + (d.vintage ? ` · Einwohner ACS ${d.vintage}` : "");
  document.getElementById("karten").replaceChildren(...d.staedte.map((s) => karte(s, d)));
  document.getElementById("karten").classList.toggle("einzeln", d.staedte.length === 1);

  document.getElementById("t-legende").textContent = `Fälle je 1'000 Einwohner · ${zr}`;
  const klassen = [...d.klassen.map((_, i) => i), d.klassen.length];
  document.getElementById("d-legende").replaceChildren(...klassen.map((i) => {
    const k = document.createElement("span");
    const farbe = document.createElement("i");
    farbe.style.background = STUFEN[i];
    k.append(farbe, klassentext(d.klassen, i));
    return k;
  }));
  document.getElementById("t-geringe").textContent =
    `Geringe Basis (unter ${zahl.format(d.geringe_basis)} Einwohner)`;

  for (const s of ["chicago", "detroit"]) {
    const ziel = document.getElementById(`rang-${s}`);
    const stadt = d.staedte.find((x) => x.stadt === s);
    ziel.hidden = !stadt;
    if (stadt) rangliste(ziel, stadt);
  }

  const punkte = [
    "Kleine Einwohnerzahlen lassen Raten stark schwanken; Tracts unter "
      + `${zahl.format(d.geringe_basis)} Einwohnern sind schraffiert und nicht in der Rangliste.`,
    "Tatort ist nicht Wohnort: Innenstadt und Verkehrsknoten haben viele Taten und wenige Bewohner.",
    ...d.staedte.map((s) => {
      const v = s.verortung;
      const ohne = v.outside_city + v.no_tract + v.missing_coordinate;
      const alle = ohne + v.inside_city;
      return `${s.name}: ${zahl.format(ohne)} Fälle ohne Ort in der Stadt`
        + (alle ? ` (${komma.format((ohne * 100) / alle)} %)` : "")
        + ` – ${zahl.format(v.missing_coordinate)} ohne Koordinate, `
        + `${zahl.format(v.outside_city + v.no_tract)} ausserhalb. Sie fehlen auf der Karte.`;
    }),
    "Keine Aussage über individuelles Risiko.",
  ];
  document.getElementById("d-hinweise").replaceChildren(...punkte.map((p) => {
    const li = document.createElement("li");
    li.textContent = p;
    return li;
  }));
}

async function start() {
  const antwort = await fetch("/api/karten");
  if (antwort.ok) karten = await antwort.json();
  starteBrett({ api: "/api/geografie", zeichne });
}

start();
