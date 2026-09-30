#!/usr/bin/env sh

set -eu

usage() {
    printf '%s\n' "Usage: $0 [--yes]"
    printf '%s\n' ""
    printf '%s\n' "Updates the user-level Codex remote-control service and restarts the app-server."
    printf '%s\n' "--yes  Do not ask for confirmation; active Codex app-server sessions may be interrupted."
}

assume_yes=0
case "${1:-}" in
    "") ;;
    --yes|-y) assume_yes=1 ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

user_home=${HOME:?HOME is not set}
codex_state=${CODEX_HOME:-"$user_home/.codex"}
config_root=${XDG_CONFIG_HOME:-"$user_home/.config"}
codex_bin="$codex_state/packages/standalone/current/bin/codex"
unit_file="$config_root/systemd/user/codex-remote-control.service"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

for command_name in systemctl readlink awk mktemp pgrep; do
    command -v "$command_name" >/dev/null 2>&1 || die "Required command not found: $command_name"
done

[ -x "$codex_bin" ] || die "Managed Codex binary not found: $codex_bin"
[ -f "$unit_file" ] || die "User service unit not found: $unit_file"

current_exe=$(readlink -f "$codex_bin")
codex_version=$("$codex_bin" --version 2>&1) || die "Could not execute $codex_bin"
user_id=$(id -u)

printf 'Codex binary: %s\n' "$current_exe"
printf 'Codex version: %s\n' "$codex_version"
printf 'Service unit: %s\n' "$unit_file"
printf '\n'

if [ "$assume_yes" -ne 1 ]; then
    printf '%s' 'The Codex app-server will be restarted and active sessions may be interrupted. Continue? [y/N] '
    IFS= read -r answer
    case "$answer" in
        y|Y|yes|YES|Yes) ;;
        *)
            printf '%s\n' 'Cancelled.'
            exit 0
            ;;
    esac
fi

timestamp=$(date +%Y%m%d-%H%M%S)
unit_backup="${unit_file}.bak.${timestamp}"
cp -p "$unit_file" "$unit_backup"
printf 'Backup created: %s\n' "$unit_backup"

printf '%s\n' 'Stopping the currently managed remote-control daemon...'
"$codex_bin" remote-control stop >/dev/null 2>&1 || true
systemctl --user stop codex-remote-control.service >/dev/null 2>&1 || true

unit_tmp=$(mktemp "${unit_file}.tmp.XXXXXX")
cleanup() {
    rm -f "$unit_tmp"
}
trap cleanup EXIT HUP INT TERM

if ! awk -v codex_path="$codex_bin" '
    /^ExecStart=/ {
        print "ExecStart=" codex_path " remote-control start"
        found_start = 1
        next
    }
    /^ExecStop=/ {
        print "ExecStop=" codex_path " remote-control stop"
        found_stop = 1
        next
    }
    { print }
    END {
        if (!found_start || !found_stop) {
            exit 42
        }
    }
' "$unit_file" > "$unit_tmp"; then
    die "Could not update ExecStart/ExecStop in $unit_file"
fi

chmod 0644 "$unit_tmp"
mv "$unit_tmp" "$unit_file"
trap - EXIT HUP INT TERM
printf '%s\n' 'Service unit now points to the current managed Codex binary.'

find_stale_pids() {
    stale_pids=''
    for pid in $(pgrep -u "$user_id" -f '[c]odex' 2>/dev/null || true); do
        proc_cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$proc_cmdline" in
            *app-server*|*code-mode-host*)
                proc_exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
                if [ "$proc_exe" != "$current_exe" ]; then
                    stale_pids="$stale_pids $pid"
                fi
                ;;
        esac
    done
    printf '%s' "$stale_pids"
}

stale_pids=$(find_stale_pids)
if [ -n "$stale_pids" ]; then
    printf 'Stopping stale Codex process(es):%s\n' "$stale_pids"
    # These are only app-server/code-mode-host processes, never the plain CLI.
    kill $stale_pids 2>/dev/null || true

    deadline=$(( $(date +%s) + 10 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        remaining=''
        for pid in $stale_pids; do
            if kill -0 "$pid" 2>/dev/null; then
                remaining="$remaining $pid"
            fi
        done
        [ -z "$remaining" ] && break
        sleep 1
    done

    remaining=''
    for pid in $stale_pids; do
        if kill -0 "$pid" 2>/dev/null; then
            remaining="$remaining $pid"
        fi
    done
    [ -z "$remaining" ] || die "Could not stop stale Codex process(es):$remaining"
fi

systemctl --user daemon-reload
systemctl --user reset-failed codex-remote-control.service >/dev/null 2>&1 || true
systemctl --user enable codex-remote-control.service >/dev/null
if ! systemctl --user start codex-remote-control.service; then
    systemctl --user status codex-remote-control.service --no-pager >&2 || true
    die 'Could not start codex-remote-control.service'
fi

if ! systemctl --user is-active --quiet codex-remote-control.service; then
    systemctl --user status codex-remote-control.service --no-pager >&2 || true
    die 'codex-remote-control.service did not become active'
fi

current_server_pid=''
deadline=$(( $(date +%s) + 10 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    for pid in $(pgrep -u "$user_id" -f '[c]odex' 2>/dev/null || true); do
        proc_cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$proc_cmdline" in
            *app-server*)
                proc_exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
                if [ "$proc_exe" = "$current_exe" ]; then
                    current_server_pid=$pid
                    break
                fi
                ;;
        esac
    done
    [ -n "$current_server_pid" ] && break
    sleep 1
done

[ -n "$current_server_pid" ] || die 'Service is active, but no app-server using the current binary was found'

printf '\n%s\n' 'Codex service updated successfully.'
printf 'Service status: active\n'
printf 'App-server PID: %s\n' "$current_server_pid"
printf 'App-server binary: %s\n' "$current_exe"
