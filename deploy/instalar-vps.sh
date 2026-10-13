#!/usr/bin/env bash
# Instala o ATC LMS num VPS Ubuntu (feito para Ubuntu 24.04) com HTTPS.
# - Se o servidor já usa nginx (outros sites), junta um ficheiro só para o LMS e pede o certificado ao Certbot.
# - Num servidor sem servidor web, instala o Caddy, que trata do HTTPS sozinho.
# Os outros sites não são alterados. Uso (como root):  DOMINIO=lms.atc-lda.com bash instalar-vps.sh
# Pode correr de novo para atualizar o código: os dados em /var/lib/atc-lms não são tocados.
set -euo pipefail

DOMINIO="${DOMINIO:-lms.atc-lda.com}"
RAMO="${RAMO:-claude/modest-franklin-264d3y}"
REPO="${REPO:-https://github.com/almeidaojose36/atc_lms.git}"
APP=/opt/atc-lms
DADOS=/var/lib/atc-lms
PORTA="${PORTA:-8080}"

[ "$(id -u)" = 0 ] || { echo "Corra como root."; exit 1; }

dono_porta() { ss -ltnpH "sport = :$1" | grep -o 'users:(("[^"]*' | cut -d'"' -f2 | sort -u | tr '\n' ' '; }

# 1. Verificações antes de mudar seja o que for.
d=$(dono_porta "$PORTA")
if [ -n "$d" ] && ! systemctl is-active -q atc-lms; then
  echo "A porta $PORTA já está a ser usada por: $d. Escolha outra: PORTA=8090 bash instalar-vps.sh"; exit 1
fi
web=$(dono_porta 80)$(dono_porta 443)
case "$web" in
  "")                 MODO=caddy ;;
  *nginx*)            MODO=nginx ;;
  *caddy*)            MODO=caddy ;;
  *) echo "As portas 80/443 estão a ser usadas por: $web. Nada foi alterado."; exit 1 ;;
esac
if [ "$MODO" = nginx ]; then
  nginx -t -q || { echo "A configuração do nginx já tem erros; corrija-os antes. Nada foi alterado."; exit 1; }
  command -v certbot >/dev/null || { echo "Falta o certbot (apt install certbot python3-certbot-nginx)."; exit 1; }
fi
echo "Modo: $MODO. Domínio: $DOMINIO. Porta interna: $PORTA."

# 2. Pacotes (o LMS só precisa de Python 3; não usa pip).
apt-get update -q
apt-get install -y -q python3 git
[ "$MODO" = caddy ] && apt-get install -y -q caddy

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
systemctl enable -q atc-lms
systemctl restart atc-lms
sleep 2
curl -fsS -o /dev/null "http://127.0.0.1:$PORTA/entrar" || { echo "O LMS não arrancou. Veja: journalctl -u atc-lms -n 50"; exit 1; }

# 7. HTTPS.
if [ "$MODO" = nginx ]; then
  CONF=/etc/nginx/sites-available/$DOMINIO.conf
  if [ ! -f "$CONF" ]; then
    cat > "$CONF" <<EOF
# ATC LMS. Ficheiro próprio: os outros sites deste servidor não são alterados.
server {
    listen 80;
    server_name $DOMINIO;

    client_max_body_size 6m;   # perguntas faladas ao guia por voz

    location / {
        proxy_pass http://127.0.0.1:$PORTA;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
    ln -sf "$CONF" "/etc/nginx/sites-enabled/$DOMINIO.conf"
    if ! nginx -t -q; then
      rm -f "/etc/nginx/sites-enabled/$DOMINIO.conf" "$CONF"
      echo "O nginx recusou a configuração nova; foi retirada e nada mudou nos outros sites."; exit 1
    fi
    systemctl reload nginx
  fi
  if [ ! -d "/etc/letsencrypt/live/$DOMINIO" ]; then
    certbot --nginx -d "$DOMINIO" --non-interactive --agree-tos --redirect \
      || { echo "O certificado falhou (o DNS de $DOMINIO já aponta para este servidor?). O site fica em HTTP até correr de novo."; exit 1; }
  fi
else
  if ! grep -q "^$DOMINIO " /etc/caddy/Caddyfile 2>/dev/null; then
    # Só limpa o ficheiro se for o exemplo que vem com o pacote; outros sites ficam como estão.
    if grep -q "easy way to configure your Caddy" /etc/caddy/Caddyfile 2>/dev/null && ! grep -qE "^[a-z0-9.-]+\.[a-z]+ " /etc/caddy/Caddyfile; then
      : > /etc/caddy/Caddyfile
    fi
    printf '\n%s {\n    encode gzip\n    reverse_proxy 127.0.0.1:%s\n}\n' "$DOMINIO" "$PORTA" >> /etc/caddy/Caddyfile
  fi
  systemctl enable -q caddy
  systemctl reload caddy || systemctl restart caddy
fi

# 8. Firewall do sistema, se estiver ligada (só acrescenta; não remove regras).
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
fi

echo "ATC LMS a funcionar. Endereço: https://$DOMINIO"
grep -q '^ATC_ELEVEN_KEY=.\+' /etc/atc-lms.env || \
  echo "Falta: escrever a chave em /etc/atc-lms.env (ATC_ELEVEN_KEY=...) e correr: systemctl restart atc-lms"
