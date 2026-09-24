#!/usr/bin/env python
"""Xray Cloud GraphQL helper for the unattended QA routine.

Ships with the qa-workflow plugin and reads its settings from
~/.claude/qa-config.json (copy plugins/qa-workflow/qa-config.example.json there).

Usage:
  python xray-graphql.py '<graphql query or mutation>'
  python xray-graphql.py --file query.graphql
  echo '<query>' | python xray-graphql.py -

The Xray endpoint comes from xray.api_base in qa-config.json. Credentials come
from the environment variables *named* in that same file
(xray.client_id_env_var / xray.client_secret_env_var); the values themselves are
read from the environment, falling back to the 'env' blocks of
~/.claude/settings.json. No secret is ever stored in qa-config.json.

Prints the raw JSON response. Exit 1 on transport or GraphQL error.
"""
import json, os, sys, urllib.request

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".claude", "qa-config.json")
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
DEFAULT_XRAY_API_BASE = "https://xray.cloud.getxray.app/api/v2"


def config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit("no config file at {}. Copy qa-config.example.json from the "
                 "qa-workflow plugin to that path and fill in your own values."
                 .format(CONFIG_PATH))
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        sys.exit("could not read {}: {}".format(CONFIG_PATH, exc))


def env_value(name):
    """Environment first, then the 'env' blocks of ~/.claude/settings.json."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            settings = json.load(fh)
    except (OSError, ValueError):
        return None
    value = (settings.get("env") or {}).get(name)
    if value:
        return value
    for server in (settings.get("mcpServers") or {}).values():
        value = ((server or {}).get("env") or {}).get(name)
        if value:
            return value
    return None


def creds(xray_cfg):
    id_var = xray_cfg.get("client_id_env_var") or "XRAY_CLIENT_ID"
    secret_var = xray_cfg.get("client_secret_env_var") or "XRAY_CLIENT_SECRET"
    cid, secret = env_value(id_var), env_value(secret_var)
    if not (cid and secret):
        sys.exit("{} and {} must be set in the environment (or in "
                 "~/.claude/settings.json under 'env'). qa-config.json holds "
                 "only the variable names.".format(id_var, secret_var))
    return cid, secret


def post(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode()


def read_query(argv):
    if not argv:
        sys.exit("no query given")
    if argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if argv[0] == "--file":
        if len(argv) < 2:
            sys.exit("--file needs a path")
        with open(argv[1], encoding="utf-8") as fh:
            return fh.read()
    if argv[0] == "-":
        return sys.stdin.read()
    return argv[0]


def main():
    query = read_query(sys.argv[1:])
    xray_cfg = (config().get("xray") or {})
    base = (xray_cfg.get("api_base") or DEFAULT_XRAY_API_BASE).rstrip("/")
    cid, secret = creds(xray_cfg)
    token = post(base + "/authenticate", {"client_id": cid, "client_secret": secret}).strip().strip('"')
    body = post(base + "/graphql", {"query": query}, token)
    print(body)
    if '"errors"' in body:
        sys.exit(1)


if __name__ == "__main__":
    main()
