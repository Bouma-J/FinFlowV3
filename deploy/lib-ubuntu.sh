#!/usr/bin/env bash
# Fonctions partagées par les scripts d'installation et de mise à jour
# sur Ubuntu Server. À sourcer, pas à exécuter.
#
# Le dépôt FinFlowV3 est privé : le jeton (Contents: Read) est stocké
# hors du projet, dans /root/.config/finflow/github.token (mode 600).
# Il n'est pas écrit dans l'URL origin ni dans le .env applicatif.

FINFLOW_REPO_DEFAULT="https://github.com/Bouma-J/FinFlowV3.git"
FINFLOW_GIT_TOKEN_FILE="${FINFLOW_GIT_TOKEN_FILE:-/root/.config/finflow/github.token}"
FINFLOW_GIT_HELPER="${FINFLOW_GIT_HELPER:-/usr/local/lib/finflow/git-credential.sh}"

finflow_require_tty() {
  local hint="${1:-sudo bash deploy/ubuntu-install.sh}"
  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    echo "L'installation est un questionnaire dans le terminal." >&2
    echo "Ouvrez une session SSH sur le serveur, puis lancez :" >&2
    echo "  ${hint}" >&2
    exit 1
  fi
}

finflow_read() {
  # Toujours le clavier du terminal, jamais l'entrée redirigée du script.
  if ! read "$@" </dev/tty; then
    echo "Saisie interrompue. Installation annulée." >/dev/tty
    exit 1
  fi
}

finflow_newline() {
  if [[ -w /dev/tty ]]; then
    echo >/dev/tty
  else
    echo
  fi
}

finflow_prepare_apt() {
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a
  export NEEDRESTART_SUSPEND=1
  export APT_LISTCHANGES_FRONTEND=none
  mkdir -p /etc/needrestart/conf.d
  printf '%s\n' '$nrconf{restart} = "a";' > /etc/needrestart/conf.d/finflow.conf
  timedatectl set-ntp true >/dev/null 2>&1 || true
}

finflow_ufw_allow_ssh() {
  local port="22"
  local p=""
  local f
  if [[ -f /etc/ssh/sshd_config ]]; then
    p="$(awk 'tolower($1)=="port" {print $2; exit}' /etc/ssh/sshd_config || true)"
    [[ -n "$p" ]] && port="$p"
  fi
  if compgen -G "/etc/ssh/sshd_config.d/*.conf" >/dev/null 2>&1; then
    for f in /etc/ssh/sshd_config.d/*.conf; do
      p="$(awk 'tolower($1)=="port" {print $2; exit}' "$f" || true)"
      [[ -n "$p" ]] && port="$p"
    done
  fi
  if [[ -n "${SSH_CONNECTION:-}" ]]; then
    local live="${SSH_CONNECTION##* }"
    ufw allow "${live}/tcp" >/dev/null || true
  fi
  ufw allow "${port}/tcp" >/dev/null || true
  printf '%s\n' "$port"
}

finflow_install_git_helper() {
  install -d -m 755 /usr/local/lib/finflow
  cat > "$FINFLOW_GIT_HELPER" <<'EOF'
#!/usr/bin/env bash
# Git credential helper FinFlow — github.com uniquement.
op="${1:-get}"
[[ "$op" == "get" ]] || exit 0
host=""
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && break
  case "$line" in
    host=*) host="${line#host=}" ;;
  esac
done
[[ "$host" == "github.com" ]] || exit 0
token_file="/root/.config/finflow/github.token"
[[ -f "$token_file" ]] || exit 1
token="$(tr -d '[:space:]' < "$token_file")"
[[ -n "$token" ]] || exit 1
printf 'username=x-access-token\npassword=%s\n' "$token"
EOF
  chmod 700 "$FINFLOW_GIT_HELPER"
}

finflow_save_github_token() {
  local token="$1"
  [[ -n "$token" ]] || return 0
  install -d -m 700 "$(dirname "$FINFLOW_GIT_TOKEN_FILE")"
  printf '%s\n' "$token" > "$FINFLOW_GIT_TOKEN_FILE"
  chmod 600 "$FINFLOW_GIT_TOKEN_FILE"
  finflow_install_git_helper
}

finflow_prepare_git_auth() {
  export GIT_TERMINAL_PROMPT=0
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    finflow_save_github_token "$GITHUB_TOKEN"
    unset GITHUB_TOKEN
  elif [[ -f "$FINFLOW_GIT_TOKEN_FILE" ]]; then
    finflow_install_git_helper
  fi
}

finflow_git() {
  local dir="$1"
  shift
  local -a args=(git -C "$dir" -c "safe.directory=*")
  if [[ -f "$FINFLOW_GIT_TOKEN_FILE" ]]; then
    finflow_install_git_helper
    args+=(-c credential.helper=)
    args+=(-c "credential.helper=!${FINFLOW_GIT_HELPER}")
  fi
  "${args[@]}" "$@"
}

finflow_clone() {
  local repo="$1"
  local dir="$2"
  local branch="$3"
  local -a args=(git -c "safe.directory=*")
  if [[ -f "$FINFLOW_GIT_TOKEN_FILE" ]]; then
    finflow_install_git_helper
    args+=(-c credential.helper=)
    args+=(-c "credential.helper=!${FINFLOW_GIT_HELPER}")
  fi
  "${args[@]}" clone --branch "$branch" "$repo" "$dir"
}

finflow_install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "Docker déjà installé : $(docker --version)"
    return 0
  fi
  apt-get remove -y docker.io docker-compose docker-doc podman-docker >/dev/null 2>&1 || true
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg.tmp
  install -m 0644 /etc/apt/keyrings/docker.gpg.tmp /etc/apt/keyrings/docker.gpg
  rm -f /etc/apt/keyrings/docker.gpg.tmp
  # shellcheck disable=SC1091
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

finflow_docker_log_limits() {
  local f="/etc/docker/daemon.json"
  if [[ -f "$f" ]]; then
    return 0
  fi
  mkdir -p /etc/docker
  cat > "$f" <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "20m",
    "max-file": "3"
  }
}
EOF
  if docker ps -q 2>/dev/null | grep -q .; then
    echo deferred
    return 0
  fi
  systemctl restart docker >/dev/null
  echo restarted
}
