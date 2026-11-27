// Was die Kartenbretter teilen: Hintergrundkacheln, Zoom und Verschieben.
//
// Die Tracts bleiben eigenes SVG aus Gold; darunter liegen die Standard-
// Rasterkacheln von OpenStreetMap, per CSS entfaerbt, damit nur die Tracts
// Farbe tragen. Die Kacheln sind Web-Mercator wie die Pfade aus
// ``geografie.pfade``; Kachel-URL und Kachelnummern nach OpenStreetMap Wiki,
// »Slippy map tilenames« (https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames).
// Die Nutzungsregeln (https://operations.osmfoundation.org/policies/tiles/)
// verlangen die Namensnennung und einen Referer - deshalb sendet das Dashboard
// seinen Ursprung mit (``Referrer-Policy`` in ``app.py``). CARTO, der erste
// Versuch, liefert seit 2025 ohne API-Schluessel nur noch »API KEY REQUIRED«.
import { el } from "./gemeinsam.js";

const KACHEL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const MAX_ZOOM = 16; // Vergroesserung gegenueber der ganzen Stadt
const MAX_KACHELSTUFE = 19;

function kachelurl(z, x, y) {
  return KACHEL.replace("{z}", z).replace("{x}", x).replace("{y}", y);
}

// Eine Kachelebene: haelt die Bilder je Schluessel, damit beim Verschieben
// nichts neu laedt, was schon da ist.
function kachelebene(k, klasse) {
  const g = el("g", { class: klasse, "aria-hidden": "true" });
  const da = new Map();
  return {
    g,
    // Kacheln der Stufe z fuer den Ausschnitt [ax, bx] x [ay, by] in Karteneinheiten.
    zeige(z, ax, ay, bx, by) {
      const n = 2 ** z, w = k.massstab / n;
      const welt = (v, null0) => null0 + v / k.massstab;
      const i0 = Math.max(0, Math.floor(welt(ax, k.x0) * n));
      const i1 = Math.min(n - 1, Math.floor(welt(bx, k.x0) * n));
      const j0 = Math.max(0, Math.floor(welt(ay, k.y0) * n));
      const j1 = Math.min(n - 1, Math.floor(welt(by, k.y0) * n));
      const noetig = new Set();
      for (let i = i0; i <= i1; i++) {
        for (let j = j0; j <= j1; j++) {
          const schluessel = `${z}/${i}/${j}`;
          noetig.add(schluessel);
          if (da.has(schluessel)) continue;
          // Ein Hauch Ueberlappung, sonst zeigen sich zwischen den Kacheln Haarlinien.
          const bild = el("image", {
            href: kachelurl(z, i, j), x: (i / n - k.x0) * k.massstab,
            y: (j / n - k.y0) * k.massstab, width: w * 1.004, height: w * 1.004,
            preserveAspectRatio: "none",
          });
          da.set(schluessel, bild);
          g.append(bild);
        }
      }
      for (const [schluessel, bild] of da) {
        if (!noetig.has(schluessel)) { bild.remove(); da.delete(schluessel); }
      }
    },
    leere() {
      for (const bild of da.values()) bild.remove();
      da.clear();
    },
  };
}

// Koppelt Karten derselben Stadt: Wer zoomt oder verschiebt, nimmt die
// anderen mit. Alle Mitglieder teilen ``k`` und damit dieselben Einheiten.
export function kopplung() {
  const mitglieder = new Set();
  return {
    melde(von, ansicht) {
      for (const m of mitglieder) if (m !== von) m(ansicht);
    },
    nimm(m) { mitglieder.add(m); },
  };
}

// Die Kartenflaeche: ``inhalt`` ist eine <g> mit den Tracts, ``defs`` die
// Muster dazu, ``gekoppelt`` optional eine ``kopplung()``. Gibt das
// <div class="kartenflaeche"> zurueck.
export function kartenflaeche(k, { titel, inhalt, defs, gekoppelt = null }) {
  const B = k.breite, H = k.hoehe;
  const svg = el("svg", { viewBox: `0 0 ${B} ${H}`, role: "img", "aria-label": titel });
  const ansicht = el("g", { class: "ansicht" });
  // Die ganze Stadt bleibt als grobe Ebene liegen; die feine laedt darueber nach.
  // So bleibt beim Zoomen nie eine leere Flaeche stehen.
  const grob = kachelebene(k, "kacheln");
  const fein = kachelebene(k, "kacheln");
  ansicht.append(grob.g, fein.g, inhalt);
  if (defs) svg.append(defs);
  svg.append(ansicht);

  // Massstab und Nordpfeil stehen fest und rechnen mit dem Zoom mit.
  const massstab = el("g", { class: "massstabsleiste" });
  const nord = el("g", { transform: `translate(${B - 16}, 14)` });
  nord.append(el("path", { d: "M0 0 L8 22 L0 16 L-8 22 Z", class: "nord" }),
    el("text", { x: 0, y: -3, "text-anchor": "middle", class: "kartenschrift" }, "N"));
  svg.append(massstab, nord);

  let s = 1, tx = 0, ty = 0, geplant = false;

  function leiste() {
    // Die groesste runde Strecke, die in ein Viertel der Breite passt.
    const kmJeEinheit = 1 / (k.km * s);
    const ziel = (B / 4) * kmJeEinheit;
    const stufen = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20];
    const km = stufen.filter((v) => v <= ziel).pop() ?? stufen[0];
    const l = km / kmJeEinheit, x = 12, y = H - 12;
    const text = km < 1 ? `${km * 1000} m` : `${km} km`;
    massstab.replaceChildren(
      el("rect", { x: x - 6, y: y - 20, width: l + 40 + 12, height: 28, rx: 3, class: "massstabsgrund" }),
      el("line", { x1: x, x2: x + l, y1: y, y2: y, class: "massstab" }),
      el("line", { x1: x, x2: x, y1: y - 4, y2: y + 4, class: "massstab" }),
      el("line", { x1: x + l, x2: x + l, y1: y - 4, y2: y + 4, class: "massstab" }),
      el("text", { x: x + l + 6, y: y + 4, class: "kartenschrift" }, text));
  }

  function zeichne() {
    geplant = false;
    ansicht.setAttribute("transform", `translate(${tx} ${ty}) scale(${s})`);
    leiste();
    const breite = svg.getBoundingClientRect().width || B;
    // Bildschirmpixel je Karteneinheit, und daraus die Kachelstufe, bei der
    // eine Kachel (256 px) etwa so gross erscheint, wie sie ist.
    const stufe = (faktor) => Math.max(0, Math.min(MAX_KACHELSTUFE,
      Math.round(Math.log2((breite / B) * faktor * k.massstab / 256))));
    const ax = -tx / s, ay = -ty / s, bx = (B - tx) / s, by = (H - ty) / s;
    const zg = stufe(1), z = stufe(s);
    grob.zeige(zg, 0, 0, B, H);
    if (z > zg) fein.zeige(z, ax, ay, bx, by); else fein.leere();
  }

  function plane() {
    if (!geplant) { geplant = true; requestAnimationFrame(zeichne); }
  }

  // Eine Aenderung durch die Hand: selbst zeichnen und die Gekoppelten mitnehmen.
  function geaendert() {
    plane();
    gekoppelt?.melde(uebernimm, { s, tx, ty });
  }
  function uebernimm(ansicht) {
    ({ s, tx, ty } = ansicht);
    plane();
  }
  gekoppelt?.nimm(uebernimm);

  // Die Karte deckt die Flaeche immer ganz; weiter hinaus als die Stadt geht es nicht.
  function begrenze() {
    s = Math.min(MAX_ZOOM, Math.max(1, s));
    tx = Math.min(0, Math.max(B * (1 - s), tx));
    ty = Math.min(0, Math.max(H * (1 - s), ty));
  }

  // Bildschirmpunkt in SVG-Einheiten der festen Flaeche.
  function punkt(ereignis) {
    const m = svg.getScreenCTM().inverse();
    return new DOMPoint(ereignis.clientX, ereignis.clientY).matrixTransform(m);
  }

  // Um den Punkt p (SVG-Einheiten) um den Faktor f vergroessern.
  function zoome(f, p = { x: B / 2, y: H / 2 }) {
    const neu = Math.min(MAX_ZOOM, Math.max(1, s * f));
    tx = p.x - ((p.x - tx) * neu) / s;
    ty = p.y - ((p.y - ty) * neu) / s;
    s = neu;
    begrenze();
    geaendert();
  }

  svg.addEventListener("wheel", (e) => {
    // Ganz herausgezoomt rollt das Mausrad die Seite weiter, statt sie festzuhalten.
    if (e.deltaY > 0 && s <= 1) return;
    e.preventDefault();
    zoome(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002)), punkt(e));
  }, { passive: false });

  svg.addEventListener("dblclick", (e) => zoome(e.shiftKey ? 0.5 : 2, punkt(e)));

  let zug = null;
  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || s <= 1) return;
    zug = { p: punkt(e), tx, ty, id: e.pointerId };
    svg.setPointerCapture(e.pointerId);
    svg.classList.add("zieht");
  });
  svg.addEventListener("pointermove", (e) => {
    if (!zug || e.pointerId !== zug.id) return;
    const p = punkt(e);
    tx = zug.tx + p.x - zug.p.x;
    ty = zug.ty + p.y - zug.p.y;
    begrenze();
    geaendert();
  });
  const los = () => { zug = null; svg.classList.remove("zieht"); };
  svg.addEventListener("pointerup", los);
  svg.addEventListener("pointercancel", los);

  const knopf = (zeichen, text, tun) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = zeichen;
    b.title = text;
    b.setAttribute("aria-label", text);
    b.addEventListener("click", tun);
    return b;
  };
  const knoepfe = document.createElement("div");
  knoepfe.className = "zoomknoepfe";
  knoepfe.append(knopf("+", "Hineinzoomen", () => zoome(2)),
    knopf("−", "Herauszoomen", () => zoome(0.5)),
    knopf("⤢", "Ganze Stadt", () => { s = 1; tx = 0; ty = 0; geaendert(); }));

  const nennung = document.createElement("div");
  nennung.className = "kartennennung";
  const link = (href, text) => {
    const a = document.createElement("a");
    a.href = href; a.textContent = text; a.target = "_blank"; a.rel = "noopener";
    return a;
  };
  nennung.append("© ", link("https://www.openstreetmap.org/copyright", "OpenStreetMap-Mitwirkende"));

  const flaeche = document.createElement("div");
  flaeche.className = "kartenflaeche";
  flaeche.append(svg, knoepfe, nennung);
  // Erst im Dokument kennt die Flaeche ihre Breite; die Kachelstufe haengt daran.
  new ResizeObserver(plane).observe(svg);
  leiste();
  return flaeche;
}

// Das Schraffurmuster fuer Tracts ohne tragfaehige Basis.
export function schraffur(id) {
  const defs = el("defs");
  const muster = el("pattern", { id, width: 6, height: 6, patternUnits: "userSpaceOnUse",
    patternTransform: "rotate(45)" });
  muster.append(el("rect", { width: 6, height: 6, fill: "#f1f3f6" }),
    el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "#aab3bf", "stroke-width": 2 }));
  defs.append(muster);
  return defs;
}
