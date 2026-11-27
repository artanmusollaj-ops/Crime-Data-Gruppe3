// Das Brett »Überblick«.
import {
  FARBE, JE_PERIODE, PERIODEN, achsenzahl, balken, hochrechnung, komma, legende, linie, periodentext,
  starteBrett, zahl, zeitraumtext,
} from "./gemeinsam.js";

function abdeckung(ziel, staedte, koernung) {
  ziel.replaceChildren(...staedte.map((s) => {
    const karte = document.createElement("div");
    karte.className = `stadtkarte ${s.stadt}`;
    const h3 = document.createElement("h3");
    h3.textContent = s.name;
    const tabelle = document.createElement("table");
    const letzter = s.letzter_tag ? new Date(s.letzter_tag).toLocaleDateString("de-CH") : "–";
    const zeilen = [
      ["Zeitraum mit Daten", s.von
        ? `${periodentext(s.von, koernung)} – ${periodentext(s.bis, koernung)}` : "keine Daten"],
      [`Vollständige ${PERIODEN[koernung]}`, `${s.vollstaendig} / ${s.monate.length}`,
        s.vollstaendig === s.monate.length],
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
  // Verglichen wird ueber die Tage, die in beiden Jahren fuer jede Stadt
  // vorliegen; ueber mehr als ein Jahr Spanne gar nicht.
  const teilweise = k.vorjahr_tage > 0 && k.vorjahr_tage < k.tage;
  vj.title = !k.vorjahr_moeglich ? "Kein Vorjahresvergleich über mehr als ein Jahr Spanne"
    : teilweise ? `Über ${zahl.format(k.vorjahr_tage)} von ${zahl.format(k.tage)} Tagen, `
      + "die in beiden Jahren für jede gewählte Stadt vorliegen"
    : "Derselbe Zeitraum ein Jahr früher";
  document.getElementById("k-vorjahr-basis").textContent = !k.vorjahr_moeglich ? "Spanne über ein Jahr"
    : teilweise ? `über ${zahl.format(k.vorjahr_tage)} vergleichbare Tage` : "";
  const kachel = document.getElementById("k-monate");
  kachel.previousElementSibling.textContent = `Vollständige ${PERIODEN[d.achse.koernung]}`;
  kachel.textContent = `${k.vollstaendige_monate} / ${k.monate}`;

  const zr = zeitraumtext(d.auswahl);
  document.getElementById("t-verlauf").textContent =
    `${JE_PERIODE[d.achse.koernung]} Entwicklung registrierter Delikte`;
  linie(document.getElementById("d-verlauf"), d.verlauf.monate,
    d.verlauf.reihen.map((r) => ({ ...r, farbe: FARBE[r.stadt] })), { koernung: d.achse.koernung });
  // Je Jahr (serving.dashboard.zeitraum): Ueber weniger als ein Jahr steht
  // dabei, aus wie vielen Tagen hochgerechnet ist.
  const hoch = hochrechnung(d.raten.tage);
  document.getElementById("t-raten").textContent = `Fälle je 1'000 Einwohner und Jahr · ${zr}`
    + (hoch ? ` · ${hoch}` : "");
  const e = d.raten.einwohner, pj = d.raten.personenjahre;
  document.getElementById("u-raten").textContent = "Bevölkerungsbasis: " + (Object.keys(e).length
    ? staedte.map((s) => `${s.name} ${zahl.format(e[s.stadt])}`).join(", ") + " (ACS)"
    : Object.keys(pj).length
      ? staedte.map((s) => `${s.name} ${zahl.format(pj[s.stadt])}`).join(", ")
        + " Personenjahre (ACS, mehrere Jahrgänge)"
      : "keine einheitliche – Rate nicht definiert");
  // Fallebene vorn, Tatebene daneben (Entscheid E5): Chicago erfasst je Fall
  // nur das schwerste Delikt, Detroit jedes. Die Tatebene steht als zweite,
  // blasse Zeile im selben Massstab.
  const fall = d.raten.zeilen[0];
  balken(document.getElementById("d-raten"),
    [fall, { kategorie: "tatebene", name: "Delikte (Tatebene)", werte: d.raten.tatebene,
      blass: true }],
    staedte, (v) => komma.format(v), achsenzahl, { balkenhoehe: 26, abstand: 30 });
  const tatebene = document.getElementById("h-tatebene");
  const symbol = document.createElement("span");
  symbol.className = "i";
  symbol.textContent = "i";
  const text = document.createElement("span");
  text.textContent = "Vorn steht der Fall, blass daneben die Tatebene: Detroit erfasst jedes "
    + "Delikt eines Falls, Chicago nur das schwerste. Auf der Tatebene misst ein Vergleich "
    + "diesen Unterschied mit.";
  tatebene.replaceChildren(symbol, text);
  const titel = { anzahl: "Registrierte Delikte", anteil: "Anteil an allen Delikten",
    rate: "Delikte je 1'000 Einwohner und Jahr" }[d.kategorien.mass];
  document.getElementById("t-kategorien").textContent = `${titel} nach Kategorie · ${zr}`;
  const format = d.kategorien.mass === "anzahl" ? (v) => zahl.format(v)
    : d.kategorien.mass === "anteil" ? (v) => `${komma.format(v)} %` : (v) => komma.format(v);
  balken(document.getElementById("d-kategorien"), d.kategorien.zeilen, staedte, format,
    d.kategorien.mass === "anteil" ? (v) => `${achsenzahl(v)} %` : achsenzahl);
  abdeckung(document.getElementById("d-abdeckung"), d.abdeckung, d.achse.koernung);
  const eintraege = staedte.map((s) => ({ name: s.name, klasse: s.stadt }));
  document.querySelectorAll(".tafel .legende").forEach((l) => legende(l, eintraege));
}

starteBrett({ api: "/api/ueberblick", zeichne });
