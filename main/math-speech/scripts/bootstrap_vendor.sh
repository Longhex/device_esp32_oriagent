#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(cd -- "${script_dir}/.." && pwd)"
repo_root="$(cd -- "${service_dir}/../.." && pwd)"
vendor_dir="${service_dir}/vendor"
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "${tmp_dir}"' EXIT

binary_url="https://github.com/daisy/MathCATForPython/releases/download/v0.7.3/libmathcat_py-64-3.11-linux.zip"
rules_url="https://github.com/daisy/MathCATForPython/releases/download/v0.7.3/Rules.zip"
binary_sha256="cf72ddff5bdfd24ca397d40eb2a50dcc9e4ac1c5acd0f2044d938fc945cc7fc5"
rules_sha256="3eab4b5b5d2c8ca4adf3aac203efbc638191e5ddab6f72c4b35f690758b7c9a5"

curl --fail --location --retry 3 --output "${tmp_dir}/lib.zip" "${binary_url}"
curl --fail --location --retry 3 --output "${tmp_dir}/rules.zip" "${rules_url}"
printf '%s  %s\n' "${binary_sha256}" "${tmp_dir}/lib.zip" | sha256sum --check -
printf '%s  %s\n' "${rules_sha256}" "${tmp_dir}/rules.zip" | sha256sum --check -

mkdir -p "${tmp_dir}/lib" "${tmp_dir}/rules" "${vendor_dir}/licenses"
unzip -q "${tmp_dir}/lib.zip" -d "${tmp_dir}/lib"
unzip -q "${tmp_dir}/rules.zip" -d "${tmp_dir}/rules"

binary_path="$(find "${tmp_dir}/lib" -type f -name 'libmathcat_py.so' -print -quit)"
if [[ -z "${binary_path}" ]]; then
  echo "libmathcat_py.so not found in the official archive" >&2
  exit 1
fi
cp "${binary_path}" "${vendor_dir}/libmathcat_py.so"

rm -rf -- "${vendor_dir}/Rules"
if [[ -d "${tmp_dir}/rules/Rules" ]]; then
  cp -R "${tmp_dir}/rules/Rules" "${vendor_dir}/Rules"
else
  mkdir -p "${vendor_dir}/Rules"
  cp -R "${tmp_dir}/rules/." "${vendor_dir}/Rules/"
fi

cp "${repo_root}/third_party/math-tts-src/MathCAT/LICENSE" \
  "${vendor_dir}/licenses/MathCAT-LICENSE"
cp "${repo_root}/third_party/math-tts-src/MathCATForPython/LICENSE" \
  "${vendor_dir}/licenses/MathCATForPython-LICENSE"

echo "Vendored MathCATForPython v0.7.3 for CPython 3.11 into ${vendor_dir}"
