#!/bin/bash
file_list="dlgis *.py"

echo_result() {
    [[ "$1" -eq 0 ]] && echo "$2: SUCCESS" || echo "$2: FAILURE"
}

ret_code=0
run_command() {
    echo "Running: '$@'"
    $@
    local rc=$?
    [[ $rc -ne 0 ]] && ret_code=1
    echo_result $rc Result
}

run_command black --check $file_list
run_command mypy --strict $file_list
run_command flake8 $file_list
run_command pylint $file_list

echo_result $ret_code "Overall Result"

exit $ret_code
