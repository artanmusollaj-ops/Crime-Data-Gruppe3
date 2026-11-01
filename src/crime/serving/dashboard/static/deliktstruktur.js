// Das Brett »Deliktstruktur«.
import { achsenzahl, balken, el, komma, legende, starteBrett, zahl, zeitraumtext } from "./gemeinsam.js";

// Eine Farbe je Rang, nicht je Kategorie: Die Reihenfolge folgt der Auswahl.
// Die letzte, graue, gehoert der Restgruppe.
const RANGFARBEN = ["#d64545", "#f2b134", "#8e6bd8", "#ef7d32", "#173f7a"];
const REST = "#c9ced6";

function anteile(ziel, staedte) {
  const b = Math.max(ziel.clientWidth, 320), l = 80, r = 24, hoehe = 64, luecke = 26, u = 26;
  const h = staedte.length * (hoehe + luecke) + u;
  const x = (v) => l + ((b - l - r) * v) / 100;
  const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
  for (let k = 0; k <= 5; k++) {
    svg.append(el("line", { x1: x(k * 20), x2: x(k * 20), y1: 0, y2: h - u, class: "achse" }));
    svg.append(el("text", { x: x(k * 20), y: h - 8, "text-anchor": "middle" }, `${k * 20} %`));
  }
  staedte.forEach((s, i) => {
    const y = i * (hoehe + luecke) + luecke / 2;
    svg.append(el("text", { x: l - 10, y: y + hoehe / 2 + 4, "text-anchor": "end" }, s.name));
    let links = 0;
    s.teile.forEach((t, j) => {
      const farbe = j < RANGFARBEN.length && t.kategorie !== "Übrige Kategorien" ? RANGFARBEN[j] : REST;
      const rect = el("rect", { x: x(links), y, width: x(links + t.anteil) - x(links), height: hoehe, fill: farbe });
      rect.append(el("title", {}, `${s.name}, ${t.name}: ${komma.format(t.anteil)} %`));
      svg.append(rect);
      if (t.anteil >= 4) {
        svg.append(el("text", { x: x(links + t.anteil / 2), y: y + hoehe / 2 + 4, "text-anchor": "middle",
          class: farbe === REST || farbe === "#f2b134" ? "im-balken dunkel" : "im-balken" },
          `${Math.round(t.anteil)} %`));
      }
      links += t.anteil;
    });
  });
  ziel.replaceChildren(svg);
}

function veraenderung(v) {
  const span = document.createElement("span");
  if (v === null) {
    span.textContent = "–";
    span.className = "leise";
    return span;
  }
  span.textContent = `${v > 0 ? "↑ +" : v < 0 ? "↓ −" : "± "}${komma.format(Math.abs(v))} %`;
  span.className = v > 0 ? "rauf" : v < 0 ? "runter" : "";
  return span;
}

function tabelle(ziel, d) {
  const zr = zeitraumtext(d.auswahl);
  const kopf = ziel.createTHead().insertRow();
  const spalten = ["Kategorie", "NIBRS (häufigste Delikte)",
    ...d.staedte.map((s) => `${s.name}\n${zr}`),
    ...d.staedte.map((s) => `${s.name}\nzum Vorjahr`)];
  for (const s of spalten) {
    const th = document.createElement("th");
    const [oben, unten] = s.split("\n");
    th.textContent = oben;
    if (unten) th.append(Object.assign(document.createElement("small"), { textContent: unten }));
    kopf.append(th);
  }
  const rumpf = ziel.createTBody();
  for (const z of d.tabelle) {
    const tr = rumpf.insertRow();
    tr.insertCell().textContent = z.name;
    tr.insertCell().textContent = z.beispiele.join(", ");
    for (const s of d.staedte) {
      const td = tr.insertCell();
      td.textContent = zahl.format(z.werte[s.stadt]);
      td.className = "zahl";
    }
    for (const s of d.staedte) tr.insertCell().append(veraenderung(z.vorjahr[s.stadt]));
  }
}

function zeichne(d) {
  const zr = zeitraumtext(d.auswahl);
  const ebene = d.ebene === "faelle" ? "Fälle" : "Delikte";
  document.getElementById("h-ebene").hidden = d.ebene !== "delikte";
  document.getElementById("u-balken").textContent = `Anzahl ${ebene}, ${zr}`;
  const staedte = d.staedte.map((s) => ({ stadt: s.stadt, name: s.name }));
  balken(document.getElementById("d-balken"), d.balken, staedte, (v) => zahl.format(v), achsenzahl);
  legende(document.getElementById("l-balken"), staedte.map((s) => ({ name: s.name, klasse: s.stadt })));

  document.getElementById("u-anteile").textContent = `Verteilung der ${ebene} innerhalb der Stadt, ${zr}`;
  anteile(document.getElementById("d-anteile"), d.anteile);
  const teile = d.anteile.length ? d.anteile[0].teile : [];
  const leg = document.getElementById("l-anteile");
  legende(leg, teile.map((t, j) => ({ name: t.name, klasse: "rang" })));
  [...leg.children].forEach((span, j) => {
    span.style.setProperty("--farbe",
      j < RANGFARBEN.length && teile[j].kategorie !== "Übrige Kategorien" ? RANGFARBEN[j] : REST);
  });

  const t = document.getElementById("d-tabelle");
  t.replaceChildren();
  tabelle(t, d);
  const vergleich = d.staedte.map((s) => `${s.name} ${s.vergleichbare_monate} von ${d.monate}`).join(", ");
  document.getElementById("u-tabelle").textContent =
    (d.weitere ? `${d.weitere} weitere Kategorien nicht gezeigt. ` : "")
    + `Zum Vorjahr über die Monate, die in beiden Jahren vollständig vorliegen (${vergleich}); `
    + `unter ${d.mindestzahl} ${ebene} im Vorjahr bleibt die Veränderung leer.`;
}

starteBrett({ api: "/api/deliktstruktur", zeichne });
