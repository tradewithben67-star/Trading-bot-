"""Impressum, Datenschutz, Nutzungsbedingungen, Widerruf, Cookies.

Die Texte sind **Vorlagen**: sorgfältig geschrieben, aber keine Rechtsberatung.
Vor dem Start mit zahlenden Kunden gehören sie in die Hand einer Fachperson
(Anwältin, Datenschutzbeauftragter). Stellen, die besonders zu prüfen sind,
stehen in `PRUEFEN`.

Die Angaben zum Betreiber (Name, Anschrift, E-Mail …) trägt der Inhaber in der
Oberfläche unter „Rechtliches“ ein; sie liegen in `ki/betreiber.json`. Fehlt
etwas Pflichtiges, zeigen die Texte „[noch nicht angegeben]“ und die
Oberfläche warnt den Inhaber.

Ändert sich ein Text inhaltlich, `STAND` erhöhen: dann bestätigen alle Kunden
Nutzungsbedingungen und Datenschutz beim nächsten Anmelden neu.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

STAND = "2026-11-24"
AUFBEWAHRUNG_TAGE = 365          # Verlauf und Chats, danach automatisch gelöscht
MINDESTALTER = 18

FELDER = {
    "name": ("Name oder Firma", True),
    "anschrift": ("Anschrift (Straße, PLZ, Ort, Land)", True),
    "email": ("E-Mail", True),
    "telefon": ("Telefon", False),
    "ustid": ("Umsatzsteuer-ID", False),
    "verantwortlich": ("Verantwortlich für den Inhalt (§ 18 Abs. 2 MStV), falls abweichend", False),
    "hoster": ("Hoster des Servers (Name und Sitz)", False),
    "aufsicht": ("Zuständige Datenschutz-Aufsichtsbehörde", False),
}

PRUEFEN = [
    "Ist mit Anthropic ein Vertrag zur Auftragsverarbeitung (Data Processing Addendum) wirksam? "
    "Er ist Teil der kommerziellen Bedingungen von Anthropic; bitte dort bestätigen.",
    "Grundlage der Übermittlung in die USA (Standardvertragsklauseln oder Data Privacy Framework) "
    "für Anthropic und, falls zutreffend, den Hoster.",
    "Kündigungsfristen und Preise der Abos, sobald es eine Bezahlung gibt.",
    "Widerrufsbelehrung: passt sie zum tatsächlichen Bezahlablauf (Zustimmung zum vorzeitigen Beginn)?",
    "Ob die Tätigkeit (KI-Einschätzungen zu Gold) erlaubnisfrei ist oder als Anlageberatung "
    "bzw. Finanzanalyse gilt (WpHG, KWG, MAR).",
    "Ob ein Datenschutzbeauftragter benannt werden muss.",
]

CHAT_HINWEIS = ("Deine Chat-Nachrichten werden zur Beantwortung an Anthropic (USA) übermittelt, "
                "den Anbieter des Sprachmodells Claude. Dein Name wird dabei nicht mitgeschickt. "
                "Gib im Chat bitte keine sensiblen persönlichen Daten ein, etwa Kontonummern oder Gesundheitsangaben.")

RISIKO = ("Der Handel mit Gold und gehebelten Produkten wie CFDs ist mit hohem Risiko verbunden "
          "und kann zum Totalverlust führen. Die KI gibt Einschätzungen eines statistischen Modells, "
          "keine Anlageberatung. Vergangene Ergebnisse und Tests sind kein verlässlicher Hinweis auf künftige.")

SEITEN = {"impressum": "Impressum", "datenschutz": "Datenschutzerklärung",
          "nutzungsbedingungen": "Nutzungsbedingungen", "widerruf": "Widerruf und Erstattung",
          "cookies": "Cookies und Speicher"}


class Betreiber:
    def __init__(self, pfad: str | Path) -> None:
        self.pfad = Path(pfad)
        self._sperre = threading.Lock()
        self._d: dict = (json.loads(self.pfad.read_text(encoding="utf-8"))
                         if self.pfad.exists() else {})

    def daten(self) -> dict:
        with self._sperre:
            return {k: str(self._d.get(k, "")) for k in FELDER}

    def fehlend(self) -> list[str]:
        d = self.daten()
        return [FELDER[k][0] for k, (_, pflicht) in FELDER.items() if pflicht and not d[k].strip()]

    def vollstaendig(self) -> bool:
        return not self.fehlend()

    def setzen(self, neu: dict) -> dict:
        sauber = {}
        for k in FELDER:
            wert = str(neu.get(k, "")).strip()
            if len(wert) > 300:
                raise ValueError(f"{FELDER[k][0]}: höchstens 300 Zeichen.")
            sauber[k] = wert
        if sauber["email"] and ("@" not in sauber["email"] or " " in sauber["email"]):
            raise ValueError("Die E-Mail-Adresse sieht nicht gültig aus.")
        with self._sperre:
            self._d = sauber
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pfad.with_suffix(".tmp")
            tmp.write_text(json.dumps(sauber, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.pfad)
        return self.daten()


# -- Texte --------------------------------------------------------------------
# Jede Seite ist eine Liste von Blöcken: {"h": Überschrift}, {"p": Absatz},
# {"ul": [Punkte]}, {"adresse": [Zeilen]}.

def _w(d: dict, k: str) -> str:
    return d.get(k, "").strip() or "[noch nicht angegeben]"


def _betreiber_block(d: dict) -> dict:
    zeilen = [_w(d, "name")] + [z.strip() for z in _w(d, "anschrift").replace(",", "\n").splitlines() if z.strip()]
    return {"adresse": zeilen}


def impressum(d: dict) -> list[dict]:
    b = [{"h": "Angaben gemäß § 5 DDG"}, _betreiber_block(d),
         {"h": "Kontakt"}, {"p": f"E-Mail: {_w(d, 'email')}"}]
    if d.get("telefon"):
        b.append({"p": f"Telefon: {d['telefon']}"})
    if d.get("ustid"):
        b += [{"h": "Umsatzsteuer-ID"}, {"p": f"Umsatzsteuer-Identifikationsnummer nach § 27a UStG: {d['ustid']}"}]
    b += [{"h": "Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV"},
          {"p": d.get("verantwortlich") or f"{_w(d, 'name')}, Anschrift wie oben."},
          {"h": "Verbraucherstreitbeilegung"},
          {"p": "Wir sind nicht bereit und nicht verpflichtet, an Streitbeilegungsverfahren vor einer "
                "Verbraucherschlichtungsstelle teilzunehmen."},
          {"h": "Hinweis zu den Inhalten"}, {"p": RISIKO}]
    return b


def datenschutz(d: dict) -> list[dict]:
    aufsicht = d.get("aufsicht") or "der Datenschutz-Aufsichtsbehörde deines Bundeslands oder deines Wohnorts"
    hoster = d.get("hoster")
    return [
        {"h": "1. Wer verantwortlich ist"}, _betreiber_block(d), {"p": f"E-Mail: {_w(d, 'email')}"},
        {"h": "2. Kurz gesagt"},
        {"ul": ["Wir speichern nur, was für die KI und dein Konto nötig ist.",
                "Kein Tracking, keine Werbung, keine Analyse-Werkzeuge, kein Verkauf von Daten.",
                "Die Seite lädt nichts von fremden Servern, keine Schriften, keine Skripte.",
                "Chat-Nachrichten gehen zur Beantwortung an Anthropic (USA), ohne deinen Namen.",
                "Du kannst deine Daten jederzeit herunterladen und dein Konto selbst löschen."]},
        {"h": "3. Dein Konto"},
        {"p": "Wir speichern deinen frei wählbaren Namen (ein Pseudonym genügt), dein Passwort nur als "
              "Hash (nicht umkehrbar), dein Abo, den Zeitpunkt der Anlage sowie wann du Nutzungsbedingungen, "
              "Datenschutzhinweise und den Chat-Hinweis bestätigt hast. Eine E-Mail-Adresse brauchen wir nicht."},
        {"p": "Zweck: dir das Konto und die KI bereitzustellen. Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO "
              "(Vertrag). Speicherdauer: bis du das Konto löschst oder es gelöscht wird."},
        {"h": "4. Nutzung, Verlauf und eigene Indikatoren"},
        {"p": "Wenn du die KI nutzt, speichern wir die Aktion (Analyse, Strategie-Test, Indikatoren, Training) "
              "mit Ergebnis, Zeitpunkt und Modell, deinen Verbrauch je Modell im laufenden Monat und deine "
              "eigenen Indikator-Formeln. Zweck: dir den Verlauf zu zeigen und die Kontingente deines Abos "
              "einzuhalten. Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO."},
        {"p": f"Verlaufseinträge und Chats löschen wir automatisch nach {AUFBEWAHRUNG_TAGE} Tagen, "
              "eigene Indikatoren und den Verbrauch mit deinem Konto."},
        {"h": "5. Chat mit der KI (Anthropic)"},
        {"p": "Für den Chat nutzen wir das Sprachmodell Claude der Anthropic, PBC, 548 Market Street, "
              "San Francisco, CA 94104, USA. Übermittelt werden deine Nachricht, der bisherige Gesprächsverlauf "
              "in diesem Bereich, die Seite, auf der du bist, dein Abo und die Ergebnisse der Werkzeuge, die die KI "
              "dabei aufruft (z. B. Analysen). Dein Name, dein Passwort und deine anderen Kontodaten werden nicht übermittelt."},
        {"p": "Anthropic verarbeitet diese Daten in unserem Auftrag (Art. 28 DSGVO). Weil Anthropic in den USA sitzt, "
              "werden Daten in ein Drittland übermittelt; Grundlage sind die Standardvertragsklauseln der "
              "EU-Kommission (Art. 46 Abs. 2 lit. c DSGVO) im Vertrag zur Auftragsverarbeitung. Nach seinen "
              "kommerziellen Bedingungen nutzt Anthropic Daten aus der API nicht zum Training seiner Modelle und "
              "bewahrt sie nur begrenzt auf."},
        {"p": "Auf unserem Server speichern wir den Chat, damit du ihn wieder siehst, bis du ihn mit "
              f"„Neues Gespräch“ löschst, dein Konto löschst oder {AUFBEWAHRUNG_TAGE} Tage vergangen sind. "
              "Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO. Bitte gib im Chat keine sensiblen Daten ein."},
        {"h": "6. Speicherung im Browser"},
        {"p": "Wir setzen ein technisch notwendiges Cookie für die Anmeldung und speichern auf Wunsch "
              "Komfort-Einstellungen im Browser. Einzelheiten stehen unter „Cookies und Speicher“."},
        {"h": "7. Server und Protokolle"},
        {"p": "Unser Server schreibt keine Zugriffsprotokolle mit IP-Adressen. "
              + (f"Der Server wird betrieben von {hoster}. Der Hoster verarbeitet beim Ausliefern der Seite technisch "
                 "nötige Verbindungsdaten wie die IP-Adresse in unserem Auftrag." if hoster else
                 "Wird der Server bei einem Hoster betrieben, verarbeitet dieser beim Ausliefern technisch nötige "
                 "Verbindungsdaten wie die IP-Adresse in unserem Auftrag. [Hoster noch nicht angegeben]")},
        {"h": "8. Empfänger"},
        {"p": "Anthropic (Chat)" + (f", {hoster} (Hosting)" if hoster else "") + ". Sonst geben wir keine Daten weiter."},
        {"h": "9. Keine automatisierten Entscheidungen"},
        {"p": "Die Einschätzungen der KI sind Hinweise für dich. Wir treffen damit keine Entscheidungen über dich, "
              "die dir gegenüber rechtliche Wirkung haben (Art. 22 DSGVO)."},
        {"h": "10. Deine Rechte"},
        {"ul": ["Auskunft (Art. 15 DSGVO) und Datenübertragbarkeit (Art. 20): unter Konto → „Meine Daten herunterladen“.",
                "Löschung (Art. 17): unter Konto → „Konto löschen“, sofort und vollständig.",
                "Berichtigung (Art. 16), Einschränkung (Art. 18) und Widerspruch (Art. 21): per E-Mail an uns.",
                f"Beschwerde bei einer Aufsichtsbehörde (Art. 77 DSGVO), zum Beispiel bei {aufsicht}."]},
        {"h": "11. Mindestalter"},
        {"p": f"Die KI ist nur für Personen ab {MINDESTALTER} Jahren. Wir speichern wissentlich keine Daten von Kindern."},
        {"h": "12. Kein Newsletter"},
        {"p": "Wir verschicken keine Newsletter und keine Werbe-Nachrichten. Sollte sich das ändern, "
              "nur mit deiner Einwilligung und mit Abmeldelink in jeder Nachricht."},
        {"p": f"Stand: {STAND}"},
    ]


def nutzungsbedingungen(d: dict) -> list[dict]:
    return [
        {"h": "1. Anbieter und Geltung"},
        {"p": f"Anbieter der BENGX KI ist {_w(d, 'name')} (siehe Impressum). Diese Bedingungen gelten für jede Nutzung."},
        {"h": "2. Was die KI ist"},
        {"p": "Die BENGX KI ist ein Analyse-Werkzeug. Sie schätzt mit einem eigenen statistischen Modell ein, ob ein "
              "Kurs zuerst ein Ziel oben oder einen Stop unten erreicht, zeigt Indikatoren und lässt eigene Indikatoren "
              "bauen. Im Chat antwortet ein Sprachmodell (Claude von Anthropic), das mit diesen Werkzeugen rechnet. "
              "Beide können sich irren. Wie gut ein Modell auf vergangenen Kursen war, zeigt der Strategie-Test; "
              "das ist keine Zusage für die Zukunft."},
        {"h": "3. Keine Anlageberatung, Risiko"},
        {"p": "Die KI gibt keine Anlageberatung, keine Anlagevermittlung und keine Finanzanalyse im Sinne des "
              "Wertpapierhandels- oder Kreditwesengesetzes. Jede Handelsentscheidung triffst du selbst und auf eigenes Risiko."},
        {"p": RISIKO + " In den Ergebnissen sind Spread und Gebühren nicht enthalten. Teste Ideen zuerst ohne echtes Geld."},
        {"h": "4. Konto"},
        {"ul": [f"Nutzen darf die KI nur, wer mindestens {MINDESTALTER} Jahre alt ist.",
                "Ein Konto gehört einer Person. Halte dein Passwort geheim.",
                "Du kannst dein Konto jederzeit selbst löschen (Konto → Konto löschen)."]},
        {"h": "5. Abos, Kontingente, Preise"},
        {"ul": ["Jedes Abo legt fest, wie viel du je Modell und im Chat pro Monat nutzen kannst. Die Übersicht steht unter „Nutzung & Abo“.",
                "Das Kontingent erneuert sich zum Monatsersten; nicht Genutztes verfällt.",
                "Ist das Kontingent eines Modells aufgebraucht, pausiert dieses Modell bis zum Monatsersten. Es entstehen keine Nachzahlungen.",
                "Scheitert eine Aktion, wird ihr Verbrauch automatisch gutgeschrieben.",
                "Preise werden vor jedem Abschluss vollständig als Endpreis inklusive Umsatzsteuer angezeigt. "
                "Es gibt keine versteckten Gebühren. Solange keine Preise angegeben sind, ist die Nutzung kostenlos.",
                "Ein bezahltes Abo kannst du jederzeit zum Ende des laufenden Abrechnungszeitraums kündigen."]},
        {"h": "6. Faire Nutzung"},
        {"p": "Nicht erlaubt ist, die Grenzen zu umgehen, die KI automatisiert abzufragen, Zugänge weiterzugeben "
              "oder den Chat für rechtswidrige Inhalte zu verwenden."},
        {"h": "7. Verfügbarkeit"},
        {"p": "Wir bemühen uns um einen störungsfreien Betrieb, können ihn aber nicht zusagen. Wartung, Ausfälle "
              "des Sprachmodell-Anbieters oder fehlende Kursdaten können die Nutzung zeitweise einschränken."},
        {"h": "8. Haftung"},
        {"p": "Wir haften unbeschränkt bei Vorsatz und grober Fahrlässigkeit, bei Verletzung von Leben, Körper oder "
              "Gesundheit und nach dem Produkthaftungsgesetz. Bei leichter Fahrlässigkeit haften wir nur für die "
              "Verletzung wesentlicher Vertragspflichten und begrenzt auf den vorhersehbaren, typischen Schaden. "
              "Für Verluste aus Handelsentscheidungen, die du auf Grundlage der Einschätzungen triffst, haften wir, "
              "soweit gesetzlich zulässig, nicht."},
        {"h": "9. Änderungen"},
        {"p": "Ändern sich diese Bedingungen, zeigen wir das beim nächsten Anmelden an und bitten erneut um deine Zustimmung."},
        {"h": "10. Recht"},
        {"p": "Es gilt deutsches Recht. Zwingende Verbraucherschutzvorschriften des Staates, in dem du lebst, bleiben unberührt."},
        {"p": f"Stand: {STAND}"},
    ]


def widerruf(d: dict) -> list[dict]:
    return [
        {"p": "Derzeit gibt es keine kostenpflichtigen Abos. Die folgenden Regeln gelten, sobald Abos bezahlt werden können."},
        {"h": "Widerrufsbelehrung"},
        {"p": "Widerrufsrecht: Du hast das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu "
              "widerrufen. Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsabschlusses."},
        {"p": "Um dein Widerrufsrecht auszuüben, musst du uns mittels einer eindeutigen Erklärung (z. B. per E-Mail) "
              "über deinen Entschluss, diesen Vertrag zu widerrufen, informieren an:"},
        _betreiber_block(d), {"p": f"E-Mail: {_w(d, 'email')}"},
        {"p": "Du kannst dafür das untenstehende Muster-Widerrufsformular verwenden, das jedoch nicht vorgeschrieben ist. "
              "Zur Wahrung der Widerrufsfrist reicht es aus, dass du die Mitteilung vor Ablauf der Frist absendest."},
        {"p": "Folgen des Widerrufs: Wenn du diesen Vertrag widerrufst, haben wir dir alle Zahlungen, die wir von dir "
              "erhalten haben, unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die "
              "Mitteilung über deinen Widerruf bei uns eingegangen ist. Für diese Rückzahlung verwenden wir dasselbe "
              "Zahlungsmittel, das du bei der ursprünglichen Transaktion eingesetzt hast, es sei denn, mit dir wurde "
              "ausdrücklich etwas anderes vereinbart; in keinem Fall werden dir wegen dieser Rückzahlung Entgelte berechnet."},
        {"p": "Hast du verlangt, dass die Leistung während der Widerrufsfrist beginnen soll, so hast du uns einen "
              "angemessenen Betrag zu zahlen, der dem Anteil der bis zum Widerruf bereits erbrachten Leistungen im "
              "Vergleich zum Gesamtumfang der im Vertrag vorgesehenen Leistungen entspricht."},
        {"h": "Muster-Widerrufsformular"},
        {"p": "(Wenn du den Vertrag widerrufen willst, fülle bitte dieses Formular aus und sende es zurück.)"},
        {"ul": [f"An: {_w(d, 'name')}, {_w(d, 'anschrift')}, {_w(d, 'email')}",
                "Hiermit widerrufe(n) ich/wir den von mir/uns abgeschlossenen Vertrag über die Erbringung der folgenden Dienstleistung (*)",
                "Bestellt am (*) / erhalten am (*)", "Name des/der Verbraucher(s)", "Anschrift des/der Verbraucher(s)",
                "Unterschrift des/der Verbraucher(s) (nur bei Mitteilung auf Papier)", "Datum", "(*) Unzutreffendes streichen."]},
        {"h": "Erstattungen im Betrieb"},
        {"ul": ["Scheitert eine Analyse, ein Strategie-Test oder eine Chat-Nachricht, wird der Verbrauch sofort automatisch gutgeschrieben.",
                "Nicht genutztes Kontingent verfällt zum Monatsersten und wird nicht ausgezahlt.",
                "Nach einer Kündigung bleibt das Abo bis zum Ende des bezahlten Zeitraums nutzbar.",
                f"Bei Fragen zu einer Abrechnung schreib uns an {_w(d, 'email')}."]},
        {"p": f"Stand: {STAND}"},
    ]


def cookies(d: dict) -> list[dict]:
    return [
        {"p": "Wir verwenden kein Tracking, keine Werbe-Cookies und keine Analyse-Werkzeuge. Die Seite lädt keine "
              "Inhalte von fremden Servern. Im Browser landet nur, was unten steht."},
        {"h": "Technisch notwendig"},
        {"ul": ["Cookie „bengx_sitzung“: hält dich angemeldet. Enthält nur eine zufällige Kennung, keine persönlichen Daten. "
                "Gültig 30 Tage oder bis zur Abmeldung. Rechtsgrundlage: § 25 Abs. 2 Nr. 2 TDDDG.",
                "Browser-Speicher „speicher-wahl“: merkt sich deine Entscheidung zu den Komfort-Einstellungen, "
                "damit wir nicht bei jedem Besuch fragen."]},
        {"h": "Komfort, nur wenn du zustimmst"},
        {"ul": ["„thema“: hell, dunkel oder automatisch.",
                "„modell“: zuletzt gewähltes KI-Modell.",
                "„filter“: zuletzt gewählter Filter im Verlauf (nur für die aktuelle Sitzung)."]},
        {"p": "Deine Wahl kannst du jederzeit ändern: über „Speicher-Einstellungen“ unten in der Seitenleiste. "
              "Lehnst du die Komfort-Einstellungen ab, löschen wir sie aus deinem Browser."},
        {"p": f"Stand: {STAND}"},
    ]


def seite(name: str, d: dict) -> dict:
    texte = {"impressum": impressum, "datenschutz": datenschutz, "nutzungsbedingungen": nutzungsbedingungen,
             "widerruf": widerruf, "cookies": cookies}
    if name not in texte:
        raise ValueError("Unbekannte Seite.")
    return {"seite": name, "titel": SEITEN[name], "stand": STAND, "bloecke": texte[name](d)}
