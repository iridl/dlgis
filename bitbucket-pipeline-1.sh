#!/bin/bash

function ret {
    return $1
}

echo "black:"
black --check .
ret_black=$?

echo "mypy:"
mypy --strict .
ret_mypy=$?

echo "flake8:"
flake8 dlgis *.py
ret_flake8=$?

echo "pylint:"
pylint dlgis *.py
ret_pylint=$?

ret $ret_black &&\
ret $ret_mypy &&\
ret $ret_flake8 &&\
ret $ret_pylint
ret_code=$?

echo "result:"
if [ $ret_code -eq 0 ]; then
    echo "SUCCESS"
else
    echo "FAILURE"
fi

exit $ret_code
