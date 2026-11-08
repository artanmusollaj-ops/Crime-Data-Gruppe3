// Das Brett »Quellbewegung«.
import { FARBE, MONATE, balken, el, komma, leer, legende, runde, starteBrett, zahl } from "./gemeinsam.js";

const ARTNAME = { entfernt: "Entfernt", geaendert: "Geändert", neu: "Neu" };
const tag = (iso) => new Date(iso).toLocaleDateString("de-CH");
const prozent = (v) => (v === null || v === undefined ? "–" : `${komma.format(v)} %`);
const rate = (v) => (v === null || v === undefined ? "–" : komma.format(v));

function pwert(p) {
  if (p === null) return "–";
  if (p < 0.001) return "< 0,001";
  return p.toFixed(3).replace(".", ",");
}

function zelle(tr, text, klasse) {
  const td = tr.insertCell();
  td.textContent = text;
  if (klasse) td.className = klasse;
  return td;
}

function kopf(tabelle, spalten) {
  tabelle.replaceChildren();
  const tr = tabelle.createTHead().insertRow();
  for (const s of spalten) tr.append(Object.assign(document.createElement("th"), { textContent: s }));
  return tabelle.createTBody();
}

function kacheln(d) {
  const summe = (feld) => d.staedte.reduce((a, s) => a + s[feld], 0);
  const je = (feld) => d.staedte.map((s) => `${s.name} ${zahl.format(s[feld])}`).join(" · ");
  const raten = (feld) => d.staedte.map((s) => `${s.name} ${rate(s.je_10000[feld])}`).join(" · ")
    + " je 10'000 Einträge und Monat";
  document.getElementById("k-paare").textContent = zahl.format(summe("paare"));
  const von = d.staedte.map((s) => s.von).filter(Boolean).sort()[0];
  const bis = d.staedte.map((s) => s.bis).filter(Boolean).sort().at(-1);
  document.getElementById("k-paare-text").textContent =
    von ? `${je("paare")}; ${tag(von)} bis ${tag(bis)}` : "Noch kein Paar zweier Vollabzüge";
  for (const feld of ["geaendert", "entfernt", "neu"]) {
    document.getElementById(`k-${feld}`).textContent = zahl.format(summe(feld));
    document.getElementById(`k-${feld}-text`).textContent =
      d.staedte.length > 1 ? `${je(feld)}. ${raten(feld)}` : raten(feld);
  }
}

function vergleich(d) {
  const tafel = document.getElementById("t-vergleich");
  tafel.hidden = !d.vergleich.length;
  if (!d.vergleich.length) return;
  const [a, b] = d.staedte;
  const rumpf = kopf(document.getElementById("d-vergleich"),
    ["Bewegung", `${a.name} (je 10'000)`, `${b.name} (je 10'000)`, "Faktor", "Bei gleicher Rate erwartet",
      "p-Wert", "Befund"]);
  for (const v of d.vergleich) {
    const tr = rumpf.insertRow();
    zelle(tr, ARTNAME[v.art]);
    for (const s of [a, b]) {
      zelle(tr, `${zahl.format(v.anzahl[s.stadt])} (${rate(v.rate[s.stadt])})`, "zahl");
    }
    zelle(tr, v.faktor === null ? "–" : `${komma.format(v.faktor)}-fach`, "zahl");
    zelle(tr, v.erwartet ? `${a.name} ${komma.format(v.erwartet[0])} · ${b.name} ${komma.format(v.erwartet[1])}`
      : "–", "zahl");
    zelle(tr, pwert(v.p_wert), "zahl");
    const hoeher = d.staedte.find((s) => s.stadt === v.auffaellig);
    const befund = zelle(tr, v.p_wert === null ? "Keine Ereignisse"
      : hoeher ? `${hoeher.name} auffällig höher` : "Kein auffälliger Unterschied",
    hoeher ? "teil" : "ok");
    befund.title = v.p_wert === null ? "" : `Unter gleicher Rate wäre ein so ungleiches Ergebnis `
      + `mit Wahrscheinlichkeit ${pwert(v.p_wert)} zu sehen.`;
  }
}

// Je Stadt eine eigene Balkenliste: Die Felder heissen in beiden Quellen anders.
function felder(ziel, d) {
  ziel.replaceChildren();
  for (const s of d.staedte) {
    const zeilen = d.felder[s.stadt] || [];
    const block = document.createElement("div");
    block.className = `feldblock ${s.stadt}`;
    block.append(Object.assign(document.createElement("h3"), { textContent: s.name }));
    const flaeche = document.createElement("div");
    flaeche.className = "diagramm klein";
    block.append(flaeche);
    ziel.append(block);
    if (!zeilen.length) {
      leer(flaeche, "Keine Feldänderung");
      continue;
    }
    const b = Math.max(flaeche.clientWidth, 320), l = 190, r = 56, hoehe = 16, luecke = 6, u = 22;
    const h = zeilen.length * (hoehe + luecke) + u;
    const max = runde(Math.max(1, ...zeilen.map((z) => z.anteil ?? 0)));
    const x = (v) => l + ((b - l - r) * v) / max;
    const svg = el("svg", { viewBox: `0 0 ${b} ${h}`, role: "img" });
    for (let k = 0; k <= 4; k++) {
      const v = (max * k) / 4;
      svg.append(el("line", { x1: x(v), x2: x(v), y1: 0, y2: h - u, class: "achse" }));
      svg.append(el("text", { x: x(v), y: h - 6, "text-anchor": "middle" }, `${Math.round(v)} %`));
    }
    zeilen.forEach((z, i) => {
      const y = i * (hoehe + luecke);
      svg.append(el("text", { x: l - 8, y: y + hoehe - 3, "text-anchor": "end",
        class: z.stempel ? "leise-text" : "" }, z.stempel ? `${z.feld} (Stempel)` : z.feld));
      const rect = el("rect", { x: l, y, width: Math.max(0, x(z.anteil ?? 0) - l), height: hoehe, rx: 2,
        fill: FARBE[s.stadt], "fill-opacity": z.stempel ? 0.4 : 1 });
      rect.append(el("title", {}, `${s.name}, ${z.feld}: ${zahl.format(z.aenderungen)} Änderungen, `
        + `an ${prozent(z.anteil)} der geänderten Einträge`));
      svg.append(rect);
      svg.append(el("text", { x: x(z.anteil ?? 0) + 6, y: y + hoehe - 3, class: "wert" }, prozent(z.anteil)));
    });
    flaeche.replaceChildren(svg);
  }
}

function haeufigkeit(d) {
  const namen = { 1: "einmal", 2: "zweimal", "3+": "dreimal und öfter" };
  const zeilen = Object.entries(namen).map(([k, name]) => ({
    name, werte: Object.fromEntries(d.staedte.map((s) => [s.stadt, d.haeufigkeit[s.stadt][k]])) }));
  balken(document.getElementById("d-haeufigkeit"), zeilen, d.staedte, zahl.format);
  legende(document.getElementById("l-haeufigkeit"),
    d.staedte.map((s) => ({ name: s.name, klasse: s.stadt })));
  const rumpf = kopf(document.getElementById("d-uebergaenge"), ["Stadt", "Feld", "Vorher → nachher", "Anzahl"]);
  const kurz = (t) => (t === null ? "leer" : t.length > 40 ? `${t.slice(0, 39)}…` : t);
  for (const u of d.uebergaenge) {
    const tr = rumpf.insertRow();
    zelle(tr, d.staedte.find((s) => s.stadt === u.stadt).name, `stadtname ${u.stadt}`);
    zelle(tr, u.feld);
    zelle(tr, `${kurz(u.alt)} → ${kurz(u.neu)}`).title = `${u.alt ?? "leer"} → ${u.neu ?? "leer"}`;
    zelle(tr, zahl.format(u.anzahl), "zahl");
  }
  if (!d.uebergaenge.length) zelle(rumpf.insertRow(), "Keine inhaltliche Änderung").colSpan = 4;
}

function kategorien(d) {
  const e = d.entfernt;
  const spalten = ["Kategorie"];
  for (const s of d.staedte) spalten.push(`${s.name}: entfernt`, `${s.name}: Anteil Taten`);
  const rumpf = kopf(document.getElementById("d-kategorien"), spalten);
  for (const k of e.kategorien) {
    const tr = rumpf.insertRow();
    zelle(tr, k.name);
    for (const s of d.staedte) {
      const n = k.anzahl[s.stadt];
      zelle(tr, n ? `${zahl.format(n)} (${prozent(k.anteil[s.stadt])})` : "–", "zahl");
      // Stellt eine Kategorie bei den Loeschungen ein Vielfaches ihres
      // Anteils an den Taten, ist sie hervorgehoben.
      const ueber = n && k.anteil_taten[s.stadt] !== null && k.anteil[s.stadt] >= 3 * k.anteil_taten[s.stadt];
      zelle(tr, prozent(k.anteil_taten[s.stadt]), ueber ? "zahl rauf" : "zahl");
    }
  }
  if (!e.kategorien.length) zelle(rumpf.insertRow(), "Kein Eintrag entfernt").colSpan = spalten.length;
  const h = document.getElementById("h-konzentration");
  const saetze = d.staedte.filter((s) => e.konzentration[s.stadt]).map((s) => {
    const k = e.konzentration[s.stadt];
    return `${s.name}: ${zahl.format(e.gesamt[s.stadt])} entfernte Einträge aus ${k.kategorien} `
      + `${k.kategorien === 1 ? "Kategorie" : "Kategorien"}, am häufigsten ${k.haeufigste} (${prozent(k.anteil)}).`;
  });
  h.hidden = !saetze.length;
  h.textContent = saetze.join(" ") + (saetze.length ? " Rot: mindestens dreimal so häufig gelöscht, "
    + "wie die Kategorie unter den Taten vorkommt." : "");
}

function paare(d) {
  const rumpf = kopf(document.getElementById("d-paare"),
    ["Stadt", "Zeitraum", "Tage", "Bestand", "Geändert", "Entfernt", "Neu"]);
  for (const p of d.paare) {
    const tr = rumpf.insertRow();
    zelle(tr, d.staedte.find((s) => s.stadt === p.stadt).name, `stadtname ${p.stadt}`);
    zelle(tr, `${tag(p.von)} – ${tag(p.bis)}`);
    zelle(tr, komma.format(p.tage), "zahl");
    zelle(tr, p.bestand === null ? "unbekannt" : zahl.format(p.bestand), "zahl");
    for (const f of ["geaendert", "entfernt", "neu"]) zelle(tr, zahl.format(p[f]), "zahl");
  }
}

function liste(d) {
  const rumpf = kopf(document.getElementById("d-liste"),
    ["Stadt", "Eintrag", "Deliktsart der Quelle", "Code", "NIBRS-Kategorie", "Verschwunden zwischen"]);
  for (const z of d.entfernt.liste) {
    const tr = rumpf.insertRow();
    zelle(tr, z.name, `stadtname ${z.stadt}`);
    zelle(tr, z.offense_id);
    zelle(tr, z.quellkategorie ?? "unbekannt");
    zelle(tr, z.code ?? "–");
    zelle(tr, z.kategorie ?? "–");
    zelle(tr, `${tag(z.von)} und ${tag(z.bis)}`);
  }
  if (!d.entfernt.liste.length) zelle(rumpf.insertRow(), "Kein Eintrag entfernt").colSpan = 6;
}

// Die Filter kennt erst die Antwort des Bretts: welche Jahrgaenge und Monate es gibt.
const monat = (m) => `${MONATE[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}`;

function fuelle(id, eintraege, wert) {
  const select = document.getElementById(id);
  select.replaceChildren(...eintraege.map(([w, name]) => new Option(name, w, false, String(w) === String(wert))));
}

// Ohne Paare - das Release fuehrt die Tabelle nicht, oder es gibt noch kein
// Paar - gibt es nichts zu waehlen. Die Felder sind dann ausgegraut und sagen
// es, statt leer und scheinbar kaputt dazustehen. Ein gesperrtes Feld schickt
// das Formular nicht mit; die Anfrage nimmt dann die Vorgabe.
function sperre(id, gesperrt, grund) {
  const select = document.getElementById(id);
  select.disabled = gesperrt;
  select.title = gesperrt ? grund : "";
  if (gesperrt) select.replaceChildren(new Option("keine Daten", "", true, true));
}

function filter(d) {
  const o = d.optionen || { jahrgaenge: [], monate: [] }, a = d.auswahl;
  const grund = d.vorhanden ? "Für diese Auswahl gibt es kein Vergleichspaar."
    : "Das aktive Release führt die Quellbewegung noch nicht.";
  if (o.jahrgaenge.length) {
    sperre("q-jahrgang", false);
    fuelle("q-jahrgang", [["alle", "Alle"], ...o.jahrgaenge.map((j) => [j, String(j)])], a.jahrgang);
  } else sperre("q-jahrgang", true, grund);
  for (const [id, wert] of [["q-von", a.beob_von], ["q-bis", a.beob_bis]]) {
    if (o.monate.length) {
      sperre(id, false);
      fuelle(id, o.monate.map((m) => [m, monat(m)]), wert);
    } else sperre(id, true, grund);
  }
}

// Vor dem ersten Laden: was die Adresse sagt, als einzige Option - sonst
// faende die erste Anfrage leere Felder und vergaesse die Auswahl.
const adresse = new URLSearchParams(location.search);
for (const [id, name] of [["q-jahrgang", "jahrgang"], ["q-von", "beob_von"], ["q-bis", "beob_bis"]]) {
  if (adresse.get(name)) fuelle(id, [[adresse.get(name), adresse.get(name)]], adresse.get(name));
}
document.getElementById("leiste").addEventListener("change", (ev) => {
  // Von nach Bis gezogen: Bis rueckt nach, und umgekehrt.
  const von = document.getElementById("q-von"), bis = document.getElementById("q-bis");
  if (von.value > bis.value) {
    if (ev.target === von) bis.value = von.value; else von.value = bis.value;
  }
}, true);

function zeichne(d) {
  filter(d);
  document.getElementById("ohne-tabelle").hidden = d.vorhanden;
  document.getElementById("inhalt").hidden = !d.vorhanden;
  if (!d.vorhanden) return;
  kacheln(d);
  vergleich(d);
  felder(document.getElementById("d-felder"), d);
  haeufigkeit(d);
  kategorien(d);
  paare(d);
  liste(d);
}

starteBrett({ api: "/api/quellbewegung", zeichne });
