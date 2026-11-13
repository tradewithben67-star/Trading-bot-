#!/bin/sh
cd "$(dirname "$0")" || exit 1
PY=python3
command -v $PY >/dev/null 2>&1 || { echo "Python 3 fehlt."; read -r _; exit 1; }

echo
echo "  BENGX"
echo "  ====="
echo "  Einrichten, pruefen, und erst dann starten."
echo

if [ -f .env ]; then
  # Schon eingerichtet: nur fragen, was es seit dem letzten Mal Neues gibt.
  $PY einrichten.py --nur-neues
else
  $PY einrichten.py || { read -r _; exit 1; }
fi

echo
echo "  ------------------------------------------------"
echo "  Pruefe, ob alles da ist ..."
echo "  ------------------------------------------------"
echo
if ! $PY -m bengx_bot pruefen; then
  echo
  echo "  Ich starte den Bot NICHT, weil oben etwas fehlt."
  echo "  Mach ein Foto davon und schick es Claude."
  read -r _
  exit 1
fi

echo
echo "  Alles gut. Der Bot laeuft jetzt. Fenster offen lassen."
echo
$PY -m bengx_bot telegram
read -r _
