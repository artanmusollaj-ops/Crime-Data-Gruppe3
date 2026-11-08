// Das Brett »Wetter«.
import { FARBE, balken, el, komma, leer, legende, linie, starteBrett } from "./gemeinsam.js";

const prozent = (v) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${komma.format(v)} %`);
const zweistellig = (v) => (v === null || v === undefined ? "–"
  : `${v > 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")} %`);
const grad = (v) => (v === null || v === undefined ? "–" : `${komma.format(v)} °C`);

// Divergierende Balken um null: je Band eine Gruppe, je Stadt ein Balken.
// Ein Band mit zu wenigen Tagen ist blass - sein Mittel traegt wenig.
function divergierend(ziel, staedte, schluessel, mindest) {
  const baender = staedte[0][schluessel].map((z) => z.band);
  const werte = staedte.flatMap((s) => s[schluessel].map((z) => z.prozent).filter((v) => v !== null));
  if (!werte.length) return leer(ziel, "Zu wenige Tage in dieser Auswahl");
  const b = Math.max(ziel.clientWidth, 320), l = 150, r = 60, o = 6, u = 26;
  const hoehe = 14, luecke = 3, gruppe = staedte.length * (hoehe + luecke) + 14;
  const h = o + baender.length * gruppe + u;
  const weite = Math.max(2, ...werte.map(Math.abs));
  // Ein Drittel Luft, damit die Zahl neben dem laengsten Balken nicht in die
  // Beschriftung der Baender laeuft; hoechstens drei Teilstriche je Seite.
  const roh = weite * 1.35;
  const schritt = [1, 2, 5, 10, 20, 50].find((c) => roh / c <= 3) ?? 100;
  const grenze = Math.ceil(roh / schritt) * schritt;
  const x = (v) => l + ((b - l - r) * (v + grenze)) / (2 * grenze);
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let v = -grenze; v <= grenze; v += schritt) {
    svg.append(el("line", { x1: x(v), x2: x(v), y1: o, y2: h - u, class: v === 0 ? "basis" : "achse" }));
    svg.append(el("text", { x: x(v), y: h - 8, "text-anchor": "middle" }, `${v > 0 ? "+" : ""}${v} %`));
  }
  baender.forEach((band, i) => {
    const y0 = o + i * gruppe;
    svg.append(el("text", { x: l - 10, y: y0 + (staedte.length * (hoehe + luecke)) / 2 + 4,
      "text-anchor": "end" }, band));
    staedte.forEach((s, j) => {
      const z = s[schluessel][i], v = z.prozent;
      const y = y0 + j * (hoehe + luecke);
      if (v === null) return;
      const rect = el("rect", { x: Math.min(x(0), x(v)), y, width: Math.abs(x(v) - x(0)), height: hoehe,
        rx: 2, fill: FARBE[s.stadt], "fill-opacity": z.tage < mindest ? 0.35 : 1 });
      rect.append(el("title", {}, `${s.name}, ${band}: ${prozent(v)} gegenüber dem Monatsmittel (${z.tage} Tage)`));
      svg.append(rect);
      svg.append(el("text", { x: v >= 0 ? x(v) + 6 : x(v) - 6, y: y + hoehe - 3, class: "wert",
        "text-anchor": v >= 0 ? "start" : "end" }, prozent(v)));
    });
  });
  ziel.replaceChildren(svg);
}

function kacheln(ziel, staedte) {
  ziel.replaceChildren();
  for (const s of staedte) {
    const e = s.effekt, nass = (s.niederschlag || []).find((z) => z.band === "nass");
    const kachel = document.createElement("div");
    kachel.className = `kachel stadtkachel ${s.stadt}`;
    const text = document.createElement("div");
    const zeilen = [
      ["etikett", `${s.name}: je Grad wärmer als der Monat`],
      ["b", e ? zweistellig(e.je_grad) : "–"],
      ["small", e ? `95-%-Intervall ${zweistellig(e.von)} bis ${zweistellig(e.bis)} · r = ${komma.format(e.r)} `
        + `(ohne Bereinigung ${s.r_roh === null ? "–" : komma.format(s.r_roh)}) · ${e.tage} Tage`
        : "Zu wenige Tage für eine Schätzung"],
      ["small", `${komma.format(s.faelle_je_tag ?? 0)} Fälle je Tag; an nassen Tagen ${prozent(nass?.prozent)}`],
    ];
    for (const [art, inhalt] of zeilen) {
      const e2 = document.createElement(art === "etikett" ? "span" : art);
      if (art === "etikett") e2.className = "etikett";
      e2.textContent = inhalt;
      text.append(e2);
    }
    kachel.append(text);
    ziel.append(kachel);
  }
}

function zeichne(d) {
  document.getElementById("ohne-wetter").hidden = d.vorhanden;
  document.getElementById("inhalt").hidden = !d.vorhanden;
  if (!d.vorhanden) return;
  const staedte = d.staedte.filter((s) => s.tage > 0);
  kacheln(document.getElementById("k-staedte"), d.staedte);
  const legendeStaedte = staedte.map((s) => ({ name: s.name, klasse: s.stadt }));
  if (!staedte.length) {
    for (const id of ["d-temperatur", "d-faelle", "d-roh", "d-abweichung", "d-niederschlag"]) {
      leer(document.getElementById(id), "Keine Tage mit Wetter in dieser Auswahl");
    }
    return;
  }

  const monate = [...new Set(staedte.flatMap((s) => s.monate.map((m) => m.monat)))].sort();
  const reihe = (s, feld) => monate.map((m) => s.monate.find((x) => x.monat === m)?.[feld] ?? null);
  linie(document.getElementById("d-temperatur"), monate,
    staedte.map((s) => ({ name: s.name, farbe: FARBE[s.stadt], werte: reihe(s, "tmax") })),
    { format: grad });
  linie(document.getElementById("d-faelle"), monate,
    staedte.map((s) => ({ name: s.name, farbe: FARBE[s.stadt], werte: reihe(s, "faelle_je_tag") })),
    { format: (v) => komma.format(v) });
  legende(document.getElementById("l-monate"), legendeStaedte);

  const zeilen = staedte[0].temperatur.map((z, i) => ({
    name: z.band,
    werte: Object.fromEntries(staedte.map((s) => [s.stadt, s.temperatur[i].faelle_je_tag])),
  })).filter((z) => Object.values(z.werte).some((v) => v !== null));
  balken(document.getElementById("d-roh"), zeilen, staedte, (v) => komma.format(v));
  legende(document.getElementById("l-roh"), legendeStaedte);

  divergierend(document.getElementById("d-abweichung"), staedte, "abweichung", d.mindesttage);
  legende(document.getElementById("l-abweichung"), legendeStaedte);
  document.getElementById("u-niederschlag").textContent =
    `Abweichung der Fälle vom Monatsmittel. Nass heisst ab ${komma.format(d.nass_mm)} mm, `
    + "Schnee jeder Tag mit Neuschnee";
  divergierend(document.getElementById("d-niederschlag"), staedte, "niederschlag", d.mindesttage);
  legende(document.getElementById("l-niederschlag"), legendeStaedte);
  document.getElementById("t-stationen").textContent =
    staedte.map((s) => `${s.name}: ${s.station}`).join(", ");
  document.getElementById("t-mindest").textContent = d.mindesttage;
}

starteBrett({ api: "/api/wetter", zeichne });
