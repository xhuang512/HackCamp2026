#!/usr/bin/env bash
set -euo pipefail

required=(
  LIFECYCLE_TEST_DB_URL
  LIFECYCLE_TEST_PROJECT_REF
  LIFECYCLE_TEST_CONFIRM_DISPOSABLE
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required variable: ${name}" >&2
    exit 2
  fi
done

if [[ "${LIFECYCLE_TEST_CONFIRM_DISPOSABLE}" != "YES_DELETE_TEST_DATA" ]]; then
  echo "Refusing to continue without the disposable-project confirmation." >&2
  exit 2
fi

if [[ "${LIFECYCLE_TEST_DB_URL}" != *"${LIFECYCLE_TEST_PROJECT_REF}"* ]]; then
  echo "The database URL does not match LIFECYCLE_TEST_PROJECT_REF." >&2
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required to apply the test schema." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sql_dir="$(cd "${script_dir}/../sql" && pwd)"

existing_students="$(
  psql "${LIFECYCLE_TEST_DB_URL}" -X -A -t -v ON_ERROR_STOP=1 \
    -c "select to_regclass('public.students') is not null"
)"
if [[ "${existing_students}" == "t" ]]; then
  echo "Refusing to initialize a database that already contains public.students." >&2
  exit 2
fi

psql "${LIFECYCLE_TEST_DB_URL}" -X -v ON_ERROR_STOP=1 \
  -f "${sql_dir}/001_core_schema.sql"
psql "${LIFECYCLE_TEST_DB_URL}" -X -v ON_ERROR_STOP=1 \
  -f "${sql_dir}/002_group_lifecycle.sql"

echo "Lifecycle V2 schema installed in the confirmed disposable project."
