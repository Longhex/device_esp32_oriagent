#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
target="${repo_root}/third_party/math-tts-src"
mkdir -p "${target}"

clone_once() {
  local url="$1"
  local name="$2"
  if [[ -d "${target}/${name}/.git" ]]; then
    echo "${name}: already cloned"
    return
  fi
  git clone --depth 1 "${url}" "${target}/${name}"
}

clone_once https://github.com/daisy/MathCAT.git MathCAT
clone_once https://github.com/daisy/MathCATForPython.git MathCATForPython
clone_once https://github.com/roniemartinez/latex2mathml.git latex2mathml
clone_once https://github.com/Speech-Rule-Engine/speech-rule-engine.git speech-rule-engine

git -C "${target}/MathCAT" rev-parse HEAD
git -C "${target}/MathCATForPython" rev-parse HEAD
git -C "${target}/latex2mathml" rev-parse HEAD
git -C "${target}/speech-rule-engine" rev-parse HEAD
