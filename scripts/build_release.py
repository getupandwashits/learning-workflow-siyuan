#!/usr/bin/env python3
"""Build release assets.

1. Always builds a Markdown zip from starter/ (importable via SiYuan's
   "导入 Markdown .zip").
2. Optionally builds a native .sy.zip by driving a running SiYuan kernel:
   create a temporary notebook -> create one document per starter/*.md
   -> export .sy.zip -> remove the temporary notebook.

Usage:
    python3 scripts/build_release.py --base-url http://127.0.0.1:6806 [--token TOKEN]
    python3 scripts/build_release.py --markdown-only

The token is only used in memory and is never written to disk.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STARTER = os.path.join(REPO, "starter")
RELEASE = os.path.join(REPO, "release")
MD_ZIP = os.path.join(RELEASE, "learning-workflow-siyuan-starter-md.zip")
SY_ZIP = os.path.join(RELEASE, "learning-workflow-siyuan-starter.sy.zip")


def build_markdown_zip():
    os.makedirs(RELEASE, exist_ok=True)
    with zipfile.ZipFile(MD_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, files in os.walk(STARTER):
            for name in sorted(files):
                if name.startswith("."):
                    continue
                path = os.path.join(dirpath, name)
                z.write(path, os.path.relpath(path, STARTER))
    return MD_ZIP


def api(base, path, payload, token=None, timeout=90):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(payload).encode(), headers=headers
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def create_docs(base, token, notebook):
    for name in sorted(os.listdir(STARTER)):
        if not name.endswith(".md") or name.startswith("."):
            continue
        with open(os.path.join(STARTER, name), encoding="utf-8") as f:
            markdown = f.read()
        created = api(
            base,
            "/api/filetree/createDocWithMd",
            {"notebook": notebook, "path": "/" + name[:-3], "markdown": markdown},
            token,
        )
        if created.get("code") != 0:
            raise RuntimeError(f"createDocWithMd failed for {name}: {created}")


def write_zip_payload(payload, out_path, base):
    value = payload
    if isinstance(value, dict):
        value = value.get("zip") or value.get("path") or value.get("content")
    if not isinstance(value, str) or not value:
        raise RuntimeError("unexpected exportNotebookSY payload")
    if value.startswith(("http://", "https://")):
        with urllib.request.urlopen(value, timeout=120) as resp:
            raw = resp.read()
    elif value.startswith("/"):
        with urllib.request.urlopen(base.rstrip("/") + value, timeout=120) as resp:
            raw = resp.read()
    elif os.path.exists(value):
        with open(value, "rb") as f:
            raw = f.read()
    else:
        raw = base64.b64decode(value)
    if not raw.startswith(b"PK"):
        raise RuntimeError("exported payload is not a zip")
    with open(out_path, "wb") as f:
        f.write(raw)


def build_sy_zip(base, token):
    temp_name = "学习与成长-上手骨架"
    notebook_id = None
    try:
        created = api(base, "/api/notebook/createNotebook", {"name": temp_name}, token)
        if created.get("code") != 0:
            raise RuntimeError(f"createNotebook failed: {created}")
        notebook_id = created["data"]["notebook"]["id"]
        print(f"temporary notebook: {notebook_id}", file=sys.stderr)

        create_docs(base, token, notebook_id)

        for _ in range(10):
            time.sleep(1)
            exported = api(
                base, "/api/export/exportNotebookSY", {"id": notebook_id}, token
            )
            if exported.get("code") != 0:
                raise RuntimeError(f"exportNotebookSY failed: {exported}")
            try:
                write_zip_payload(exported.get("data"), SY_ZIP, base)
                return SY_ZIP
            except RuntimeError:
                continue
        raise RuntimeError("exportNotebookSY kept returning an empty zip")
    finally:
        if notebook_id:
            try:
                api(base, "/api/notebook/removeNotebook", {"notebook": notebook_id}, token)
                print("temporary notebook removed", file=sys.stderr)
            except Exception as e:
                print(f"WARNING: failed to remove temp notebook: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:6806")
    parser.add_argument("--token", default=os.environ.get("SIYUAN_API_TOKEN", ""))
    parser.add_argument("--markdown-only", action="store_true")
    args = parser.parse_args()

    md = build_markdown_zip()
    print(md)
    if args.markdown_only:
        return
    sy = build_sy_zip(args.base_url, args.token or None)
    print(sy)


if __name__ == "__main__":
    main()
