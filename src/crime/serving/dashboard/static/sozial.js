// Das Brett »Soziales Umfeld«.
import { FARBE, achsenzahl, balken, el, komma, leer, legende, starteBrett, zahl, zeitraumtext }
  from "./gemeinsam.js";
import { kartenflaeche, kopplung, schraffur } from "./karte.js";

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
function karte(stadt, titel, farbe, d, gekoppelt = null) {
  const k = karten[stadt.stadt];
  const tafel = document.createElement("article");
  tafel.className = `tafel karte ${stadt.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = titel;
  const id = `schraffur-${stadt.stadt}-${titel.length}`;
  const inhalt = el("g");
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
    inhalt.append(pfad);
  }
  const flaeche = kartenflaeche(k, { titel, inhalt, defs: schraffur(id), gekoppelt });
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
      // Rate und Armut derselben Stadt zoomen gemeinsam: Derselbe Ausschnitt
      // nebeneinander ist der Sinn des Paars.
      const gemeinsam = kopplung();
      paar.append(karte(s, `${s.name}: Fälle je 1'000 Einwohner und Jahr`, rateFarbe, d, gemeinsam),
        karte(s, `${s.name}: Armutsquote`, armutFarbe, d, gemeinsam));
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

// Das Streudiagramm, seit dem 28.11.2026 mit drei Aenderungen:
// * Die senkrechte Achse richtet sich nach den Daten. Vorher begann sie fest
//   bei 1 je 1'000 und setzte alles darunter auf 1; bei Toetungsdelikten
//   (2025) lagen so 989 von 1'052 Punkten am Boden, 675 davon mit Rate 0.
//   Eine Rate 0 hat auf einer logarithmischen Achse keinen Ort; diese Tracts
//   stehen in einem eigenen Streifen »0 Fälle« unter der Achse.
// * Ein Klick auf eine Stadt in der Legende blendet sie aus und ein.
// * Ein aufgezogenes Rechteck zoomt hinein; Doppelklick oder »Zurücksetzen«
//   fuehrt zurueck. Ein neuer Filter beginnt wieder ungezoomt.
const streuwahl = { aus: new Set(), zoom: null, daten: null };

// Logarithmische Teilstriche zwischen a und b: 1-3-10, bei kleiner Spanne 1-2-5.
function logstriche(a, b) {
  const striche = (faktoren) => {
    const t = [];
    for (let e = Math.floor(Math.log10(a)) - 1; e <= Math.ceil(Math.log10(b)) + 1; e++) {
      for (const f of faktoren) {
        const v = Number((f * 10 ** e).toPrecision(6));
        if (v >= a * 0.999 && v <= b * 1.001) t.push(v);
      }
    }
    return t;
  };
  const grob = striche([1, 3]);
  return grob.length >= 4 ? grob : striche([1, 2, 5]);
}

// Die Huelle aus 1-3-10-Stufen um die positiven Raten.
function loghuelle(werte) {
  if (!werte.length) return [0.1, 1];
  const min = Math.min(...werte), max = Math.max(...werte);
  const stufen = [];
  for (let e = Math.floor(Math.log10(min)) - 1; e <= Math.ceil(Math.log10(max)) + 1; e++) {
    stufen.push(10 ** e, 3 * 10 ** e);
  }
  const unten = Math.max(...stufen.filter((v) => v <= min * 1.0001));
  const oben = Math.min(...stufen.filter((v) => v >= max * 0.9999));
  return [unten, oben > unten ? oben : unten * 10];
}

// Ein fester Versatz je Tract im Nullstreifen, damit die Punkte nicht
// aufeinander liegen und bei jedem Zeichnen gleich stehen.
function versatz(text) {
  let h = 2166136261;
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

function linearstriche(a, b) {
  const schritt = [0.5, 1, 2, 5, 10, 20, 25].find((s) => (b - a) / s <= 8) ?? 50;
  const t = [];
  for (let v = Math.ceil(a / schritt) * schritt; v <= b + 1e-9; v += schritt) t.push(Number(v.toFixed(2)));
  return t;
}

function streuung(ziel, d) {
  if (streuwahl.daten !== d) { streuwahl.daten = d; streuwahl.zoom = null; }
  const alle = d.staedte.flatMap((s) => s.tracts
    .filter((t) => !t.geringe_basis && t.rate !== null && t.armut !== null)
    .map((t) => ({ ...t, stadt: s.stadt, name_stadt: s.name })));
  const knopf = document.getElementById("streuung-zurueck");
  knopf.hidden = !streuwahl.zoom;
  if (!alle.length) return leer(ziel, "Keine Tracts mit tragfähiger Basis");
  const sichtbar = alle.filter((p) => !streuwahl.aus.has(p.stadt));
  if (!sichtbar.length) return leer(ziel, "Alle Städte ausgeblendet – Klick auf eine Stadt in der Legende");

  // Bereich: ungezoomt aus allen Tracts (auch ausgeblendeten), damit die Achse
  // beim Ein- und Ausblenden stehen bleibt.
  const z = streuwahl.zoom;
  const [ya, yb] = z ? [z.ya, z.yb] : loghuelle(alle.filter((p) => p.rate > 0).map((p) => p.rate));
  const [xa, xb] = z ? [z.xa, z.xb] : [0, Math.max(10, Math.ceil(Math.max(...alle.map((p) => p.armut)) / 10) * 10)];
  const hatNull = alle.some((p) => p.rate === 0);
  const mitNull = z ? z.mitNull : hatNull;
  const nullen = mitNull ? sichtbar.filter((p) => p.rate === 0 && p.armut >= xa && p.armut <= xb) : [];
  const positiv = sichtbar.filter((p) => p.rate > 0 && p.rate >= ya && p.rate <= yb
    && p.armut >= xa && p.armut <= xb);

  const b = Math.max(ziel.clientWidth, 320), l = 56, r = 16, o = 12, u = 40;
  // Die Hoehe bleibt beim Zoomen dieselbe, damit die Legende nicht springt.
  const streifen = mitNull ? 44 : 0, h = 300 + (hatNull ? 44 : 0);
  const unten = h - u - streifen;  // Unterkante der logarithmischen Flaeche
  const x = (v) => l + ((b - l - r) * (v - xa)) / (xb - xa);
  const y = (v) => o + (unten - o) * (1 - (Math.log10(v) - Math.log10(ya)) / (Math.log10(yb) - Math.log10(ya)));
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img", class: "streuflaeche" });
  for (const t of logstriche(ya, yb)) {
    svg.append(el("line", { x1: l, x2: b - r, y1: y(t), y2: y(t), class: "achse" }));
    svg.append(el("text", { x: l - 8, y: y(t) + 4, "text-anchor": "end" }, achsenzahl(t)));
  }
  for (const v of linearstriche(xa, xb)) {
    svg.append(el("line", { x1: x(v), x2: x(v), y1: o, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(v), y: h - u + 16, "text-anchor": "middle" }, `${achsenzahl(v)} %`));
  }
  if (mitNull) {
    const oben = unten + 6;
    svg.append(el("rect", { x: l, y: oben, width: b - l - r, height: streifen - 8, class: "nullstreifen" }));
    svg.append(el("text", { x: l - 8, y: oben + (streifen - 8) / 2 + 4, "text-anchor": "end" }, "0"));
    const anzahl = nullen.length;
    const zahltext = el("text", { x: b - r - 6, y: oben + 13, "text-anchor": "end", class: "nullzahl" },
      `${zahl.format(anzahl)} ${anzahl === 1 ? "Tract" : "Tracts"} ohne Fall`);
    for (const p of nullen) {
      const c = el("circle", { cx: x(p.armut), cy: oben + 4 + versatz(p.stadt + p.name) * (streifen - 16),
        r: 3, fill: FARBE[p.stadt], "fill-opacity": 0.45 });
      c.append(el("title", {}, `${p.name_stadt}, ${p.name}: kein Fall, Armutsquote ${komma.format(p.armut)} %`));
      svg.append(c);
    }
    svg.append(zahltext);
  }
  svg.append(el("text", { x: (l + b - r) / 2, y: h - 4, "text-anchor": "middle", class: "achsentitel" },
    "Armutsquote des Tracts"));
  for (const p of positiv) {
    const c = el("circle", { cx: x(p.armut), cy: y(p.rate), r: 3, fill: FARBE[p.stadt], "fill-opacity": 0.55 });
    c.append(el("title", {}, `${p.name_stadt}, ${p.name}: ${komma.format(p.rate)} je 1'000, `
      + `Armutsquote ${komma.format(p.armut)} %`));
    svg.append(c);
  }

  // Zoomen: ein Rechteck aufziehen (Maus; auf dem Telefon bleibt das Wischen
  // dem Scrollen). Reicht es in den Nullstreifen, bleibt der Streifen.
  const punkt = (ev) => {
    const box = svg.getBoundingClientRect(), f = b / box.width;
    return [(ev.clientX - box.left) * f, (ev.clientY - box.top) * f];
  };
  const imFeld = ([px, py]) => Math.min(Math.max(px, l), b - r) === px && py >= o && py <= h - u;
  let start = null, rahmen = null;
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType !== "mouse" || ev.button !== 0 || !imFeld(punkt(ev))) return;
    start = punkt(ev);
    rahmen = el("rect", { class: "zoomrahmen", x: start[0], y: start[1], width: 0, height: 0 });
    svg.append(rahmen);
    svg.setPointerCapture(ev.pointerId);
    ev.preventDefault();
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!start) return;
    const [px, py] = punkt(ev);
    const cx = Math.min(Math.max(px, l), b - r), cy = Math.min(Math.max(py, o), h - u);
    Object.entries({ x: Math.min(start[0], cx), y: Math.min(start[1], cy),
      width: Math.abs(cx - start[0]), height: Math.abs(cy - start[1]) })
      .forEach(([k, v]) => rahmen.setAttribute(k, v));
  });
  svg.addEventListener("pointerup", () => {
    if (!start) return;
    const bx = Number(rahmen.getAttribute("x")), by = Number(rahmen.getAttribute("y"));
    const bw = Number(rahmen.getAttribute("width")), bh = Number(rahmen.getAttribute("height"));
    start = null;
    rahmen.remove();
    if (bw < 8 || bh < 8) return;  // ein Klick, kein Rahmen
    const wert = (py) => 10 ** (Math.log10(ya) + (1 - (Math.min(py, unten) - o) / (unten - o))
      * (Math.log10(yb) - Math.log10(ya)));
    const armut = (px) => xa + ((px - l) / (b - l - r)) * (xb - xa);
    const neuNull = mitNull && by + bh > unten;
    let neuYa = wert(by + bh), neuYb = wert(by);
    if (by >= unten) { neuYa = ya; neuYb = ya * 10; }  // nur im Nullstreifen
    if (neuYb / neuYa < 1.5) neuYb = neuYa * 1.5;
    streuwahl.zoom = { xa: armut(bx), xb: Math.max(armut(bx + bw), armut(bx) + 0.5),
      ya: neuYa, yb: neuYb, mitNull: neuNull };
    streuung(ziel, d);
  });
  svg.addEventListener("dblclick", () => { if (streuwahl.zoom) { streuwahl.zoom = null; streuung(ziel, d); } });
  ziel.replaceChildren(svg);
}

// Die Legende des Streudiagramms: ein Klick blendet eine Stadt aus und ein.
function streulegende(ziel, d) {
  legende(ziel, d.staedte.map((s) => ({ name: s.name, klasse: s.stadt })));
  [...ziel.children].forEach((span, i) => {
    const stadt = d.staedte[i].stadt;
    const setze = () => {
      span.classList.toggle("aus", streuwahl.aus.has(stadt));
      span.setAttribute("aria-pressed", String(!streuwahl.aus.has(stadt)));
    };
    span.classList.add("umschaltbar");
    span.setAttribute("role", "button");
    span.tabIndex = 0;
    span.title = "Klick blendet die Stadt aus oder ein";
    setze();
    const wechsle = () => {
      if (streuwahl.aus.has(stadt)) streuwahl.aus.delete(stadt); else streuwahl.aus.add(stadt);
      setze();
      streuung(document.getElementById("d-streuung"), d);
    };
    span.addEventListener("click", wechsle);
    span.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); wechsle(); }
    });
  });
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  document.getElementById("u-sozial").textContent = `Fälle je 1'000 Einwohner und Jahr sowie die Armutsquote je Census `
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
  streulegende(document.getElementById("l-streuung"), d);

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
  document.getElementById("streuung-zurueck").addEventListener("click", () => {
    streuwahl.zoom = null;
    if (streuwahl.daten) streuung(document.getElementById("d-streuung"), streuwahl.daten);
  });
  const antwort = await fetch("/api/karten");
  if (antwort.ok) karten = await antwort.json();
  starteBrett({ api: "/api/sozial", zeichne });
}

start();
