#!/usr/bin/env bash
function tellVersion() {
    echo "1"
}

function tellName() {
    echo "Cobra"
}

function tellApplicable() {
    echo "true"
}

function runCobra() {
  SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
  rulesdir="/tmp/cobra-rules/"
  mkdir $rulesdir
  git clone https://github.com/sonatype/cobra-rules.git $rulesdir
  git clone https://github.com/sonatype/naja.git 'naja'
  cwd=$(pwd)
  cobraname="/naja/cobrarunner.py"
  cobrarunner="$SCRIPT_DIR$cobraname"
  echo "$cobrarunner" 1>&2
  pip3 install pandas 1>&2
  python3 "$cobrarunner" "./" "$rulesdir" 1>&2

  cat /tmp/tmpcobra.json | jq '.' | jq -s
}

case "$3" in
    run)
        runCobra
        ;;
    name)
        tellName
        ;;
    applicable)
        tellApplicable
        ;;
    *)
        tellVersion
        ;;
esac
