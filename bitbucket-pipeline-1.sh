#!/bin/bash
black --check . &&\
mypy --strict . &&\
flake8 dlgis *.py &&\
pylint dlgis *.py
ret_code=$?

echo ""
if [ $ret_code -eq 0 ]; then
    echo "SUCCESS"
else
    echo "FAILURE"
fi

exit $ret_code
