#!/usr/bin/env bash
set -euo pipefail

required=(
  SUPABASE_DB_URL
  SUPABASE_PROJECT_REF
  SUPABASE_SQL_SETUP_CONFIRM_PROJECT_REF
  SUPABASE_SQL_SETUP_CONFIRM_EMPTY
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required variable: ${name}" >&2
    exit 2
  fi
done

if [[ "${SUPABASE_SQL_SETUP_CONFIRM_EMPTY}" != "YES_INITIALIZE_EMPTY_DATABASE" ]]; then
  echo "Refusing to continue without the empty-database setup confirmation." >&2
  exit 2
fi

if [[ "${SUPABASE_SQL_SETUP_CONFIRM_PROJECT_REF}" != "${SUPABASE_PROJECT_REF}" ]]; then
  echo "The confirmed project reference does not match SUPABASE_PROJECT_REF." >&2
  exit 2
fi

if [[ "${SUPABASE_DB_URL}" != *"${SUPABASE_PROJECT_REF}"* ]]; then
  echo "SUPABASE_DB_URL does not match SUPABASE_PROJECT_REF." >&2
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required to apply the test schema." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sql_dir="$(cd "${script_dir}/../sql" && pwd)"

existing_students="$(
  psql "${SUPABASE_DB_URL}" -X -A -t -v ON_ERROR_STOP=1 \
    -c "select to_regclass('public.students') is not null"
)"
if [[ "${existing_students}" == "t" ]]; then
  echo "Refusing to initialize a database that already contains public.students." >&2
  exit 2
fi

psql "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 \
  -f "${sql_dir}/001_core_schema.sql"
psql "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 \
  -f "${sql_dir}/002_group_lifecycle.sql"

echo "Lifecycle V2 schema installed in the confirmed disposable project."
