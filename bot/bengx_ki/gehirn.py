"""Teil 2 — das Gehirn: ein Transformer, von Hand gebaut.

Es ist dasselbe Prinzip wie in großen Sprachmodellen, nur dass die „Wörter“
hier Kerzen sind. PyTorch liefert nur die Rechenbausteine (Matrizen
multiplizieren, Ableitungen bilden). Wie das Netz aufgebaut ist und wie es
denkt, steht vollständig in dieser Datei.

Der Weg einer Vorhersage:

1. **Einbettung** — jede Kerze (12 Zahlen) wird zu einem Vektor der Breite
   `breite`. Dazu kommt ein gelernter Vektor für ihre Position im Fenster.
2. **Blöcke** — mehrmals hintereinander:
   * **Aufmerksamkeit**: jede Kerze fragt alle *älteren* Kerzen „bist du für
     mich wichtig?“ und sammelt deren Informationen gewichtet ein. So kann die
     KI zum Beispiel lernen, dass ein Docht vor drei Kerzen zum heutigen
     Ausbruch gehört.
   * **Nachdenken** (ein kleines Netz je Kerze), das das Gesammelte verarbeitet.
3. **Kopf** — die letzte Kerze kennt jetzt das ganze Fenster. Aus ihr werden
   drei Zahlen: wie wahrscheinlich runter, seitwärts, hoch.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
from torch import nn
from torch.nn import functional as F


@dataclass
class Bauplan:
    merkmale: int = 12      # Zahlen pro Kerze
    fenster: int = 64       # so viele Kerzen sieht die KI auf einmal
    breite: int = 64        # Größe des inneren Vektors je Kerze
    koepfe: int = 4         # parallele Aufmerksamkeiten
    schichten: int = 3      # wie viele Blöcke hintereinander
    klassen: int = 3        # runter, seitwärts, hoch
    vergessen: float = 0.1  # Dropout: zufälliges Abschalten gegen Auswendiglernen

    def als_dict(self) -> dict:
        return asdict(self)


class Aufmerksamkeit(nn.Module):
    """Mehrköpfige Selbst-Aufmerksamkeit, Schritt für Schritt ausgeschrieben."""

    def __init__(self, plan: Bauplan) -> None:
        super().__init__()
        assert plan.breite % plan.koepfe == 0, "breite muss durch koepfe teilbar sein"
        self.koepfe = plan.koepfe
        # Aus jeder Kerze werden drei Vektoren:
        #   Frage   (q) — wonach suche ich?
        #   Schlüssel (k) — was biete ich an?
        #   Wert    (v) — was gebe ich weiter, wenn ich gewählt werde?
        self.fqw = nn.Linear(plan.breite, 3 * plan.breite)
        self.zurueck = nn.Linear(plan.breite, plan.breite)
        self.vergessen = nn.Dropout(plan.vergessen)
        # Maske: Kerze t darf nur Kerzen 0..t sehen, nie spätere.
        maske = torch.tril(torch.ones(plan.fenster, plan.fenster, dtype=torch.bool))
        self.register_buffer("maske", maske, persistent=False)
        # Für die Erklärung: auf Wunsch die letzten Aufmerksamkeits-Gewichte behalten.
        self.merken = False
        self.zuletzt: torch.Tensor | None = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        stapel, zeit, breite = x.shape
        h = self.koepfe
        d = breite // h
        q, k, v = self.fqw(x).split(breite, dim=2)
        # (stapel, zeit, breite) → (stapel, köpfe, zeit, d)
        q = q.view(stapel, zeit, h, d).transpose(1, 2)
        k = k.view(stapel, zeit, h, d).transpose(1, 2)
        v = v.view(stapel, zeit, h, d).transpose(1, 2)

        # Wie gut passt jede Frage zu jedem Schlüssel? Skalarprodukt, skaliert.
        passung = (q @ k.transpose(-2, -1)) / math.sqrt(d)
        passung = passung.masked_fill(~self.maske[:zeit, :zeit], float("-inf"))
        gewichte = F.softmax(passung, dim=-1)        # jede Zeile summiert zu 1
        if self.merken:
            self.zuletzt = gewichte.detach()
        gewichte = self.vergessen(gewichte)

        y = gewichte @ v                               # gewichtete Summe der Werte
        y = y.transpose(1, 2).contiguous().view(stapel, zeit, breite)
        return self.zurueck(y)


class Nachdenken(nn.Module):
    """Kleines Netz, das jede Kerze für sich weiterverarbeitet."""

    def __init__(self, plan: Bauplan) -> None:
        super().__init__()
        self.rein = nn.Linear(plan.breite, 4 * plan.breite)
        self.raus = nn.Linear(4 * plan.breite, plan.breite)
        self.vergessen = nn.Dropout(plan.vergessen)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.vergessen(self.raus(F.gelu(self.rein(x))))


class Block(nn.Module):
    def __init__(self, plan: Bauplan) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(plan.breite)
        self.aufmerksamkeit = Aufmerksamkeit(plan)
        self.norm2 = nn.LayerNorm(plan.breite)
        self.nachdenken = Nachdenken(plan)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # „x + …“: das Neue wird auf das Alte addiert, statt es zu ersetzen.
        # So geht beim Durchlauf durch viele Blöcke nichts verloren.
        x = x + self.aufmerksamkeit(self.norm1(x))
        x = x + self.nachdenken(self.norm2(x))
        return x


class Gehirn(nn.Module):
    def __init__(self, plan: Bauplan) -> None:
        super().__init__()
        self.plan = plan
        self.einbettung = nn.Linear(plan.merkmale, plan.breite)
        self.position = nn.Parameter(torch.zeros(1, plan.fenster, plan.breite))
        self.vergessen = nn.Dropout(plan.vergessen)
        self.bloecke = nn.ModuleList(Block(plan) for _ in range(plan.schichten))
        self.norm = nn.LayerNorm(plan.breite)
        self.kopf = nn.Linear(plan.breite, plan.klassen)
        self.apply(self._start)
        nn.init.normal_(self.position, std=0.02)

    @staticmethod
    def _start(modul: nn.Module) -> None:
        # Kleine Zufallswerte zum Start: das Netz weiß noch nichts.
        if isinstance(modul, nn.Linear):
            nn.init.normal_(modul.weight, std=0.02)
            nn.init.zeros_(modul.bias)

    def forward(self, fenster: torch.Tensor) -> torch.Tensor:
        """fenster: (stapel, zeit, merkmale) → Rohwerte (stapel, klassen)."""
        zeit = fenster.shape[1]
        x = self.einbettung(fenster) + self.position[:, :zeit]
        x = self.vergessen(x)
        for block in self.bloecke:
            x = block(x)
        letzte = self.norm(x[:, -1])          # die jüngste Kerze kennt jetzt alles
        return self.kopf(letzte)

    def aufmerksamkeit(self, fenster: torch.Tensor) -> torch.Tensor:
        """Worauf die jüngste Kerze geachtet hat — über alle Blöcke hinweg.

        „Aufmerksamkeits-Durchrollen“: in jedem Block wird über die Köpfe
        gemittelt, der direkte Weg (x + …) mit eingerechnet und Block für
        Block weitermultipliziert. Ergebnis: ein Gewicht je Kerze im Fenster,
        zusammen 1. Hoch heißt: diese Kerze hat die Entscheidung geprägt.
        """
        self.eval()
        for b in self.bloecke:
            b.aufmerksamkeit.merken = True
        try:
            with torch.no_grad():
                self(fenster)
            zeit = fenster.shape[1]
            gesamt = torch.eye(zeit)
            for b in self.bloecke:
                a = b.aufmerksamkeit.zuletzt[0].mean(dim=0)          # (zeit, zeit)
                a = 0.5 * a + 0.5 * torch.eye(zeit)
                a = a / a.sum(dim=-1, keepdim=True)
                gesamt = a @ gesamt
            return gesamt[-1]
        finally:
            for b in self.bloecke:
                b.aufmerksamkeit.merken = False
                b.aufmerksamkeit.zuletzt = None

    def anzahl_gewichte(self) -> int:
        return sum(p.numel() for p in self.parameters())
