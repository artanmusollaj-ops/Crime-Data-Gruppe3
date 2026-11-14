// Das Brett »Überblick«.
import {
  FARBE, achsenzahl, balken, komma, legende, linie, monatsname, starteBrett, zahl, zeitraumtext,
} from "./gemeinsam.js";

function abdeckung(ziel, staedte) {
  ziel.replaceChildren(...staedte.map((s) => {
    const karte = document.createElement("div");
    karte.className = `stadtkarte ${s.stadt}`;
    const h3 = document.createElement("h3");
    h3.textContent = s.name;
    const tabelle = document.createElement("table");
    const letzter = s.letzter_tag ? new Date(s.letzter_tag).toLocaleDateString("de-CH") : "–";
    const zeilen = [
      ["Zeitraum mit Daten", s.von ? `${monatsname(s.von)} – ${monatsname(s.bis)}` : "keine Daten"],
      ["Vollständige Monate", `${s.vollstaendig} / ${s.monate.length}`, s.vollstaendig === s.monate.length],
      ["Letzter Tag im Bestand", letzter],
      ["Datenstatus", { vollstaendig: "Vollständig", unvollstaendig: "Teilweise", keine_daten: "Keine Daten" }[s.status],
        s.status === "vollstaendig"],
    ];
    for (const [etikett, wert, gut] of zeilen) {
      const tr = tabelle.insertRow();
      tr.insertCell().textContent = etikett;
      const td = tr.insertCell();
      td.textContent = wert;
      if (gut !== undefined) td.className = gut ? "ok" : "teil";
    }
    karte.append(h3, tabelle);
    return karte;
  }));
}

function zeichne(d) {
  const k = d.kennzahlen;
  const staedte = d.verlauf.reihen.map((r) => ({ stadt: r.stadt, name: r.name }));
  document.getElementById("k-delikte").textContent = zahl.format(k.delikte);
  document.getElementById("k-faelle").textContent = zahl.format(k.faelle);
  const vj = document.getElementById("k-vorjahr");
  vj.className = k.vorjahr_prozent === null ? "" : k.vorjahr_prozent < 0 ? "runter" : "rauf";
  vj.textContent = k.vorjahr_prozent === null ? "nicht vergleichbar"
    : `${k.vorjahr_prozent < 0 ? "↓ −" : "↑ +"}${komma.format(Math.abs(k.vorjahr_prozent))} %`;
  vj.title = k.vorjahr_monate < k.monate
    ? `Über ${k.vorjahr_monate} von ${k.monate} Monaten, die in beiden Jahren vollständig vorliegen`
    : "Dieselben Monate im Vorjahr";
  document.getElementById("k-vorjahr-basis").textContent = k.vorjahr_monate < k.monate
    ? `über ${k.vorjahr_monate} vergleichbare Monate` : "";
  document.getElementById("k-monate").textContent = `${k.vollstaendige_monate} / ${k.monate}`;

  const zr = zeitraumtext(d.auswahl);
  linie(document.getElementById("d-verlauf"), d.verlauf.monate,
    d.verlauf.reihen.map((r) => ({ ...r, farbe: FARBE[r.stadt] })));
  document.getElementById("t-raten").textContent = `Fälle je 1'000 Einwohner · ${zr}`;
  const e = d.raten.einwohner;
  document.getElementById("u-raten").textContent = "Bevölkerungsbasis: " + (Object.keys(e).length
    ? staedte.map((s) => `${s.name} ${zahl.format(e[s.stadt])}`).join(", ") + " (ACS)"
    : "keine einheitliche – Rate nicht definiert");
  balken(document.getElementById("d-raten"), d.raten.zeilen, staedte, (v) => komma.format(v),
    achsenzahl);
  // Fallebene vorn, Tatebene daneben (Entscheid E5): Chicago erfasst je Fall
  // nur das schwerste Delikt, Detroit jedes.
  const tat = d.raten.tatebene;
  const tatebene = document.getElementById("h-tatebene");
  tatebene.hidden = !staedte.some((s) => tat[s.stadt] !== null);
  const symbol = document.createElement("span");
  symbol.className = "i";
  symbol.textContent = "i";
  const text = document.createElement("span");
  tatebene.replaceChildren(symbol, text);
  text.textContent = "Tatebene, alle Delikte je 1'000: "
    + staedte.map((s) => `${s.name} ${tat[s.stadt] === null ? "–" : komma.format(tat[s.stadt])}`)
      .join(" · ")
    + ". Detroit erfasst jedes Delikt eines Falls, Chicago nur das schwerste – "
    + "vorn steht deshalb der Fall.";
  const titel = { anzahl: "Registrierte Delikte", anteil: "Anteil an allen Delikten",
    rate: "Delikte je 1'000 Einwohner" }[d.kategorien.mass];
  document.getElementById("t-kategorien").textContent = `${titel} nach Kategorie · ${zr}`;
  const format = d.kategorien.mass === "anzahl" ? (v) => zahl.format(v)
    : d.kategorien.mass === "anteil" ? (v) => `${komma.format(v)} %` : (v) => komma.format(v);
  balken(document.getElementById("d-kategorien"), d.kategorien.zeilen, staedte, format,
    d.kategorien.mass === "anteil" ? (v) => `${achsenzahl(v)} %` : achsenzahl);
  abdeckung(document.getElementById("d-abdeckung"), d.abdeckung);
  const eintraege = staedte.map((s) => ({ name: s.name, klasse: s.stadt }));
  document.querySelectorAll(".tafel .legende").forEach((l) => legende(l, eintraege));
}

starteBrett({ api: "/api/ueberblick", zeichne });
