"""Die Konfiguration des Notebook-Servers im Analyse-Abbild.

Sie liegt im Abbild unter ``/usr/local/etc/jupyter/`` und gilt damit fuer
**jeden** Start, auch fuer einen mit eigenem ``command``. Genau darum geht
es: Der Verbund (``docker-compose.srv01.yml``) setzt sein eigenes
``command``, und die beiden Zusagen hier duerfen nicht daran haengen, dass
dort die richtigen Schalter stehen.

Kein Token und kein Passwort hier. Das Token kommt als ``JUPYTER_TOKEN`` aus
der Umgebung - in dieser Datei waere es ein Geheimnis im Abbild, lesbar in
jeder Schicht, auch nach einem spaeteren Loeschen.
"""

c = get_config()  # noqa: F821 - traitlets legt get_config() beim Laden bereit

# Die Wurzel ist der beschreibbare Arbeitsbereich und nicht /app: Dort liegen
# config/, src/ und der ganze eingehaengte Bestand, und sie gehoeren nicht in
# den Dateibaum eines Browsers. Der Pfad steht auch in Dockerfile.jupyter
# (mkdir, chmod) und in docker-compose.srv01.yml (der Datentraeger);
# tests/test_jupyter_abbild.py haelt die drei Stellen gegeneinander.
c.ServerApp.root_dir = "/app/arbeit"

# Der Verbund setzt keinen Benutzer, der Container laeuft also als root -
# und jupyter-server verweigert dann den Start ("Running as root is not
# recommended. Use --allow-root to bypass."). Das ist hier kein Risiko, das
# weggeschaltet wird: Der Zugang liegt vor dem Dienst (Cloudflare Access
# ueber urbancrime-*, dazu das Token), data/ ist schreibgeschuetzt
# eingehaengt, und der Container hat keine Schluessel. Ohne diese Zeile
# startete der Dienst ueberhaupt nicht, und zwar erst auf dem Server.
c.ServerApp.allow_root = True

# Untaetige Kernel nach zwei Stunden beenden, auch bei offenem Tab. Eine
# Analysesitzung der Notebooks 34/37 haelt die exklusive Datensperre bis
# analyse.beenden() oder Kernel-Ende (storage.analysesitzung) - nach einem
# Zellfehler absichtlich. Ein vergessener Tab liesse sonst den Datenlauf am
# Montag um 04:30 sofort scheitern. Ein rechnender Kernel gilt nicht als
# untaetig und bleibt. Traitlets: jupyter_server MappingKernelManager.
c.MappingKernelManager.cull_idle_timeout = 2 * 60 * 60
c.MappingKernelManager.cull_interval = 5 * 60
c.MappingKernelManager.cull_connected = True
c.MappingKernelManager.cull_busy = False
