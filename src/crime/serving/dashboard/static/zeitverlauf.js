// Das Brett »Zeitverlauf«.
import {
  FARBE, MONATE, el, komma, legende, linie, starteBrett, zahl, zeitraumtext,
} from "./gemeinsam.js";

// Hell nach dunkel in der Farbe der Stadt: Weiss gemischt mit der Stadtfarbe.
function ton(farbe, anteil) {
  const rgb = [1, 3, 5].map((i) => parseInt(farbe.slice(i, i + 2), 16));
  const t = 0.08 + 0.92 * Math.min(1, Math.max(0, anteil));
  return `rgb(${rgb.map((c) => Math.round(255 + (c - 255) * t)).join(",")})`;
}

function heatmap(stadt, wochentage) {
  const h = stadt.heatmap, farbe = FARBE[stadt.stadt];
  const zelle = 15, l = 26, o = 4, unten = 72, b = l + 24 * zelle + 6;
  const hoehe = o + 7 * zelle + unten;
  const svg = el("svg", { viewBox: `0 0 ${b} ${hoehe}`, role: "img",
    "aria-label": `${stadt.name}: Fälle je Wochentag und Stunde` });
  h.werte.forEach((zeile, w) => {
    svg.append(el("text", { x: l - 6, y: o + w * zelle + 11, "text-anchor": "end" }, wochentage[w]));
    zeile.forEach((v, s) => {
      const r = el("rect", { x: l + s * zelle, y: o + w * zelle, width: zelle - 1, height: zelle - 1,
        fill: ton(farbe, h.max ? v / h.max : 0) });
      r.append(el("title", {}, `${stadt.name}, ${wochentage[w]} ${s}–${s + 1} Uhr: `
        + `Ø ${komma.format(v)} Fälle`));
      svg.append(r);
    });
  });
  for (let s = 0; s < 24; s += 2) {
    svg.append(el("text", { x: l + s * zelle + zelle / 2, y: o + 7 * zelle + 13,
      "text-anchor": "middle" }, String(s)));
  }
  svg.append(el("text", { x: l + 12 * zelle, y: o + 7 * zelle + 28, "text-anchor": "middle",
    class: "achsentitel" }, "Lokale Uhrzeit (Stunde)"));
  // Die Skala: zehn Stufen von 0 bis zum Hoechstwert dieser Stadt.
  const sy = o + 7 * zelle + 38, sb = 24 * zelle * 0.8, sx = l + 24 * zelle * 0.1;
  for (let i = 0; i < 10; i++) {
    svg.append(el("rect", { x: sx + (i * sb) / 10, y: sy, width: sb / 10, height: 10,
      fill: ton(farbe, (i + 0.5) / 10) }));
  }
  svg.append(el("text", { x: sx, y: sy + 23, "text-anchor": "middle" }, "0"));
  svg.append(el("text", { x: sx + sb, y: sy + 23, "text-anchor": "middle" }, komma.format(h.max)));
  svg.append(el("text", { x: sx + sb / 2, y: sy + 23, "text-anchor": "middle", class: "achsentitel" },
    "Ø Fälle pro Stunde"));
  const kasten = document.createElement("div");
  kasten.className = `heatmap ${stadt.stadt}`;
  const titel = document.createElement("h3");
  titel.textContent = stadt.name;
  kasten.append(titel, svg);
  return kasten;
}

function verlaufstafel(s, d) {
  const tafel = document.createElement("article");
  tafel.className = `tafel stadt ${s.stadt}`;
  const h2 = document.createElement("h2");
  h2.textContent = s.name;
  const u = document.createElement("p");
  u.className = "unterzeile";
  u.textContent = `Monatliche Fallzahlen (${zeitraumtext(d.auswahl, "").trim()})`;
  const ziel = document.createElement("div");
  ziel.className = "diagramm";
  const leg = document.createElement("div");
  leg.className = "legende";
  tafel.append(h2, u, ziel, leg);
  document.getElementById("verlaeufe").append(tafel);
  const reihen = [{ name: String(d.vergleich.jahr), farbe: FARBE[s.stadt], werte: s.jetzt, status: s.status }];
  const eintraege = [{ name: zeitraumtext(d.auswahl), klasse: `${s.stadt} voll` }];
  if (d.vergleich.vorjahr_vorhanden) {
    reihen.push({ name: String(d.vergleich.vorjahr), farbe: FARBE[s.stadt], werte: s.vorjahr,
      status: s.status_vorjahr, gestrichelt: true });
    eintraege.push({ name: zeitraumtext(d.auswahl, d.vergleich.vorjahr), klasse: `${s.stadt} punktiert` });
  }
  linie(ziel, s.monate, reihen);
  legende(leg, eintraege);
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  document.getElementById("m-vergleich").textContent = d.vergleich.vorjahr_vorhanden
    ? `${zr} im Vergleich zu ${zeitraumtext(d.auswahl, d.vergleich.vorjahr)}`
    : `${zr}, kein Vorjahr im Bestand`;
  document.getElementById("verlaeufe").replaceChildren();
  d.staedte.forEach((s) => verlaufstafel(s, d));

  document.getElementById("u-heatmap").textContent =
    `Durchschnittliche Anzahl Fälle pro Stunde (${zr})`;
  document.getElementById("d-heatmaps").replaceChildren(...d.staedte.map((s) => heatmap(s, d.wochentage)));
  document.getElementById("t-platzhalter").textContent = "Ohne Fälle mit Tatzeit genau 00:00 oder "
    + "12:00 – dort häufen sich Platzhalter für eine unbekannte Uhrzeit: "
    + d.staedte.map((s) => `${s.name} ${zahl.format(s.heatmap.platzhalter)} `
      + `(${s.heatmap.platzhalter_anteil === null ? "–" : komma.format(s.heatmap.platzhalter_anteil)} %)`)
      .join(", ") + ".";

  const basen = [...new Set(d.staedte.map((s) => s.index.basis).filter(Boolean))];
  const basis = basen.length === 1 ? MONATE[Number(basen[0].split("-")[1]) - 1] : "erster voller Monat";
  document.getElementById("t-index").textContent = `Entwicklung im Vergleich · ${basis} = 100`;
  document.getElementById("u-index").textContent = `Index der monatlichen Fallzahlen (${zr})`;
  linie(document.getElementById("d-index"), d.staedte[0].monate,
    d.staedte.map((s) => ({ name: s.name, farbe: FARBE[s.stadt], werte: s.index.werte, status: s.status })),
    { basis: 100, format: (v) => komma.format(v) });
  legende(document.getElementById("l-index"), [
    ...d.staedte.map((s) => ({ name: s.name, klasse: s.stadt })),
    { name: `Basis (${basis} = 100)`, klasse: "basislinie" },
  ]);
}

starteBrett({ api: "/api/zeitverlauf", zeichne });
