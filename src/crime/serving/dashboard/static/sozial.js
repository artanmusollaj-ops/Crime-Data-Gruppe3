// Das Brett »Soziales Umfeld«.
import { FARBE, achsenzahl, balken, el, komma, leer, legende, starteBrett, zahl, zeitraumtext }
  from "./gemeinsam.js";

// Dieselben Stufen wie auf der »Geografie«: dieselbe Farbe ist dieselbe Rate.
const RATE = ["#dcebfa", "#a9cdf2", "#6aa6e4", "#2f7de1", "#0b3f8a"];
const ARMUT = ["#fdebd3", "#fbc58c", "#f59a4b", "#de6a1f", "#a43d06"];
// Bivariat, nach Joshua Stevens, »Bivariate Choropleth Maps: A How-to Guide«
// (2015): Zeile = Stufe der Fallrate, Spalte = Stufe der Armutsquote.
const BIVARIAT = [
  ["#e8e8e8", "#e4acac", "#c85a5a"],
  ["#b0d5df", "#ad9ea5", "#985356"],
  ["#64acbe", "#627f8c", "#574249"],
];
let karten = null;
const zweistellig = (v) => (v === null ? "–" : v.toFixed(2).replace(".", ","));

const stufe = (wert, grenzen) => {
  const i = grenzen.findIndex((g) => wert <= g);
  return i === -1 ? grenzen.length : i;
};

function klassentext(grenzen, i, einheit = "") {
  if (i === 0) return `bis ${achsenzahl(grenzen[0])}${einheit}`;
  if (i === grenzen.length) return `> ${achsenzahl(grenzen[i - 1])}${einheit}`;
  return `${achsenzahl(grenzen[i - 1])} – ${achsenzahl(grenzen[i])}${einheit}`;
}

function armutsstufe(t, baender) {
  return t.band === null ? null : baender.findIndex((b) => b.band === t.band);
}

// Eine Karte: je Tract die Farbe, die ``farbe(t)`` sagt; ``null`` heisst schraffiert.
function karte(stadt, titel, farbe, d) {
  const k = karten[stadt.stadt];
  const tafel = document.createElement("article");
  tafel.className = `tafel karte ${stadt.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = titel;
  const id = `schraffur-${stadt.stadt}-${titel.length}`;
  const svg = el("svg", { viewBox: `-10 -10 ${k.breite + 20} ${k.hoehe + 20}`, role: "img",
    "aria-label": titel });
  const defs = el("defs");
  const muster = el("pattern", { id, width: 6, height: 6, patternUnits: "userSpaceOnUse",
    patternTransform: "rotate(45)" });
  muster.append(el("rect", { width: 6, height: 6, fill: "#f1f3f6" }),
    el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "#aab3bf", "stroke-width": 2 }));
  defs.append(muster);
  svg.append(defs);
  const nach = Object.fromEntries(stadt.tracts.map((t) => [t.geoid, t]));
  for (const f of k.tracts) {
    const t = nach[f.geoid];
    const pfad = el("path", { d: f.d, fill: (t && farbe(t)) || `url(#${id})`, class: "tract" });
    const zeilen = [`${f.name} (${f.geoid})`];
    if (t) {
      zeilen.push(t.einwohner ? `${zahl.format(t.einwohner)} Einwohner` : "keine Einwohner");
      zeilen.push(`${zahl.format(t.faelle)} Fälle` + (t.rate === null ? "" : ` · ${komma.format(t.rate)} je 1'000`));
      zeilen.push(t.armut === null ? "Armutsquote unbekannt" : `Armutsquote ${komma.format(t.armut)} %`);
      if (t.einkommen) zeilen.push(`Medianeinkommen ${zahl.format(t.einkommen)} USD`);
      if (t.geringe_basis && t.einwohner) zeilen.push(`geringe Basis (unter ${zahl.format(d.geringe_basis)})`);
    }
    pfad.append(el("title", {}, zeilen.join("\n")));
    svg.append(pfad);
  }
  const flaeche = document.createElement("div");
  flaeche.className = "kartenflaeche";
  flaeche.append(svg);
  tafel.append(h2, flaeche);
  return tafel;
}

function kartenbereich(d) {
  const ziel = document.getElementById("karten");
  ziel.replaceChildren();
  const bivariat = d.auswahl.karte === "bivariat";
  const rateFarbe = (t) => (t.geringe_basis || t.rate === null ? null : RATE[stufe(t.rate, d.klassen)]);
  const armutFarbe = (t) => (t.armut === null || !t.einwohner ? null : ARMUT[armutsstufe(t, d.armut)]);
  const biFarbe = (t) => {
    if (t.geringe_basis || t.rate === null || t.armut === null) return null;
    return BIVARIAT[stufe(t.rate, d.bivariat.rate)][stufe(t.armut, d.bivariat.armut)];
  };
  if (bivariat) {
    const reihe = document.createElement("div");
    reihe.className = `raster ${d.staedte.length === 1 ? "einzeln" : ""}`;
    reihe.append(...d.staedte.map((s) => karte(s, `${s.name}: Fallrate und Armut`, biFarbe, d)));
    ziel.append(reihe);
  } else {
    for (const s of d.staedte) {
      const paar = document.createElement("div");
      paar.className = "raster kartenpaar";
      paar.append(karte(s, `${s.name}: Fälle je 1'000 Einwohner`, rateFarbe, d),
        karte(s, `${s.name}: Armutsquote`, armutFarbe, d));
      ziel.append(paar);
    }
  }
  document.getElementById("legende-nebeneinander").hidden = bivariat;
  document.getElementById("legende-bivariat").hidden = !bivariat;

  const klassen = (ziel, farben, texte) => ziel.replaceChildren(...texte.map((text, i) => {
    const k = document.createElement("span");
    const f = document.createElement("i");
    f.style.background = farben[i];
    k.append(f, text);
    return k;
  }));
  klassen(document.getElementById("d-legende-rate"), RATE,
    [...d.klassen.map((_, i) => i), d.klassen.length].map((i) => klassentext(d.klassen, i)));
  klassen(document.getElementById("d-legende-armut"), ARMUT, d.armut.map((b) => b.band));

  // Die bivariate Legende: drei mal drei Felder, Armut nach rechts, Rate nach oben.
  const r = d.bivariat.rate, a = d.bivariat.armut;
  const legende3 = el("svg", { viewBox: "0 0 260 150", role: "img", "aria-label": "Legende" });
  for (let z = 0; z < 3; z++) {
    for (let s = 0; s < 3; s++) {
      legende3.append(el("rect", { x: 70 + s * 34, y: 10 + (2 - z) * 34, width: 32, height: 32,
        fill: BIVARIAT[z][s] }));
    }
  }
  legende3.append(el("text", { x: 121, y: 128, "text-anchor": "middle" }, "Armutsquote →"));
  legende3.append(el("text", { x: 60, y: 62, "text-anchor": "end" }, "Fallrate ↑"));
  document.getElementById("d-bivariat").replaceChildren(legende3);
  document.getElementById("u-bivariat").textContent = r.length && a.length
    ? `Terzile über ${d.staedte.map((s) => s.name).join(" und ")} zusammen. Fallrate: niedrig bis `
      + `${komma.format(r[0])}, mittel bis ${komma.format(r[1])}, hoch darüber (je 1'000). Armutsquote: `
      + `niedrig bis ${komma.format(a[0])} %, mittel bis ${komma.format(a[1])} %, hoch darüber. `
      + "Dunkel heisst beides hoch; schraffiert sind Tracts mit geringer Basis oder ohne Wert."
    : "Zu wenige Tracts für Terzile.";
}

function kacheln(d) {
  const ziel = document.getElementById("k-staedte");
  ziel.replaceChildren(...d.staedte.map((s) => {
    const kachel = document.createElement("div");
    kachel.className = `kachel stadtkachel ${s.stadt}`;
    const text = document.createElement("div");
    const sp = s.spanne;
    const zeilen = [
      ["span", `${s.name}: Fallrate im ärmsten gegen das reichste Band`],
      ["b", sp && sp.reich.rate ? `${komma.format(sp.arm.rate / sp.reich.rate)}-fach` : "–"],
      ["small", sp ? `${komma.format(sp.arm.rate)} je 1'000 (${sp.arm.band}) gegen `
        + `${komma.format(sp.reich.rate)} (${sp.reich.band})` : "Zu wenige Bänder mit fünf Tracts"],
      ["small", `Rangkorrelation mit der Armut ${zweistellig(s.spearman)}, `
        + `mit dem Einkommen ${zweistellig(s.spearman_einkommen)}`],
      ["small", `Ohne Einkommen: ${zahl.format(s.ohne_einkommen)} von ${zahl.format(s.mit_einwohnern)} `
        + `bewohnten Tracts${s.mit_einwohnern ? ` (${komma.format((s.ohne_einkommen * 100) / s.mit_einwohnern)} %)` : ""}`],
    ];
    for (const [art, inhalt] of zeilen) {
      const e = document.createElement(art);
      if (art === "span") e.className = "etikett";
      e.textContent = inhalt;
      text.append(e);
    }
    kachel.append(text);
    return kachel;
  }));
}

function streuung(ziel, d) {
  const punkte = d.staedte.flatMap((s) => s.tracts
    .filter((t) => !t.geringe_basis && t.rate !== null && t.armut !== null)
    .map((t) => ({ ...t, stadt: s.stadt, name_stadt: s.name })));
  if (!punkte.length) return leer(ziel, "Keine Tracts mit tragfähiger Basis");
  const b = Math.max(ziel.clientWidth, 320), h = 300, l = 56, r = 16, o = 12, u = 40;
  const xmax = Math.ceil(Math.max(...punkte.map((p) => p.armut)) / 10) * 10;
  const ticks = [1, 3, 10, 30, 100, 300, 1000, 3000];
  const ymax = ticks.find((t) => t >= Math.max(...punkte.map((p) => p.rate))) ?? 3000;
  const x = (v) => l + ((b - l - r) * v) / xmax;
  const y = (v) => o + (h - o - u) * (1 - Math.log10(Math.max(v, 1)) / Math.log10(ymax));
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (const t of ticks.filter((t) => t <= ymax)) {
    svg.append(el("line", { x1: l, x2: b - r, y1: y(t), y2: y(t), class: "achse" }));
    svg.append(el("text", { x: l - 8, y: y(t) + 4, "text-anchor": "end" }, zahl.format(t)));
  }
  for (let v = 0; v <= xmax; v += 10) {
    svg.append(el("line", { x1: x(v), x2: x(v), y1: o, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - u + 16, "text-anchor": "middle" }, `${v} %`));
  }
  svg.append(el("text", { x: (l + b - r) / 2, y: h - 4, "text-anchor": "middle", class: "achsentitel" },
    "Armutsquote des Tracts"));
  for (const p of punkte) {
    const c = el("circle", { cx: x(p.armut), cy: y(p.rate), r: 3, fill: FARBE[p.stadt], "fill-opacity": 0.55 });
    c.append(el("title", {}, `${p.name_stadt}, ${p.name}: ${komma.format(p.rate)} je 1'000, `
      + `Armutsquote ${komma.format(p.armut)} %`));
    svg.append(c);
  }
  ziel.replaceChildren(svg);
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  document.getElementById("u-sozial").textContent = `Fälle je 1'000 Einwohner und Armutsquote je Census `
    + `Tract · ${zr}` + (d.vintage ? ` · ACS ${d.vintage}` : "");
  document.getElementById("ohne-vintage").hidden = Boolean(d.vintage);
  if (!karten) return;
  kacheln(d);
  kartenbereich(d);
  const legendeStaedte = d.staedte.map((s) => ({ name: s.name, klasse: s.stadt }));
  const zeilen = d.armut.map((b, i) => ({
    name: b.band,
    werte: Object.fromEntries(d.staedte.map((s) => [s.stadt, s.baender[i].rate])),
  }));
  balken(document.getElementById("d-baender"), zeilen, d.staedte, (v) => komma.format(v));
  // Ein Band mit weniger als fuenf Tracts ist blass - sein Wert ruht auf wenigen Gebieten.
  const rechtecke = document.querySelectorAll("#d-baender rect");
  let n = 0;
  d.armut.forEach((_, i) => d.staedte.forEach((s) => {
    const rect = rechtecke[n++];
    if (rect && s.baender[i].tracts < 5) rect.setAttribute("fill-opacity", "0.35");
  }));
  legende(document.getElementById("l-baender"), legendeStaedte);
  streuung(document.getElementById("d-streuung"), d);
  legende(document.getElementById("l-streuung"), legendeStaedte);

  const punkte = [
    "Ein Zusammenhang je Tract sagt nichts über einzelne Menschen (ökologischer Fehlschluss) "
      + "und nichts über Ursachen.",
    "Tatort ist nicht Wohnort: Innenstadt und Verkehrsknoten haben viele Taten und wenige Bewohner.",
    "Die ACS-Werte sind Fünfjahres-Schätzungen; ihre Fehlermargen sind nicht geladen. "
      + "Für 2025 und 2026 gelten die Werte von 2024.",
    `Tracts unter ${zahl.format(d.geringe_basis)} Einwohnern sind schraffiert und fehlen im Streudiagramm.`,
    ...d.staedte.map((s) => `${s.name}: Armutsquote fehlt für ${zahl.format(s.ohne_armut)}, `
      + `Einkommen für ${zahl.format(s.ohne_einkommen)} bewohnte Tracts – die Lücken sind zwischen `
      + "den Städten ungleich."),
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
  starteBrett({ api: "/api/sozial", zeichne });
}

start();
