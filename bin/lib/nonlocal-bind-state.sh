validate_nonlocal_bind_state_linux() {
  if [ -L "${SYSCTL_STATE_FILE}" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} is a symlink; refusing to trust recovery state" >&2
    return 1
  fi
  if [ ! -e "${SYSCTL_STATE_FILE}" ]; then
    return 0
  fi
  if [ ! -f "${SYSCTL_STATE_FILE}" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} exists but is not a regular file" >&2
    return 1
  fi
  if [ ! -r "${SYSCTL_STATE_FILE}" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} exists but is not readable" >&2
    return 1
  fi

  local state_version="" file_present="" runtime_value=""
  local file_mode="" file_owner="" file_group=""
  local seen_state_version=0 seen_file_present=0 seen_runtime_value=0
  local seen_file_mode=0 seen_file_owner=0 seen_file_group=0
  local line key value
  while IFS= read -r line || [ -n "${line}" ]; do
    case "${line}" in
      *=*=*|"")
        echo "ERROR: ${SYSCTL_STATE_FILE} has malformed row: ${line}" >&2
        return 1
        ;;
      *=*)
        key="${line%%=*}"
        value="${line#*=}"
        ;;
      *)
        echo "ERROR: ${SYSCTL_STATE_FILE} has malformed row: ${line}" >&2
        return 1
        ;;
    esac

    case "${key}" in
      state_version)
        if [ "${seen_state_version}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate state_version" >&2
          return 1
        fi
        seen_state_version=1
        state_version="${value}"
        ;;
      file_present)
        if [ "${seen_file_present}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate file_present" >&2
          return 1
        fi
        seen_file_present=1
        file_present="${value}"
        ;;
      runtime_value)
        if [ "${seen_runtime_value}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate runtime_value" >&2
          return 1
        fi
        seen_runtime_value=1
        runtime_value="${value}"
        ;;
      file_mode)
        if [ "${seen_file_mode}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate file_mode" >&2
          return 1
        fi
        seen_file_mode=1
        file_mode="${value}"
        ;;
      file_owner)
        if [ "${seen_file_owner}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate file_owner" >&2
          return 1
        fi
        seen_file_owner=1
        file_owner="${value}"
        ;;
      file_group)
        if [ "${seen_file_group}" = "1" ]; then
          echo "ERROR: ${SYSCTL_STATE_FILE} has duplicate file_group" >&2
          return 1
        fi
        seen_file_group=1
        file_group="${value}"
        ;;
      *)
        echo "ERROR: ${SYSCTL_STATE_FILE} has unknown key: ${key}" >&2
        return 1
        ;;
    esac
  done < "${SYSCTL_STATE_FILE}"

  if [ "${seen_file_present}" != "1" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} is missing file_present" >&2
    return 1
  fi
  if [ "${seen_runtime_value}" != "1" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} is missing runtime_value" >&2
    return 1
  fi

  case "${file_present}" in
    0|1) ;;
    *)
      echo "ERROR: ${SYSCTL_STATE_FILE} has invalid file_present=${file_present}" >&2
      return 1
      ;;
  esac
  case "${runtime_value}" in
    0|1) ;;
    *)
      echo "ERROR: ${SYSCTL_STATE_FILE} has invalid runtime_value=${runtime_value}" >&2
      return 1
      ;;
  esac

  if [ "${seen_state_version}" = "1" ]; then
    case "${state_version}" in
      2) ;;
      *)
        echo "ERROR: ${SYSCTL_STATE_FILE} has invalid state_version=${state_version}" >&2
        return 1
        ;;
    esac
  elif [ "${file_present}" != "0" ]; then
    echo "ERROR: legacy ${SYSCTL_STATE_FILE} cannot restore original ${SYSCTL_DEST} content." >&2
    echo "Resolve manually, then remove ${SYSCTL_STATE_FILE} before re-running." >&2
    return 1
  fi

  if [ "${file_present}" = "0" ]; then
    if [ "${seen_file_mode}${seen_file_owner}${seen_file_group}" != "000" ]; then
      echo "ERROR: ${SYSCTL_STATE_FILE} carries file metadata while file_present=0" >&2
      return 1
    fi
    return 0
  fi
  if [ "${seen_file_mode}${seen_file_owner}${seen_file_group}" != "111" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} is missing file metadata for file_present=1" >&2
    return 1
  fi
  if [ -L "${SYSCTL_STATE_CONTENT_FILE}" ] || [ ! -f "${SYSCTL_STATE_CONTENT_FILE}" ] || [ ! -r "${SYSCTL_STATE_CONTENT_FILE}" ]; then
    echo "ERROR: ${SYSCTL_STATE_FILE} requires a readable regular ${SYSCTL_STATE_CONTENT_FILE}" >&2
    return 1
  fi

  if ! grep -Eq '^[0-7]{3,4}$' <<<"${file_mode}"; then
    echo "ERROR: ${SYSCTL_STATE_FILE} has invalid file_mode=${file_mode}" >&2
    return 1
  fi
  if ! grep -Eq '^[0-9]+$' <<<"${file_owner}"; then
    echo "ERROR: ${SYSCTL_STATE_FILE} has invalid file_owner=${file_owner}" >&2
    return 1
  fi
  if ! grep -Eq '^[0-9]+$' <<<"${file_group}"; then
    echo "ERROR: ${SYSCTL_STATE_FILE} has invalid file_group=${file_group}" >&2
    return 1
  fi
}
