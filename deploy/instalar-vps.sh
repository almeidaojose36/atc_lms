#!/usr/bin/env bash
# Instala o ATC LMS num VPS Ubuntu (testado para Ubuntu 24.04), com HTTPS automático pelo Caddy.
# Uso (como root):  DOMINIO=lms.atc-lda.com bash instalar-vps.sh
# Pode correr de novo para atualizar o código: os dados em /var/lib/atc-lms não são tocados.
set -euo pipefail

DOMINIO="${DOMINIO:-lms.atc-lda.com}"
RAMO="${RAMO:-claude/modest-franklin-264d3y}"
REPO="${REPO:-https://github.com/almeidaojose36/atc_lms.git}"
APP=/opt/atc-lms
DADOS=/var/lib/atc-lms
PORTA=8080

[ "$(id -u)" = 0 ] || { echo "Corra como root."; exit 1; }

# 1. Não pisar outro serviço: as portas 80/443 têm de estar livres ou ser do Caddy.
for p in 80 443 "$PORTA"; do
  dono=$(ss -ltnpH "sport = :$p" | grep -o 'users:(("[^"]*' | cut -d'"' -f2 | sort -u | tr '\n' ' ')
  if [ -n "$dono" ] && [ "$dono" != "caddy " ] && ! { [ "$p" = "$PORTA" ] && [ "$dono" = "python3 " ]; }; then
    echo "A porta $p já está a ser usada por: $dono"
    echo "Pare esse serviço ou fale com quem o instalou antes de continuar."
    exit 1
  fi
done

# 2. Pacotes (Python 3 e Caddy vêm do Ubuntu; o LMS não precisa de pip).
apt-get update -q
apt-get install -y -q python3 git caddy

# 3. Utilizador de sistema e código (sem a pasta producao/, que não é precisa no servidor).
id atc >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin atc
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q --depth 1 origin "$RAMO" && git -C "$APP" reset -q --hard FETCH_HEAD
else
  git clone -q --depth 1 --filter=blob:none --sparse --branch "$RAMO" "$REPO" "$APP"
  git -C "$APP" sparse-checkout set static cursos plataforma dados
fi
chown -R root:root "$APP"

# 4. Dados graváveis fora do código. Na primeira vez parte da base de dados de demonstração.
install -d -o atc -g atc -m 750 "$DADOS"
[ -f "$DADOS/atc.db" ] || install -o atc -g atc -m 640 "$APP/dados/atc.db" "$DADOS/atc.db"

# 5. Variáveis de ambiente. A chave ElevenLabs é escrita pelo dono, nunca aqui.
if [ ! -f /etc/atc-lms.env ]; then
  printf 'ATC_DADOS=%s\nATC_ELEVEN_KEY=\n' "$DADOS" > /etc/atc-lms.env
fi
chmod 600 /etc/atc-lms.env

# 6. Serviço que arranca com o servidor e reinicia se parar.
cat > /etc/systemd/system/atc-lms.service <<EOF
[Unit]
Description=ATC LMS
After=network-online.target

[Service]
User=atc
Group=atc
EnvironmentFile=/etc/atc-lms.env
ExecStart=/usr/bin/python3 $APP/atc_lms.py --porta $PORTA --host 127.0.0.1
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DADOS

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q --now atc-lms
systemctl restart atc-lms

# 7. HTTPS: o Caddy pede o certificado sozinho quando o DNS de $DOMINIO aponta para este servidor.
if ! grep -q "^$DOMINIO " /etc/caddy/Caddyfile 2>/dev/null; then
  # Só limpa o ficheiro se for o exemplo que vem com o pacote; outros sites ficam como estão.
  if grep -q "easy way to configure your Caddy" /etc/caddy/Caddyfile 2>/dev/null && ! grep -qE "^[a-z0-9.-]+\.[a-z]+ " /etc/caddy/Caddyfile; then
    : > /etc/caddy/Caddyfile
  fi
  printf '\n%s {\n    encode gzip\n    reverse_proxy 127.0.0.1:%s\n}\n' "$DOMINIO" "$PORTA" >> /etc/caddy/Caddyfile
fi
systemctl enable -q caddy
systemctl reload caddy || systemctl restart caddy

# 8. Firewall do sistema, se estiver ligada.
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
fi

sleep 2
if curl -fsS -o /dev/null "http://127.0.0.1:$PORTA/entrar"; then
  echo "ATC LMS a funcionar. Endereço: https://$DOMINIO"
else
  echo "O LMS não respondeu. Veja: journalctl -u atc-lms -n 50"; exit 1
fi
echo "Falta: escrever a chave em /etc/atc-lms.env (ATC_ELEVEN_KEY=...) e correr: systemctl restart atc-lms"
