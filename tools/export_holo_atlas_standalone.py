"""
Build a fully self-contained, offline standalone copy of /holo-atlas -- no FastAPI
backend, no network calls, real data and Three.js both embedded directly in the
HTML file. This is the artifact published as a shareable, any-device link when a
live server isn't available (e.g. via the Artifact tool).

Real data is embedded verbatim from the same adapter functions the live
`/holo-atlas` page's endpoints call (`tools/command_center/real_results_adapter.py`),
not recomputed or approximated. Three.js and its OrbitControls addon are embedded
as inlined ES module source, loaded at runtime via a local Blob URL + dynamic
`import()` -- this avoids both a CDN dependency (blocked by this sandbox's proxy,
and undesirable in a portable artifact anyway) and any change to the addon's own
`import ... from 'three'` statement beyond substituting the blob URL string.

Requires `npm install three@0.166.1` in a scratch directory first (matches the
version pinned in apps/awareness_studio/src/awareness_studio/web/static/holo_atlas.html's
now-removed importmap) to obtain:
  node_modules/three/build/three.module.min.js
  node_modules/three/examples/jsm/controls/OrbitControls.js

Usage:
  npm install three@0.166.1 --prefix /tmp/holo_standalone_build
  python tools/export_holo_atlas_standalone.py \\
      --three-dir /tmp/holo_standalone_build/node_modules/three \\
      --out /tmp/holo_atlas_standalone.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HOLO_ATLAS_SRC = (
    REPOSITORY_ROOT / "apps/awareness_studio/src/awareness_studio/web/static/holo_atlas.html"
)
BRAIN_MESH_SRC = (
    REPOSITORY_ROOT
    / "apps/awareness_studio/src/awareness_studio/web/static/data/fsaverage5_pial.json"
)

OLD_MODULE_HEAD = """import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

async function boot() {
  var stage = document.getElementById('ha-scene');
  var results;
  try {
    results = await Promise.all([
      fetch('/vortex-field/data').then(function (r) { return r.json(); }),
      fetch('/fmri-connectome/data').then(function (r) { return r.json(); }),
      fetch('/mapper-graph/data').then(function (r) { return r.json(); }),
      fetch('/static/data/fsaverage5_pial.json').then(function (r) { return r.json(); }),
      fetch('/command-center/visualization').then(function (r) { return r.json(); }),
      fetch('/fmri-connectome/data?dataset=ds006644').then(function (r) { return r.json(); })
    ]);
  } catch (err) {
    stage.parentElement.insertAdjacentHTML('beforeend', '<div class="ha-error">Failed to load combined data: ' + err + '</div>');
    return;
  }
  var vf = results[0], fc = results[1], mg = results[2], brainRaw = results[3], ccViz = results[4], fcLabeled = results[5];
  if (vf.status !== 'available') {
    stage.parentElement.insertAdjacentHTML('beforeend', '<div class="ha-error">EEG data unavailable: ' + (vf.reason || 'unknown') + '</div>');
    return;
  }
  run(vf, fc, mg, brainRaw, ccViz, fcLabeled);
}

function run(VF, FC, MG, BRAIN_RAW, CC_VIZ, FC_LABELED) {"""

NEW_MODULE_HEAD = """async function boot() {
  var stage = document.getElementById('ha-scene');
  var THREE, OrbitControls, vf, fc, mg, brainRaw, ccViz, fcLabeled;
  try {
    var threeSrc = document.getElementById('three-src').textContent;
    var threeUrl = URL.createObjectURL(new Blob([threeSrc], { type: 'text/javascript' }));
    THREE = await import(threeUrl);

    var controlsSrc = document.getElementById('controls-src').textContent
      .replace("from 'three'", "from '" + threeUrl + "'");
    var controlsUrl = URL.createObjectURL(new Blob([controlsSrc], { type: 'text/javascript' }));
    OrbitControls = (await import(controlsUrl)).OrbitControls;

    vf = JSON.parse(document.getElementById('vf-json').textContent);
    fc = JSON.parse(document.getElementById('fc-json').textContent);
    mg = JSON.parse(document.getElementById('mg-json').textContent);
    brainRaw = JSON.parse(document.getElementById('brain-json').textContent);
    ccViz = JSON.parse(document.getElementById('cc-viz-json').textContent);
    fcLabeled = JSON.parse(document.getElementById('fc-labeled-json').textContent);
  } catch (err) {
    stage.parentElement.insertAdjacentHTML('beforeend', '<div class="ha-error">Failed to load embedded data: ' + err + '</div>');
    return;
  }
  if (vf.status !== 'available') {
    stage.parentElement.insertAdjacentHTML('beforeend', '<div class="ha-error">EEG data unavailable: ' + (vf.reason || 'unknown') + '</div>');
    return;
  }
  run(vf, fc, mg, brainRaw, ccViz, fcLabeled, THREE, OrbitControls);
}

function run(VF, FC, MG, BRAIN_RAW, CC_VIZ, FC_LABELED, THREE, OrbitControls) {"""

OLD_EYEBROW = (
    '<span><a href="/atlas">TABBED ATLAS</a> &middot; '
    '<a href="/command-center">COMMAND CENTRE</a></span>'
)
NEW_EYEBROW = "<span>STANDALONE BUILD &middot; DATA FROZEN AT GENERATION TIME</span>"

OLD_FOOTER = (
    "      Sources: <code>/vortex-field/data</code>, <code>/fmri-connectome/data</code>,\n"
    "      <code>/mapper-graph/data</code> &mdash; the same real endpoints the standalone\n"
    "      <a href=\"/vortex-field\">vortex field</a>, <a href=\"/fmri-connectome\">fMRI connectome</a>, and\n"
    "      <a href=\"/mapper-graph\">Mapper graph</a> pages use &mdash; plus <code>/command-center/visualization</code>\n"
    "      for the real per-subject H1 persistence diagrams and per-subject EEG spatial swap. This page adds\n"
    "      no new computation; it is a single combined rendering of already-real, already-tested data."
)
NEW_FOOTER = (
    "      Sources: the same real ds005620 (propofol anesthesia EEG), ds005917 (ketamine fMRI), and\n"
    "      KeplerMapper cohort-structure computations as the live NeuroTopology-Sim Command Centre --\n"
    "      exported once and embedded directly in this file, including the real per-subject H1 persistence\n"
    "      diagrams and per-subject EEG spatial swap data, so it renders with no backend, no server, and no\n"
    "      network calls at all. Three.js is embedded the same way (as inlined source, loaded via a local\n"
    "      Blob URL) so this page never fetches anything from the internet."
)


def build_standalone_html(three_dir: Path) -> str:
    from tools.command_center.real_results_adapter import (
        build_fmri_connectome_payload,
        build_mapper_graph_payload,
        build_vortex_field_payload,
        build_visualization_payload,
    )

    vf = build_vortex_field_payload()
    fc = build_fmri_connectome_payload()
    mg = build_mapper_graph_payload()
    cc_viz = build_visualization_payload()
    fc_labeled = build_fmri_connectome_payload(dataset="ds006644")
    if vf.get("status") != "available":
        raise RuntimeError(f"vortex-field payload unavailable: {vf.get('reason')}")

    brain_json = BRAIN_MESH_SRC.read_text(encoding="utf-8")
    three_src = (three_dir / "build" / "three.module.min.js").read_text(encoding="utf-8")
    controls_src = (
        three_dir / "examples" / "jsm" / "controls" / "OrbitControls.js"
    ).read_text(encoding="utf-8")
    for name, text in (("three.module.min.js", three_src), ("OrbitControls.js", controls_src)):
        if "</script" in text:
            raise RuntimeError(f"{name} contains a literal '</script' -- would break HTML parsing")

    html = HOLO_ATLAS_SRC.read_text(encoding="utf-8")
    html = re.sub(r'<script type="importmap">.*?</script>\n', "", html, flags=re.S)
    html = html.replace(
        "<title>Holo-Atlas — Combined EEG · fMRI · Mapper, One Brain</title>",
        "<title>Holo-Atlas (Standalone) — Anesthesia EEG · fMRI · Mapper, One Brain</title>",
    )
    html = html.replace(OLD_EYEBROW, NEW_EYEBROW)
    html = html.replace(OLD_FOOTER, NEW_FOOTER)

    if OLD_MODULE_HEAD not in html:
        raise RuntimeError(
            "holo_atlas.html's module head has changed and no longer matches this "
            "script's expected text -- update OLD_MODULE_HEAD/NEW_MODULE_HEAD together."
        )
    html = html.replace(OLD_MODULE_HEAD, NEW_MODULE_HEAD)

    data_blocks = (
        '<script type="application/json" id="vf-json">' + json.dumps(vf, separators=(",", ":")) + "</script>\n"
        '<script type="application/json" id="fc-json">' + json.dumps(fc, separators=(",", ":")) + "</script>\n"
        '<script type="application/json" id="mg-json">' + json.dumps(mg, separators=(",", ":")) + "</script>\n"
        '<script type="application/json" id="brain-json">' + brain_json + "</script>\n"
        '<script type="application/json" id="cc-viz-json">' + json.dumps(cc_viz, separators=(",", ":")) + "</script>\n"
        '<script type="application/json" id="fc-labeled-json">' + json.dumps(fc_labeled, separators=(",", ":")) + "</script>\n"
        '<script type="application/octet-stream" id="three-src">' + three_src + "</script>\n"
        '<script type="application/octet-stream" id="controls-src">' + controls_src + "</script>\n"
    )
    html = html.replace('<script type="module">', data_blocks + '<script type="module">', 1)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--three-dir", required=True, help="path to node_modules/three (after npm install three@0.166.1)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))

    html = build_standalone_html(Path(args.three_dir))
    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
