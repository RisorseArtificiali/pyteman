#!/usr/bin/env bash
# Reproduce every verified leg of the two Hermes examples from nothing: fetch
# each tested upstream revision by its full SHA, build a venv holding pyteman
# and the upstream's one import-time dependency, and run each leg against its
# expected verdict. Linux and network only.
#
#   examples/verify_hermes_legs.sh [pyteman-spec] [workdir]
#
# pyteman-spec is anything pip installs; empty or absent means this checkout,
# pyteman==0.2.0 verifies the release. workdir defaults to a fresh temp dir;
# a reused one keeps its fetched revisions, each checked against its SHA.
# PYTHON picks the interpreter (default python3.13; the upstream declares
# requires-python >=3.11,<3.14). Exit 0 when every leg matched, 1 when a
# leg answered otherwise, 2 when the setup or a leg could not run or answer
# (a leg's driver error or INCONCLUSIVE outranks another leg's mismatch).
set -euo pipefail
trap 'echo "LEGS-SETUP-ERROR: line $LINENO; workdir ${work:-unset}" >&2; exit 2' ERR

here=$(cd "$(dirname "$0")" && pwd)
spec=${1:-$(dirname "$here")}
work=${2:-$(mktemp -d)}
python=${PYTHON:-python3.13}
upstream=https://github.com/NousResearch/hermes-agent

# The revisions the READMEs' verified legs name, and nothing newer: a later
# tip is unverified until it is added here and run.
tip_109966=2cfb655d52e7e482523236c4012b61fcb54b37ce
base_111912=5910de20bc9839fdd36e791a9d72ba2c2e722f66
fix_111912=6602939a4f50570b437e7ced4b043a5986bb7717  # PR #112069 head

for rev in "$tip_109966" "$base_111912" "$fix_111912"; do
    dir=$work/hermes-$rev
    # Fetched again from scratch unless already there: an interrupted
    # fetch leaves a repository with no HEAD, and an interrupted checkout
    # leaves files the next checkout would refuse to overwrite.
    if [ "$(git -C "$dir" rev-parse -q --verify HEAD 2>/dev/null)" != "$rev" ]; then
        rm -rf "$dir"
        git init -q "$dir"
        git -C "$dir" fetch -q --depth 1 "$upstream" "$rev"
        git -C "$dir" checkout -q --detach FETCH_HEAD
    fi
    head=$(git -C "$dir" rev-parse HEAD)
    [ "$head" = "$rev" ] || { echo "LEGS-SETUP-ERROR: $dir is at $head, not $rev" >&2; exit 2; }
done
# --clear: pip keeps an installed pyteman of the same version, so a reused
# venv would test the previous run's build under the new spec's name.
"$python" -m venv --clear "$work/venv"
"$work/venv/bin/pip" install -q "$spec" pyyaml==6.0.3
trap - ERR

failed=0
leg() {
    echo "=== $*"
    local rc=0
    "$work/venv/bin/python" "$@" || rc=$?
    [ $rc = 0 ] && return
    echo "LEG-FAILED rc=$rc"
    if [ $rc = 1 ]; then [ $failed = 2 ] || failed=1; else failed=2; fi
}
leg111912() {  # revision, ruleset stem, expected verdict
    leg "$here/hermes-111912/run_repro.py" "$work/hermes-$1" "$here/hermes-111912/rules-$2.yaml" "$3"
}
leg "$here/hermes-109966/run_repro.py" "$work/hermes-$tip_109966" CLEAN
leg111912 "$base_111912" slow-teardown REPRODUCED
leg111912 "$fix_111912" slow-teardown CLEAN
leg111912 "$base_111912" wedged-teardown REPRODUCED
leg111912 "$fix_111912" wedged-teardown REPRODUCED
case $failed in 0) outcome="all matched" ;; 1) outcome=MISMATCH ;; *) outcome=ERROR ;; esac
echo "LEGS: $outcome (workdir $work)"
exit $failed
